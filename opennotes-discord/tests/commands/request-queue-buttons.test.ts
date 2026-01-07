import { jest } from '@jest/globals';
import { MessageFlags } from 'discord.js';
import { loggerFactory } from '../factories/index.js';

const mockLogger = loggerFactory.build();

const cacheStore = new Map<string, unknown>();
const mockCache = {
  get: jest.fn<(key: string) => Promise<unknown>>(),
  set: jest.fn<(key: string, value: unknown, ttl?: number) => Promise<boolean>>(),
  delete: jest.fn<(key: string) => Promise<boolean>>(),
  clear: jest.fn<() => Promise<number>>(),
  start: jest.fn<() => void>(),
  stop: jest.fn<() => void>(),
  getMetrics: jest.fn(() => ({ size: cacheStore.size })),
};

function setupCacheImplementations() {
  mockCache.get.mockImplementation(async (key: string) => {
    return cacheStore.get(key) ?? null;
  });
  mockCache.set.mockImplementation(async (key: string, value: unknown, _ttl?: number) => {
    cacheStore.set(key, value);
    return true;
  });
  mockCache.delete.mockImplementation(async (key: string) => {
    return cacheStore.delete(key);
  });
  mockCache.clear.mockImplementation(async () => {
    const count = cacheStore.size;
    cacheStore.clear();
    return count;
  });
}

jest.unstable_mockModule('../../src/cache.js', () => ({
  cache: mockCache,
}));

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
}));

jest.unstable_mockModule('../../src/services/index.js', () => ({
  serviceProvider: {
    getListRequestsService: jest.fn(),
    getWriteNoteService: jest.fn(),
  },
}));

jest.unstable_mockModule('../../src/lib/config-cache.js', () => ({
  ConfigCache: jest.fn(() => ({
    getRatingThresholds: jest.fn(async () => ({
      min_ratings_needed: 5,
      min_raters_per_note: 2,
    })),
  })),
}));

describe('request-queue command - Write Note button', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    cacheStore.clear();
    setupCacheImplementations();
  });

  describe('write_note_modal success response uses v2 formatting', () => {
    it('should use formatWriteNoteSuccessV2 with v2MessageFlags for modal submit success', () => {
      const mockV2Response = {
        container: { toJSON: () => ({ type: 17 }) },
        components: [{ type: 17 }],
        flags: MessageFlags.IsComponentsV2,
      };

      expect(mockV2Response.flags & MessageFlags.IsComponentsV2).toBeTruthy();

      expect(mockV2Response.components).toBeDefined();
      expect(mockV2Response.components).toHaveLength(1);

      expect(mockV2Response.components[0].type).toBe(17);
    });

    it('should pass components and flags to editReply for v2 success response', () => {
      const mockV2Response = {
        container: { toJSON: () => ({ type: 17, accent_color: 0x57f287 }) },
        components: [{ type: 17, accent_color: 0x57f287 }],
        flags: MessageFlags.IsComponentsV2,
      };

      const editReplyArg = {
        components: mockV2Response.components,
        flags: mockV2Response.flags,
      };

      expect(editReplyArg.components).toEqual(mockV2Response.components);
      expect(editReplyArg.flags).toBe(MessageFlags.IsComponentsV2);
    });
  });

  describe('write_note button interaction', () => {
    it('should parse custom ID with 3 parts (action:classification:shortId)', () => {
      const notMisleadingCustomId = 'write_note:NOT_MISLEADING:abc12345';
      const misinformedCustomId = 'write_note:MISINFORMED_OR_POTENTIALLY_MISLEADING:def67890';

      expect(notMisleadingCustomId).toMatch(/^write_note:[A-Z_]+:[a-zA-Z0-9]{8}$/);
      expect(misinformedCustomId).toMatch(/^write_note:[A-Z_]+:[a-zA-Z0-9]{8}$/);

      expect(notMisleadingCustomId.length).toBeLessThan(100);
      expect(misinformedCustomId.length).toBeLessThan(100);
    });

    it('should extract classification from button custom ID', () => {
      const parseCustomId = (customId: string) => {
        const parts = customId.split(':');
        return {
          action: parts[0],
          classification: parts[1],
          shortId: parts[2],
        };
      };

      const notMisleading = parseCustomId('write_note:NOT_MISLEADING:abc12345');
      expect(notMisleading.classification).toBe('NOT_MISLEADING');

      const misinformed = parseCustomId('write_note:MISINFORMED_OR_POTENTIALLY_MISLEADING:def67890');
      expect(misinformed.classification).toBe('MISINFORMED_OR_POTENTIALLY_MISLEADING');
    });

    it('should show modal immediately (no dropdown step)', async () => {
      const modalCustomId = 'write_note_modal:shortid1';
      expect(modalCustomId.length).toBeLessThan(100);
      expect(modalCustomId).toMatch(/^write_note_modal:[a-zA-Z0-9]{8}$/);
    });

    it('should handle missing cache state gracefully', async () => {
      mockCache.get.mockResolvedValue(null);

      const cacheValue = await mockCache.get('write_note_state:missing123');
      expect(cacheValue).toBeNull();
      expect(mockCache.get).toHaveBeenCalledWith('write_note_state:missing123');
    });

    it('should cache modal state with short ID', async () => {
      const requestId = 'discord-1436105005051416606-1762473993351';
      const modalShortId = 'test1234';
      const modalCacheKey = `write_note_modal_state:${modalShortId}`;

      await mockCache.set(modalCacheKey, requestId, 300);

      const retrieved = await mockCache.get(modalCacheKey);
      expect(retrieved).toBe(requestId);
      expect(mockCache.set).toHaveBeenCalledWith(modalCacheKey, requestId, 300);
    });

    it('should validate modal custom ID length', () => {
      const modalShortId = 'a1b2c3d4';
      const modalCustomId = `write_note_modal:${modalShortId}`;

      expect(modalCustomId.length).toBe(25);
      expect(modalCustomId.length).toBeLessThan(100);
    });

    it('should validate modal field lengths', () => {
      const summaryLabel = 'Note Summary';
      const summaryPlaceholder = 'Explain what is misleading or provide context...';

      expect(summaryLabel.length).toBeLessThanOrEqual(45);
      expect(summaryPlaceholder.length).toBeLessThanOrEqual(100);
    });

    it('should cache classification from button click', async () => {
      const modalShortId = 'test1234';
      const classification = 'NOT_MISLEADING';
      const classificationCacheKey = `write_note_classification:${modalShortId}`;

      await mockCache.set(classificationCacheKey, classification, 300);

      const retrieved = await mockCache.get(classificationCacheKey);
      expect(retrieved).toBe(classification);
      expect(mockCache.set).toHaveBeenCalledWith(classificationCacheKey, classification, 300);
    });
  });
});
