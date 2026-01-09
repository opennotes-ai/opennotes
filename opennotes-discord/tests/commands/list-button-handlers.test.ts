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

const mockApiClient = {
  rateNote: jest.fn<() => Promise<void>>(),
  forcePublishNote: jest.fn<() => Promise<any>>(),
  generateAiNote: jest.fn<() => Promise<any>>(),
  getCommunityServerByPlatformId: jest.fn<() => Promise<any>>(),
};

const mockListRequestsService = {
  execute: jest.fn<() => Promise<any>>(),
};

const mockServiceProvider = {
  getListRequestsService: jest.fn(() => mockListRequestsService),
  getWriteNoteService: jest.fn(),
};

class MockDiscordFormatter {
  static formatListRequestsSuccessV2 = jest.fn<() => Promise<any>>();
  static formatErrorV2 = jest.fn<() => any>();
}

jest.unstable_mockModule('../../src/cache.js', () => ({
  cache: mockCache,
}));

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
}));

jest.unstable_mockModule('../../src/api-client.js', () => ({
  apiClient: mockApiClient,
}));

jest.unstable_mockModule('../../src/services/index.js', () => ({
  serviceProvider: mockServiceProvider,
}));

jest.unstable_mockModule('../../src/services/DiscordFormatter.js', () => ({
  DiscordFormatter: MockDiscordFormatter,
}));

jest.unstable_mockModule('../../src/lib/errors.js', () => ({
  generateErrorId: () => 'test-error-id',
  extractErrorDetails: (error: any) => ({
    message: error?.message || 'Unknown error',
    type: error?.constructor?.name || 'Error',
    stack: error?.stack || '',
  }),
  formatErrorForUser: (message: string, errorId: string) => `${message}\n\nError ID: \`${errorId}\``,
  ApiError: class ApiError extends Error {
    constructor(
      message: string,
      public endpoint?: string,
      public statusCode?: number,
      public responseBody?: any
    ) {
      super(message);
    }
  },
}));

jest.unstable_mockModule('../../src/lib/validation.js', () => ({
  parseCustomId: (customId: string, expectedParts: number) => {
    const parts = customId.split(':');
    if (parts.length !== expectedParts) {
      return { success: false, error: 'Invalid parts count' };
    }
    return { success: true, parts };
  },
  generateShortId: () => 'test1234',
}));

jest.unstable_mockModule('../../src/lib/constants.js', () => ({
  LIST_COMMAND_LIMITS: {
    REQUESTS_PER_PAGE: 5,
    STATE_CACHE_TTL_SECONDS: 300,
  },
}));

jest.unstable_mockModule('../../src/lib/error-handler.js', () => ({
  classifyApiError: () => 'API_ERROR',
  getQueueErrorMessage: () => 'An error occurred while processing your request.',
}));

const {
  handleRateNoteButton,
  handleForcePublishButton,
  handleRequestQueuePageButton,
  handleWriteNoteButton,
  handleAiWriteNoteButton,
} = await import('../../src/commands/list.js');

function createMockButtonInteraction(customId: string, overrides: Record<string, any> = {}) {
  return {
    customId,
    user: {
      id: 'user123',
      username: 'testuser',
      displayName: 'Test User',
      avatarURL: () => 'https://example.com/avatar.png',
    },
    guildId: 'guild123',
    reply: jest.fn<() => Promise<any>>().mockResolvedValue({}),
    deferReply: jest.fn<() => Promise<any>>().mockResolvedValue({}),
    editReply: jest.fn<() => Promise<any>>().mockResolvedValue({}),
    update: jest.fn<() => Promise<any>>().mockResolvedValue({}),
    deferUpdate: jest.fn<() => Promise<any>>().mockResolvedValue({}),
    followUp: jest.fn<() => Promise<any>>().mockResolvedValue({}),
    showModal: jest.fn<() => Promise<any>>().mockResolvedValue({}),
    deferred: false,
    replied: false,
    ...overrides,
  };
}

