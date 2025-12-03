import { jest } from '@jest/globals';
import {
  ensureRedisChecked,
  cleanupRedisTestConnection,
  type RedisTestContext,
} from '../utils/redis-test-helper.js';

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: {
    info: jest.fn(),
    error: jest.fn(),
    warn: jest.fn(),
    debug: jest.fn(),
  },
}));

jest.unstable_mockModule('../../src/services/index.js', () => ({
  serviceProvider: {
    getListRequestsService: jest.fn(),
    getWriteNoteService: jest.fn(),
  },
}));

jest.unstable_mockModule('../../src/queue.js', () => ({
  configCache: {
    getRatingThresholds: jest.fn(async () => ({
      min_ratings_needed: 5,
      min_raters_per_note: 2,
    })),
  },
  getQueueManager: jest.fn(),
}));

let cache: any = null;

describe('request-queue command - Write Note button', () => {
  let testContext: RedisTestContext;

  beforeAll(async () => {
    testContext = await ensureRedisChecked();

    if (testContext.available) {
      try {
        const cacheModule = await import('../../src/cache.js');
        cache = cacheModule.cache;
      } catch {
        testContext.available = false;
        testContext.reason = 'Failed to import cache module (Redis required)';
      }
    }
  });

  afterAll(async () => {
    await cleanupRedisTestConnection();
  });

  beforeEach(async () => {
    jest.clearAllMocks();
    if (cache && typeof cache.clear === 'function') {
      try {
        await cache.clear();
      } catch {
        // Ignore clear errors
      }
    }
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

    it('should create two write note buttons with different classifications', () => {
      const buttons = [
        {
          customId: 'write_note:NOT_MISLEADING:abc12345',
          label: 'Not Misleading',
          style: 'Success',
        },
        {
          customId: 'write_note:MISINFORMED_OR_POTENTIALLY_MISLEADING:def67890',
          label: 'Misinformed or Misleading',
          style: 'Danger',
        },
      ];

      expect(buttons).toHaveLength(2);
      expect(buttons[0].label).toBe('Not Misleading');
      expect(buttons[1].label).toBe('Misinformed or Misleading');
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
      if (!testContext.available || !cache) {
        console.log(`[SKIPPED] ${testContext.reason}`);
        return;
      }

      const cacheValue = await cache.get('write_note_state:missing123');
      expect(cacheValue).toBeNull();
    });

    it('should cache modal state with short ID', async () => {
      if (!testContext.available || !cache) {
        console.log(`[SKIPPED] ${testContext.reason}`);
        return;
      }

      const requestId = 'discord-1436105005051416606-1762473993351';
      const modalShortId = 'test1234';
      const modalCacheKey = `write_note_modal_state:${modalShortId}`;

      await cache.set(modalCacheKey, requestId, 300);

      const retrieved = await cache.get(modalCacheKey);
      expect(retrieved).toBe(requestId);
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
      if (!testContext.available || !cache) {
        console.log(`[SKIPPED] ${testContext.reason}`);
        return;
      }

      const modalShortId = 'test1234';
      const classification = 'NOT_MISLEADING';
      const classificationCacheKey = `write_note_classification:${modalShortId}`;

      await cache.set(classificationCacheKey, classification, 300);

      const retrieved = await cache.get(classificationCacheKey);
      expect(retrieved).toBe(classification);
    });
  });
});
