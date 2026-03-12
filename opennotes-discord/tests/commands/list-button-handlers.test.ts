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
  handleViewFullButton,
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
      mockApiClient.forcePublishNote.mockResolvedValue({
        data: {
          type: 'notes',
          id: 'note-uuid-123',
          attributes: {
            summary: 'Short summary',
            status: 'PUBLISHED',
            force_published_at: new Date('2026-03-11T20:00:00Z').toISOString(),
            updated_at: new Date('2026-03-11T20:00:00Z').toISOString(),
            created_at: new Date('2026-03-11T20:00:00Z').toISOString(),
          },
        },
      });

      await handleForcePublishButton(interaction as any);

      expect(interaction.deferReply).toHaveBeenCalledWith({ flags: MessageFlags.Ephemeral });
      expect(mockApiClient.forcePublishNote).toHaveBeenCalledWith(
        'note-uuid-123',
        expect.objectContaining({
          userId: 'user123',
        })
      );
      expect(interaction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('Note #note-uuid-123 has been force-published'),
        })
      );
    });

    it('should reuse the note force-publish summary preview for long summaries', async () => {
      const interaction = createMockButtonInteraction('force_publish:note-uuid-123');
      const longSummary = 'S'.repeat(260);
      mockApiClient.forcePublishNote.mockResolvedValue({
        data: {
          type: 'notes',
          id: 'note-uuid-123',
          attributes: {
            summary: longSummary,
            status: 'PUBLISHED',
            force_published_at: new Date('2026-03-11T20:00:00Z').toISOString(),
            updated_at: new Date('2026-03-11T20:00:00Z').toISOString(),
            created_at: new Date('2026-03-11T20:00:00Z').toISOString(),
          },
        },
      });

      await handleForcePublishButton(interaction as any);

      const editReplyCall = (interaction.editReply as jest.Mock).mock.calls[0][0] as any;
      expect(editReplyCall.content).toContain('Note #note-uuid-123 has been force-published');
      expect(editReplyCall.content).toContain('Admin Published');
      expect(editReplyCall.content).toContain('**Note Summary:**');
      expect(editReplyCall.content).toContain('...');
      expect(editReplyCall.components).toBeDefined();
    });

    it('should fall back to the truncated summary preview when cache.set resolves false', async () => {
      const interaction = createMockButtonInteraction('force_publish:note-uuid-123');
      const longSummary = 'T'.repeat(260);
      mockCache.set.mockResolvedValueOnce(false);
      mockApiClient.forcePublishNote.mockResolvedValue({
        data: {
          type: 'notes',
          id: 'note-uuid-123',
          attributes: {
            summary: longSummary,
            status: 'PUBLISHED',
            force_published_at: new Date('2026-03-11T20:00:00Z').toISOString(),
            updated_at: new Date('2026-03-11T20:00:00Z').toISOString(),
            created_at: new Date('2026-03-11T20:00:00Z').toISOString(),
          },
        },
      });

      await handleForcePublishButton(interaction as any);

      const editReplyCall = (interaction.editReply as jest.Mock).mock.calls[0][0] as any;
      expect(editReplyCall.content).toContain('**Note Summary:**');
      expect(editReplyCall.content).toContain('...');
      expect(editReplyCall.components).toBeUndefined();
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

    it('should add a View Full button when AI note summary is truncated', async () => {
      const requestId = 'request-uuid-789';
      const longSummary = 'x'.repeat(260);
      cacheStore.set('write_note_state:ai12345', requestId);

      const interaction = createMockButtonInteraction('ai_write_note:ai12345');

      mockApiClient.generateAiNote.mockResolvedValue({
        data: {
          id: 'note-generated',
          attributes: {
            summary: longSummary,
          },
        },
      });

      await handleAiWriteNoteButton(interaction as any);

      expect(mockCache.set).toHaveBeenCalledWith(
        'view_full:test1234',
        longSummary,
        300
      );
      expect(interaction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          components: expect.any(Array),
        })
      );
    });

    it('should fall back to the truncated preview when storing View Full state fails', async () => {
      const requestId = 'request-uuid-cache-fail';
      const longSummary = 'y'.repeat(260);
      cacheStore.set('write_note_state:cachefail1', requestId);

      const interaction = createMockButtonInteraction('ai_write_note:cachefail1');
      mockCache.set.mockRejectedValueOnce(new Error('redis unavailable'));

      mockApiClient.generateAiNote.mockResolvedValue({
        data: {
          id: 'note-generated',
          attributes: {
            summary: longSummary,
          },
        },
      });

      await handleAiWriteNoteButton(interaction as any);

      expect(interaction.editReply).toHaveBeenCalledWith({
        content: expect.stringContaining('AI Note Generated'),
      });
      const editReplyCall = (interaction.editReply as any).mock.calls.at(-1) as any[] | undefined;
      expect(editReplyCall?.[0]?.components).toBeUndefined();
    });

    it('should fall back to the truncated preview when cache.set resolves false', async () => {
      const requestId = 'request-uuid-cache-false';
      const longSummary = 'z'.repeat(260);
      cacheStore.set('write_note_state:cachefalse', requestId);

      const interaction = createMockButtonInteraction('ai_write_note:cachefalse');
      mockCache.set.mockResolvedValueOnce(false);

      mockApiClient.generateAiNote.mockResolvedValue({
        data: {
          id: 'note-generated',
          attributes: {
            summary: longSummary,
          },
        },
      });

      await handleAiWriteNoteButton(interaction as any);

      expect(interaction.editReply).toHaveBeenCalledWith({
        content: expect.stringContaining('AI Note Generated'),
      });
      const editReplyCall = (interaction.editReply as any).mock.calls.at(-1) as any[] | undefined;
      expect(editReplyCall?.[0]?.components).toBeUndefined();
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

  describe('handleViewFullButton', () => {
    it('should reply with cached full note text', async () => {
      cacheStore.set('view_full:abc123', 'Full note text for expansion');
      const interaction = createMockButtonInteraction('view_full:abc123');

      await handleViewFullButton(interaction as any);

      expect(interaction.reply).toHaveBeenCalledWith({
        content: 'Full note text for expansion',
        flags: MessageFlags.Ephemeral,
      });
    });

    it('should split cached full note text across multiple ephemeral messages when over 2000 characters', async () => {
      const longFullText = 'A'.repeat(4500);
      cacheStore.set('view_full:chunked1', longFullText);
      const interaction = createMockButtonInteraction('view_full:chunked1');

      await handleViewFullButton(interaction as any);

      expect(interaction.reply).toHaveBeenCalledWith({
        content: 'A'.repeat(2000),
        flags: MessageFlags.Ephemeral,
      });
      expect(interaction.followUp).toHaveBeenNthCalledWith(1, {
        content: 'A'.repeat(2000),
        flags: MessageFlags.Ephemeral,
      });
      expect(interaction.followUp).toHaveBeenNthCalledWith(2, {
        content: 'A'.repeat(500),
        flags: MessageFlags.Ephemeral,
      });
    });

    it('should preserve fenced markdown integrity when paginating cached request previews', async () => {
      const fencedBody = Array.from(
        { length: 220 },
        (_, index) => `const line${index} = ${index};`
      ).join('\n');
      const longFullText = [
        'Request details:',
        '',
        '```ts',
        fencedBody,
        '```',
        '',
        'Follow-up context after the code block.',
      ].join('\n');
      cacheStore.set('view_full:fenced1', longFullText);
      const interaction = createMockButtonInteraction('view_full:fenced1');

      await handleViewFullButton(interaction as any);

      const replyCalls = interaction.reply.mock.calls as unknown as Array<[{ content: string }]>;
      const followUpCalls = interaction.followUp.mock.calls as unknown as Array<[{ content: string }]>;

      expect(replyCalls).toHaveLength(1);
      expect(followUpCalls.length).toBeGreaterThanOrEqual(1);

      const replyPayload = replyCalls[0][0];
      const followUpPayload = followUpCalls[0][0];
      const renderedPages = [replyPayload.content, ...followUpCalls.map(([payload]) => payload.content)];
      const renderedContent = renderedPages.join('\n');

      expect(replyPayload.content.match(/```/g)?.length ?? 0).toBeGreaterThanOrEqual(2);
      expect((replyPayload.content.match(/```/g)?.length ?? 0) % 2).toBe(0);
      expect((followUpPayload.content.match(/```/g)?.length ?? 0) % 2).toBe(0);
      renderedPages.forEach(page => {
        expect((page.match(/```/g)?.length ?? 0) % 2).toBe(0);
      });
      expect(renderedContent).toContain('const line219 = 219;');
      expect(renderedContent).toContain('Follow-up context after the code block.');
    });

    it('should preserve normalized quoted fenced markdown and blockquoted indented fence-like literals in View Full replies', async () => {
      const quotedFenceBody = Array.from(
        { length: 80 },
        (_, index) => `   > const quotedLine${index} = ${index};`
      ).join('\n');
      const longFullText = [
        '> Request details:',
        '>     ````',
        '>',
        '   > ```ts',
        quotedFenceBody,
        '>``` ',
        '>',
        '> Follow-up context after the quoted block.',
      ].join('\n');
      cacheStore.set('view_full:quotedfence1', longFullText);
      const interaction = createMockButtonInteraction('view_full:quotedfence1');

      await handleViewFullButton(interaction as any);

      const replyCalls = interaction.reply.mock.calls as unknown as Array<[{ content: string }]>;
      const followUpCalls = interaction.followUp.mock.calls as unknown as Array<[{ content: string }]>;
      const renderedPages = [replyCalls[0][0].content, ...followUpCalls.map(([payload]) => payload.content)];
      const renderedContent = renderedPages.join('\n');

      expect(renderedPages.length).toBeGreaterThan(1);
      expect(renderedPages[0].trimEnd().endsWith('   > ```')).toBe(true);
      expect(renderedPages[1].startsWith('   > ```ts\n')).toBe(true);
      expect(renderedContent).toContain('>     ````');
      expect(renderedContent).toContain('quotedLine79 = 79;');
      expect(renderedContent).toContain('> Follow-up context after the quoted block.');
    });

    it('should avoid emitting an empty reopened fence page in View Full replies when a split lands before the original closer', async () => {
      const fenceBody = Array.from(
        { length: 249 },
        (_, index) => `line${index.toString().padStart(3, '0')}`
      ).join('\n');
      const longFullText = [
        '```ts',
        fenceBody,
        '```',
        'tail',
      ].join('\n');
      cacheStore.set('view_full:closingfence1', longFullText);
      const interaction = createMockButtonInteraction('view_full:closingfence1');

      await handleViewFullButton(interaction as any);

      const replyCalls = interaction.reply.mock.calls as unknown as Array<[{ content: string }]>;
      const followUpCalls = interaction.followUp.mock.calls as unknown as Array<[{ content: string }]>;
      const renderedPages = [replyCalls[0][0].content, ...followUpCalls.map(([payload]) => payload.content)];

      expect(renderedPages.length).toBeGreaterThan(1);
      expect(renderedPages[1]).not.toContain('```ts\n```\n');
      expect(renderedPages[1]).toContain('line248');
      expect(renderedPages.join('\n')).toContain('tail');
    });

    it('should handle expired cache state', async () => {
      const interaction = createMockButtonInteraction('view_full:expired1');

      await handleViewFullButton(interaction as any);

      expect(interaction.reply).toHaveBeenCalledWith({
        content: 'Expanded content expired. Please run the command again.',
        flags: MessageFlags.Ephemeral,
      });
    });

    it('should handle invalid customId format', async () => {
      const interaction = createMockButtonInteraction('view_full');

      await handleViewFullButton(interaction as any);

      expect(interaction.reply).toHaveBeenCalledWith({
        content: 'Invalid button data. Please try again.',
        flags: MessageFlags.Ephemeral,
      });
    });
  });
});