describe('list command - Button Handlers', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    cacheStore.clear();
    setupCacheImplementations();
  });

  describe('handleRateNoteButton', () => {
    it('should rate note as helpful successfully', async () => {
      const interaction = createMockButtonInteraction('rate:note123:helpful');
      mockApiClient.rateNote.mockResolvedValue(undefined);

      await handleRateNoteButton(interaction as any);

      expect(interaction.deferReply).toHaveBeenCalledWith({ flags: MessageFlags.Ephemeral });
      expect(mockApiClient.rateNote).toHaveBeenCalledWith(
        {
          noteId: 'note123',
          userId: 'user123',
          helpful: true,
        },
        expect.objectContaining({
          userId: 'user123',
          username: 'testuser',
        })
      );
      expect(interaction.editReply).toHaveBeenCalledWith({
        content: expect.stringContaining('Helpful'),
      });
    });

    it('should rate note as not helpful successfully', async () => {
      const interaction = createMockButtonInteraction('rate:note456:not_helpful');
      mockApiClient.rateNote.mockResolvedValue(undefined);

      await handleRateNoteButton(interaction as any);

      expect(mockApiClient.rateNote).toHaveBeenCalledWith(
        {
          noteId: 'note456',
          userId: 'user123',
          helpful: false,
        },
        expect.any(Object)
      );
      expect(interaction.editReply).toHaveBeenCalledWith({
        content: expect.stringContaining('Not Helpful'),
      });
    });

    it('should handle invalid customId format', async () => {
      const interaction = createMockButtonInteraction('rate:invalid');

      await handleRateNoteButton(interaction as any);

      expect(interaction.reply).toHaveBeenCalledWith({
        content: 'Invalid button data. Please try again.',
        flags: MessageFlags.Ephemeral,
      });
      expect(mockApiClient.rateNote).not.toHaveBeenCalled();
    });

    it('should handle API error gracefully', async () => {
      const interaction = createMockButtonInteraction('rate:note123:helpful');
      interaction.deferReply.mockImplementation(async () => {
        interaction.deferred = true;
      });
      mockApiClient.rateNote.mockRejectedValue(new Error('API Error'));

      await handleRateNoteButton(interaction as any);

      expect(interaction.editReply).toHaveBeenCalledWith({
        content: expect.stringContaining('Failed to submit rating'),
      });
    });
  });

  describe('handleForcePublishButton', () => {
    it('should force publish note successfully', async () => {
      const interaction = createMockButtonInteraction('force_publish:note-uuid-123');
      mockApiClient.forcePublishNote.mockResolvedValue({});

      await handleForcePublishButton(interaction as any);

      expect(interaction.deferReply).toHaveBeenCalledWith({ flags: MessageFlags.Ephemeral });
      expect(mockApiClient.forcePublishNote).toHaveBeenCalledWith(
        'note-uuid-123',
        expect.objectContaining({
          userId: 'user123',
        })
      );
      expect(interaction.editReply).toHaveBeenCalledWith({
        content: expect.stringContaining('Note Force Published'),
      });
    });

    it('should handle invalid customId format', async () => {
      const interaction = createMockButtonInteraction('force_publish');

      await handleForcePublishButton(interaction as any);

      expect(interaction.reply).toHaveBeenCalledWith({
        content: 'Invalid button data. Please try again.',
        flags: MessageFlags.Ephemeral,
      });
      expect(mockApiClient.forcePublishNote).not.toHaveBeenCalled();
    });

    it('should handle API error gracefully', async () => {
      const interaction = createMockButtonInteraction('force_publish:note-uuid-123');
      interaction.deferReply.mockImplementation(async () => {
        interaction.deferred = true;
      });
      mockApiClient.forcePublishNote.mockRejectedValue(new Error('Permission denied'));

      await handleForcePublishButton(interaction as any);

      expect(interaction.editReply).toHaveBeenCalledWith({
        content: expect.stringContaining('Failed to force publish'),
      });
    });
  });

  describe('handleRequestQueuePageButton', () => {
    beforeEach(() => {
      mockServiceProvider.getListRequestsService.mockReturnValue(mockListRequestsService);
    });

    it('should navigate to next page successfully', async () => {
      const filterState = {
        status: 'PENDING',
        myRequestsOnly: false,
        communityServerId: 'community-uuid',
      };
      cacheStore.set('pagination:state123', filterState);

      const interaction = createMockButtonInteraction('request_queue_page:2:state123');

      mockListRequestsService.execute.mockResolvedValue({
        success: true,
        data: {
          requests: [],
          total: 10,
          page: 2,
          size: 5,
        },
      });

      MockDiscordFormatter.formatListRequestsSuccessV2.mockResolvedValue({
        components: [{ type: 17 }],
        flags: MessageFlags.IsComponentsV2,
      });

      await handleRequestQueuePageButton(interaction as any);

      expect(interaction.deferUpdate).toHaveBeenCalled();
      expect(mockListRequestsService.execute).toHaveBeenCalledWith({
        userId: 'user123',
        page: 2,
        size: 5,
        status: 'PENDING',
        myRequestsOnly: false,
        communityServerId: 'community-uuid',
      });
      expect(interaction.editReply).toHaveBeenCalled();
    });

    it('should handle expired pagination state', async () => {
      const interaction = createMockButtonInteraction('request_queue_page:2:expired123');

      await handleRequestQueuePageButton(interaction as any);

      expect(interaction.update).toHaveBeenCalledWith({
        content: 'Session expired. Please run `/list requests` again.',
        components: [],
      });
    });

    it('should handle invalid page number', async () => {
      const interaction = createMockButtonInteraction('request_queue_page:invalid:state123');

      await handleRequestQueuePageButton(interaction as any);

      expect(interaction.reply).toHaveBeenCalledWith({
        content: 'Invalid page number. Please run `/list requests` again.',
        flags: MessageFlags.Ephemeral,
      });
    });

    it('should handle invalid customId format', async () => {
      const interaction = createMockButtonInteraction('request_queue_page:2');

      await handleRequestQueuePageButton(interaction as any);

      expect(interaction.reply).toHaveBeenCalledWith({
        content: 'Invalid button data. Please run `/list requests` again.',
        flags: MessageFlags.Ephemeral,
      });
    });
  });

  describe('handleWriteNoteButton', () => {
    it('should show modal for NOT_MISLEADING classification', async () => {
      const requestId = 'request-uuid-123';
      cacheStore.set('write_note_state:short123', requestId);

      const interaction = createMockButtonInteraction('write_note:NOT_MISLEADING:short123');

      await handleWriteNoteButton(interaction as any);

      expect(mockCache.get).toHaveBeenCalledWith('write_note_state:short123');
      expect(interaction.showModal).toHaveBeenCalled();
    });

    it('should show modal for MISINFORMED classification', async () => {
      const requestId = 'request-uuid-456';
      cacheStore.set('write_note_state:short456', requestId);

      const interaction = createMockButtonInteraction(
        'write_note:MISINFORMED_OR_POTENTIALLY_MISLEADING:short456'
      );

      await handleWriteNoteButton(interaction as any);

      expect(interaction.showModal).toHaveBeenCalled();
    });

    it('should handle expired cache state', async () => {
      const interaction = createMockButtonInteraction('write_note:NOT_MISLEADING:expired1');

      await handleWriteNoteButton(interaction as any);

      expect(interaction.reply).toHaveBeenCalledWith({
        content: 'Button expired. Please run the /list requests command again.',
        flags: MessageFlags.Ephemeral,
      });
      expect(interaction.showModal).not.toHaveBeenCalled();
    });

    it('should handle invalid customId format', async () => {
      const interaction = createMockButtonInteraction('write_note:INVALID');

      await handleWriteNoteButton(interaction as any);

      expect(interaction.reply).toHaveBeenCalledWith({
        content: 'Invalid button data. Please try again.',
        flags: MessageFlags.Ephemeral,
      });
    });
  });

  describe('handleAiWriteNoteButton', () => {
    it('should generate AI note successfully', async () => {
      const requestId = 'request-uuid-789';
      cacheStore.set('write_note_state:ai12345', requestId);

      const interaction = createMockButtonInteraction('ai_write_note:ai12345');

      mockApiClient.generateAiNote.mockResolvedValue({
        data: {
          id: 'note-generated',
          attributes: {
            summary: 'AI generated note content',
          },
        },
      });

      await handleAiWriteNoteButton(interaction as any);

      expect(interaction.deferReply).toHaveBeenCalledWith({ flags: MessageFlags.Ephemeral });
      expect(mockApiClient.generateAiNote).toHaveBeenCalledWith(requestId, expect.any(Object));
      expect(interaction.editReply).toHaveBeenCalledWith({
        content: expect.stringContaining('AI Note Generated'),
      });
    });

    it('should handle expired cache state', async () => {
      const interaction = createMockButtonInteraction('ai_write_note:expired1');

      await handleAiWriteNoteButton(interaction as any);

      expect(interaction.reply).toHaveBeenCalledWith({
        content: 'Button expired. Please run the /list requests command again.',
        flags: MessageFlags.Ephemeral,
      });
      expect(mockApiClient.generateAiNote).not.toHaveBeenCalled();
    });

    it('should handle invalid customId format', async () => {
      const interaction = createMockButtonInteraction('ai_write_note');

      await handleAiWriteNoteButton(interaction as any);

      expect(interaction.reply).toHaveBeenCalledWith({
        content: 'Invalid button data. Please try again.',
        flags: MessageFlags.Ephemeral,
      });
    });

    it('should handle API error gracefully', async () => {
      const requestId = 'request-uuid-error';
      cacheStore.set('write_note_state:error123', requestId);

      const interaction = createMockButtonInteraction('ai_write_note:error123');
      interaction.deferReply.mockImplementation(async () => {
        interaction.deferred = true;
      });
      mockApiClient.generateAiNote.mockRejectedValue(new Error('AI service unavailable'));

      await handleAiWriteNoteButton(interaction as any);

      expect(interaction.editReply).toHaveBeenCalledWith({
        content: expect.stringContaining('Failed to generate AI note'),
      });
    });
  });
});
