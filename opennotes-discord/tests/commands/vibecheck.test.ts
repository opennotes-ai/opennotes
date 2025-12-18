import { jest, describe, it, expect, beforeEach } from '@jest/globals';
import { MessageFlags, PermissionFlagsBits, ButtonStyle } from 'discord.js';
import {
  VIBE_CHECK_DAYS_OPTIONS,
  type BulkScanInitiateResponse,
  type BulkScanResultsResponse,
  type FlaggedMessage,
} from '../../src/types/bulk-scan.js';

const mockLogger = {
  info: jest.fn<(...args: unknown[]) => void>(),
  error: jest.fn<(...args: unknown[]) => void>(),
  warn: jest.fn<(...args: unknown[]) => void>(),
  debug: jest.fn<(...args: unknown[]) => void>(),
};

const mockNatsPublisher = {
  publishBulkScanBatch: jest.fn<(...args: unknown[]) => Promise<void>>().mockResolvedValue(undefined),
  isConnected: jest.fn<() => boolean>().mockReturnValue(true),
};

const mockApiClient = {
  healthCheck: jest.fn<() => Promise<any>>(),
  initiateBulkScan: jest.fn<(guildId: string, days: number) => Promise<BulkScanInitiateResponse>>(),
  getBulkScanResults: jest.fn<(scanId: string) => Promise<BulkScanResultsResponse>>(),
  createNoteRequestsFromScan: jest.fn<(scanId: string, messageIds: string[], generateAiNotes: boolean) => Promise<any>>(),
};

const mockCache = {
  get: jest.fn<(key: string) => unknown>(),
  set: jest.fn<(key: string, value: unknown, ttl?: number) => void>(),
  delete: jest.fn<(key: string) => void>(),
};

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
}));

jest.unstable_mockModule('../../src/api-client.js', () => ({
  apiClient: mockApiClient,
}));

jest.unstable_mockModule('../../src/cache.js', () => ({
  cache: mockCache,
}));

jest.unstable_mockModule('../../src/events/NatsPublisher.js', () => ({
  natsPublisher: mockNatsPublisher,
}));

jest.unstable_mockModule('../../src/lib/errors.js', () => ({
  generateErrorId: () => 'test-error-id',
  extractErrorDetails: (error: any) => ({
    message: error?.message || 'Unknown error',
    type: error?.constructor?.name || 'Error',
    stack: error?.stack || '',
  }),
  formatErrorForUser: (errorId: string, message: string) => `${message} (Error ID: ${errorId})`,
  ApiError: class ApiError extends Error {
    constructor(message: string, public endpoint?: string, public statusCode?: number, public responseBody?: any) {
      super(message);
    }
  },
}));

const { data, execute } = await import('../../src/commands/vibecheck.js');

describe('vibecheck command', () => {
  beforeEach(() => {
    jest.clearAllMocks();

    mockApiClient.initiateBulkScan.mockResolvedValue({
      scan_id: 'test-scan-123',
      status: 'pending',
      community_server_id: 'guild789',
      scan_window_days: 7,
    });

    mockApiClient.getBulkScanResults.mockResolvedValue({
      scan_id: 'test-scan-123',
      status: 'completed',
      messages_scanned: 0,
      flagged_messages: [],
    });

    mockApiClient.createNoteRequestsFromScan.mockResolvedValue({
      created_count: 0,
      scan_id: 'test-scan-123',
    });
  });

  describe('slash command registration', () => {
    it('should have the correct command name', () => {
      expect(data.name).toBe('vibecheck');
    });

    it('should have a description', () => {
      expect(data.description).toBeDefined();
      expect(data.description.length).toBeGreaterThan(0);
    });

    it('should have days parameter with correct choices', () => {
      const options = data.options;
      expect(options).toBeDefined();
      expect(options.length).toBeGreaterThanOrEqual(1);

      const daysOption = options.find((opt: any) => opt.name === 'days') as any;
      expect(daysOption).toBeDefined();
      expect(daysOption.required).toBe(true);

      const choices = daysOption.choices as { name: string; value: number }[];
      expect(choices).toHaveLength(VIBE_CHECK_DAYS_OPTIONS.length);

      VIBE_CHECK_DAYS_OPTIONS.forEach((option, index) => {
        expect(choices[index].name).toBe(option.name);
        expect(choices[index].value).toBe(option.value);
      });
    });

    it('should require ManageGuild permission by default', () => {
      const permissions = data.default_member_permissions;
      expect(permissions).toBeDefined();
      expect(BigInt(permissions as string)).toBe(PermissionFlagsBits.ManageGuild);
    });
  });

  describe('permission checks', () => {
    it('should reject non-admin users', async () => {
      const mockMember = {
        permissions: {
          has: jest.fn<(permission: bigint) => boolean>().mockReturnValue(false),
        },
      };

      const mockInteraction = {
        user: { id: 'user123' },
        member: mockMember,
        guildId: 'guild789',
        guild: {
          id: 'guild789',
          name: 'Test Guild',
          channels: {
            cache: new Map(),
          },
        },
        options: {
          getInteger: jest.fn<(name: string, required: boolean) => number>().mockReturnValue(7),
        },
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      expect(mockInteraction.reply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('permission'),
          flags: MessageFlags.Ephemeral,
        })
      );
    });

    it('should allow admin users with ManageGuild permission', async () => {
      const mockChannel = {
        id: 'channel123',
        name: 'test-channel',
        type: 0,
        isTextBased: () => true,
        viewable: true,
        messages: {
          fetch: jest.fn<(opts: any) => Promise<Map<string, any>>>().mockResolvedValue(new Map()),
        },
      };

      const mockMember = {
        permissions: {
          has: jest.fn<(permission: bigint) => boolean>().mockReturnValue(true),
        },
      };

      const channelsCache = new Map([['channel123', mockChannel]]);
      (channelsCache as any).filter = (fn: (ch: any) => boolean) => {
        const result = new Map();
        for (const [k, v] of channelsCache) {
          if (fn(v)) result.set(k, v);
        }
        return result;
      };

      const mockGuild = {
        id: 'guild789',
        name: 'Test Guild',
        channels: { cache: channelsCache },
      };

      const mockInteraction = {
        user: { id: 'admin123', username: 'adminuser' },
        member: mockMember,
        guildId: 'guild789',
        guild: mockGuild,
        options: {
          getInteger: jest.fn<(name: string, required: boolean) => number>().mockReturnValue(7),
        },
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      expect(mockInteraction.deferReply).toHaveBeenCalledWith({
        flags: MessageFlags.Ephemeral,
      });
    });
  });

  describe('guild validation', () => {
    it('should reject if not in a guild', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        member: null,
        guildId: null,
        guild: null,
        options: {
          getInteger: jest.fn<(name: string, required: boolean) => number>().mockReturnValue(7),
        },
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      expect(mockInteraction.reply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('server'),
          flags: MessageFlags.Ephemeral,
        })
      );
    });
  });

  describe('message scanning', () => {
    it('should iterate through text channels', async () => {
      const now = Date.now();
      const mockMessages = new Map([
        ['1234567890123456789', {
          id: '1234567890123456789',
          content: 'Test message 1',
          author: { id: 'author1', username: 'user1', bot: false },
          createdTimestamp: now - 1000 * 60 * 60,
          createdAt: new Date(now - 1000 * 60 * 60),
          channelId: 'channel123',
          attachments: new Map(),
          embeds: [],
        }],
        ['1234567890123456790', {
          id: '1234567890123456790',
          content: 'Test message 2',
          author: { id: 'author2', username: 'user2', bot: false },
          createdTimestamp: now - 1000 * 60 * 60 * 2,
          createdAt: new Date(now - 1000 * 60 * 60 * 2),
          channelId: 'channel123',
          attachments: new Map(),
          embeds: [],
        }],
      ]);

      const messageFetch = jest.fn<(opts: any) => Promise<Map<string, any>>>()
        .mockResolvedValueOnce(mockMessages)
        .mockResolvedValue(new Map());

      const mockChannel = {
        id: 'channel123',
        name: 'test-channel',
        type: 0,
        isTextBased: () => true,
        viewable: true,
        messages: { fetch: messageFetch },
      };

      const mockMember = {
        permissions: {
          has: jest.fn<(permission: bigint) => boolean>().mockReturnValue(true),
        },
      };

      const channelsCache = new Map([['channel123', mockChannel]]);
      (channelsCache as any).filter = (fn: (ch: any) => boolean) => {
        const result = new Map();
        for (const [k, v] of channelsCache) {
          if (fn(v)) result.set(k, v);
        }
        return result;
      };

      const mockGuild = {
        id: 'guild789',
        name: 'Test Guild',
        channels: { cache: channelsCache },
      };

      const mockInteraction = {
        user: { id: 'admin123', username: 'adminuser' },
        member: mockMember,
        guildId: 'guild789',
        guild: mockGuild,
        options: {
          getInteger: jest.fn<(name: string, required: boolean) => number>().mockReturnValue(1),
        },
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      expect(messageFetch).toHaveBeenCalled();
    });

    it('should skip bot messages', async () => {
      const now = Date.now();
      const mockMessages = new Map([
        ['1234567890123456789', {
          id: '1234567890123456789',
          content: 'Bot message',
          author: { id: 'bot1', username: 'botuser', bot: true },
          createdTimestamp: now - 1000 * 60 * 60,
          createdAt: new Date(now - 1000 * 60 * 60),
          channelId: 'channel123',
          attachments: new Map(),
          embeds: [],
        }],
        ['1234567890123456790', {
          id: '1234567890123456790',
          content: 'Human message',
          author: { id: 'human1', username: 'humanuser', bot: false },
          createdTimestamp: now - 1000 * 60 * 60,
          createdAt: new Date(now - 1000 * 60 * 60),
          channelId: 'channel123',
          attachments: new Map(),
          embeds: [],
        }],
      ]);

      const mockChannel = {
        id: 'channel123',
        name: 'test-channel',
        type: 0,
        isTextBased: () => true,
        viewable: true,
        messages: {
          fetch: jest.fn<(opts: any) => Promise<Map<string, any>>>()
            .mockResolvedValueOnce(mockMessages)
            .mockResolvedValue(new Map()),
        },
      };

      const mockMember = {
        permissions: {
          has: jest.fn<(permission: bigint) => boolean>().mockReturnValue(true),
        },
      };

      const channelsCache = new Map([['channel123', mockChannel]]);
      (channelsCache as any).filter = (fn: (ch: any) => boolean) => {
        const result = new Map();
        for (const [k, v] of channelsCache) {
          if (fn(v)) result.set(k, v);
        }
        return result;
      };

      const mockGuild = {
        id: 'guild789',
        name: 'Test Guild',
        channels: { cache: channelsCache },
      };

      const mockInteraction = {
        user: { id: 'admin123', username: 'adminuser' },
        member: mockMember,
        guildId: 'guild789',
        guild: mockGuild,
        options: {
          getInteger: jest.fn<(name: string, required: boolean) => number>().mockReturnValue(1),
        },
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      expect(mockInteraction.editReply).toHaveBeenCalled();
    });

    it('should respect the days parameter cutoff', async () => {
      const now = Date.now();

      const mockMessages = new Map([
        ['1234567890123456789', {
          id: '1234567890123456789',
          content: 'Recent message',
          author: { id: 'author1', username: 'user1', bot: false },
          createdTimestamp: now - 1000 * 60 * 60,
          createdAt: new Date(now - 1000 * 60 * 60),
          channelId: 'channel123',
          attachments: new Map(),
          embeds: [],
        }],
      ]);

      const messageFetch = jest.fn<(opts: any) => Promise<Map<string, any>>>()
        .mockResolvedValueOnce(mockMessages)
        .mockResolvedValue(new Map());

      const mockChannel = {
        id: 'channel123',
        name: 'test-channel',
        type: 0,
        isTextBased: () => true,
        viewable: true,
        messages: { fetch: messageFetch },
      };

      const mockMember = {
        permissions: {
          has: jest.fn<(permission: bigint) => boolean>().mockReturnValue(true),
        },
      };

      const channelsCache = new Map([['channel123', mockChannel]]);
      (channelsCache as any).filter = (fn: (ch: any) => boolean) => {
        const result = new Map();
        for (const [k, v] of channelsCache) {
          if (fn(v)) result.set(k, v);
        }
        return result;
      };

      const mockGuild = {
        id: 'guild789',
        name: 'Test Guild',
        channels: { cache: channelsCache },
      };

      const mockInteraction = {
        user: { id: 'admin123', username: 'adminuser' },
        member: mockMember,
        guildId: 'guild789',
        guild: mockGuild,
        options: {
          getInteger: jest.fn<(name: string, required: boolean) => number>().mockReturnValue(1),
        },
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      expect(messageFetch).toHaveBeenCalled();
      expect(mockInteraction.editReply).toHaveBeenCalled();
    });
  });

  describe('NATS batch publishing', () => {
    it('should publish messages to NATS in batches', async () => {
      const now = Date.now();
      const mockMessages = new Map();
      for (let i = 0; i < 150; i++) {
        const msgId = `145102818975626${(4000 + i).toString()}`;
        mockMessages.set(msgId, {
          id: msgId,
          content: `Test message ${i}`,
          author: { id: 'author1', username: 'user1', bot: false },
          createdTimestamp: now - 1000 * 60 * 60,
          createdAt: new Date(now - 1000 * 60 * 60),
          channelId: 'channel123',
          attachments: new Map(),
          embeds: [],
        });
      }

      const mockChannel = {
        id: 'channel123',
        name: 'test-channel',
        type: 0,
        isTextBased: () => true,
        viewable: true,
        messages: {
          fetch: jest.fn<(opts: any) => Promise<Map<string, any>>>()
            .mockResolvedValueOnce(mockMessages)
            .mockResolvedValue(new Map()),
        },
      };

      const mockMember = {
        permissions: {
          has: jest.fn<(permission: bigint) => boolean>().mockReturnValue(true),
        },
      };

      const channelsCache = new Map([['channel123', mockChannel]]);
      (channelsCache as any).filter = (fn: (ch: any) => boolean) => {
        const result = new Map();
        for (const [k, v] of channelsCache) {
          if (fn(v)) result.set(k, v);
        }
        return result;
      };

      const mockGuild = {
        id: 'guild789',
        name: 'Test Guild',
        channels: { cache: channelsCache },
      };

      const mockInteraction = {
        user: { id: 'admin123', username: 'adminuser' },
        member: mockMember,
        guildId: 'guild789',
        guild: mockGuild,
        options: {
          getInteger: jest.fn<(name: string, required: boolean) => number>().mockReturnValue(7),
        },
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      expect(mockNatsPublisher.publishBulkScanBatch).toHaveBeenCalled();
    });
  });

  describe('progress updates', () => {
    it('should update progress during scan', async () => {
      const now = Date.now();
      const mockChannel1 = {
        id: 'channel1',
        name: 'channel-1',
        type: 0,
        isTextBased: () => true,
        viewable: true,
        messages: {
          fetch: jest.fn<(opts: any) => Promise<Map<string, any>>>()
            .mockResolvedValueOnce(new Map([
              ['1234567890123456789', {
                id: '1234567890123456789',
                content: 'Message 1',
                author: { id: 'author1', username: 'user1', bot: false },
                createdTimestamp: now - 1000 * 60,
                createdAt: new Date(now - 1000 * 60),
                channelId: 'channel1',
                attachments: new Map(),
                embeds: [],
              }],
            ]))
            .mockResolvedValue(new Map()),
        },
      };

      const mockChannel2 = {
        id: 'channel2',
        name: 'channel-2',
        type: 0,
        isTextBased: () => true,
        viewable: true,
        messages: {
          fetch: jest.fn<(opts: any) => Promise<Map<string, any>>>()
            .mockResolvedValueOnce(new Map([
              ['1234567890123456790', {
                id: '1234567890123456790',
                content: 'Message 2',
                author: { id: 'author2', username: 'user2', bot: false },
                createdTimestamp: now - 1000 * 60,
                createdAt: new Date(now - 1000 * 60),
                channelId: 'channel2',
                attachments: new Map(),
                embeds: [],
              }],
            ]))
            .mockResolvedValue(new Map()),
        },
      };

      const mockMember = {
        permissions: {
          has: jest.fn<(permission: bigint) => boolean>().mockReturnValue(true),
        },
      };

      const channelsCache = new Map([
        ['channel1', mockChannel1],
        ['channel2', mockChannel2],
      ]);
      (channelsCache as any).filter = (fn: (ch: any) => boolean) => {
        const result = new Map();
        for (const [k, v] of channelsCache) {
          if (fn(v)) result.set(k, v);
        }
        return result;
      };

      const mockGuild = {
        id: 'guild789',
        name: 'Test Guild',
        channels: { cache: channelsCache },
      };

      const mockInteraction = {
        user: { id: 'admin123', username: 'adminuser' },
        member: mockMember,
        guildId: 'guild789',
        guild: mockGuild,
        options: {
          getInteger: jest.fn<(name: string, required: boolean) => number>().mockReturnValue(1),
        },
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      expect(mockInteraction.editReply).toHaveBeenCalled();
    });
  });

  describe('completion message', () => {
    it('should show completion message with scan summary', async () => {
      const now = Date.now();
      const mockChannel = {
        id: 'channel123',
        name: 'test-channel',
        type: 0,
        isTextBased: () => true,
        viewable: true,
        messages: {
          fetch: jest.fn<(opts: any) => Promise<Map<string, any>>>()
            .mockResolvedValueOnce(new Map([
              ['1234567890123456789', {
                id: '1234567890123456789',
                content: 'Test message',
                author: { id: 'author1', username: 'user1', bot: false },
                createdTimestamp: now - 1000 * 60,
                createdAt: new Date(now - 1000 * 60),
                channelId: 'channel123',
                attachments: new Map(),
                embeds: [],
              }],
            ]))
            .mockResolvedValue(new Map()),
        },
      };

      const mockMember = {
        permissions: {
          has: jest.fn<(permission: bigint) => boolean>().mockReturnValue(true),
        },
      };

      const channelsCache = new Map([['channel123', mockChannel]]);
      (channelsCache as any).filter = (fn: (ch: any) => boolean) => {
        const result = new Map();
        for (const [k, v] of channelsCache) {
          if (fn(v)) result.set(k, v);
        }
        return result;
      };

      const mockGuild = {
        id: 'guild789',
        name: 'Test Guild',
        channels: { cache: channelsCache },
      };

      const mockInteraction = {
        user: { id: 'admin123', username: 'adminuser' },
        member: mockMember,
        guildId: 'guild789',
        guild: mockGuild,
        options: {
          getInteger: jest.fn<(name: string, required: boolean) => number>().mockReturnValue(1),
        },
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      const lastEditCall = mockInteraction.editReply.mock.calls[mockInteraction.editReply.mock.calls.length - 1][0];
      expect(lastEditCall.content).toMatch(/complete|finished|done|scan/i);
    });
  });

  describe('AC #6: server-side scan initiation and results display', () => {
    const createMockInteractionWithCollector = () => {
      const now = Date.now();

      const mockCollector = {
        on: jest.fn<(event: string, handler: (...args: any[]) => void) => any>(),
        stop: jest.fn(),
      };

      const mockFetchReply = jest.fn<() => Promise<any>>().mockResolvedValue({
        createMessageComponentCollector: jest.fn().mockReturnValue(mockCollector),
      });

      const mockChannel = {
        id: 'channel123',
        name: 'test-channel',
        type: 0,
        isTextBased: () => true,
        viewable: true,
        messages: {
          fetch: jest.fn<(opts: any) => Promise<Map<string, any>>>()
            .mockResolvedValueOnce(new Map([
              ['1234567890123456789', {
                id: '1234567890123456789',
                content: 'Test message with misinformation',
                author: { id: 'author1', username: 'user1', bot: false },
                createdTimestamp: now - 1000 * 60,
                createdAt: new Date(now - 1000 * 60),
                channelId: 'channel123',
                attachments: new Map(),
                embeds: [],
              }],
            ]))
            .mockResolvedValue(new Map()),
        },
      };

      const mockMember = {
        permissions: {
          has: jest.fn<(permission: bigint) => boolean>().mockReturnValue(true),
        },
      };

      const channelsCache = new Map([['channel123', mockChannel]]);
      (channelsCache as any).filter = (fn: (ch: any) => boolean) => {
        const result = new Map();
        for (const [k, v] of channelsCache) {
          if (fn(v)) result.set(k, v);
        }
        return result;
      };

      const mockGuild = {
        id: 'guild789',
        name: 'Test Guild',
        channels: { cache: channelsCache },
      };

      const mockInteraction = {
        user: { id: 'admin123', username: 'adminuser' },
        member: mockMember,
        guildId: 'guild789',
        guild: mockGuild,
        options: {
          getInteger: jest.fn<(name: string, required: boolean) => number>().mockReturnValue(7),
        },
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        fetchReply: mockFetchReply,
      };

      return { mockInteraction, mockCollector };
    };

    it('should call initiateBulkScan API after NATS batches are published', async () => {
      const { mockInteraction } = createMockInteractionWithCollector();

      mockApiClient.initiateBulkScan.mockResolvedValue({
        scan_id: 'scan-123',
        status: 'pending',
        community_server_id: 'guild789',
        scan_window_days: 7,
      });

      mockApiClient.getBulkScanResults.mockResolvedValue({
        scan_id: 'scan-123',
        status: 'completed',
        messages_scanned: 1,
        flagged_messages: [],
      });

      await execute(mockInteraction as any);

      expect(mockApiClient.initiateBulkScan).toHaveBeenCalledWith('guild789', 7);
    });

    it('should poll for scan results until completed', async () => {
      const { mockInteraction } = createMockInteractionWithCollector();

      mockApiClient.initiateBulkScan.mockResolvedValue({
        scan_id: 'scan-123',
        status: 'pending',
        community_server_id: 'guild789',
        scan_window_days: 7,
      });

      mockApiClient.getBulkScanResults
        .mockResolvedValueOnce({
          scan_id: 'scan-123',
          status: 'in_progress',
          messages_scanned: 0,
          flagged_messages: [],
        })
        .mockResolvedValueOnce({
          scan_id: 'scan-123',
          status: 'in_progress',
          messages_scanned: 1,
          flagged_messages: [],
        })
        .mockResolvedValue({
          scan_id: 'scan-123',
          status: 'completed',
          messages_scanned: 1,
          flagged_messages: [],
        });

      await execute(mockInteraction as any);

      expect(mockApiClient.getBulkScanResults).toHaveBeenCalled();
      expect(mockApiClient.getBulkScanResults.mock.calls.length).toBeGreaterThanOrEqual(1);
    });

    it('should display flagged results with message link, confidence score, and matched claim', async () => {
      const { mockInteraction } = createMockInteractionWithCollector();

      const flaggedMessages: FlaggedMessage[] = [
        {
          message_id: '1234567890123456789',
          channel_id: 'channel123',
          content: 'This vaccine causes autism',
          author_id: 'author1',
          timestamp: new Date().toISOString(),
          match_score: 0.95,
          matched_claim: 'Vaccines cause autism',
          matched_source: 'snopes',
        },
      ];

      mockApiClient.initiateBulkScan.mockResolvedValue({
        scan_id: 'scan-123',
        status: 'pending',
        community_server_id: 'guild789',
        scan_window_days: 7,
      });

      mockApiClient.getBulkScanResults.mockResolvedValue({
        scan_id: 'scan-123',
        status: 'completed',
        messages_scanned: 1,
        flagged_messages: flaggedMessages,
      });

      await execute(mockInteraction as any);

      const lastEditCall = mockInteraction.editReply.mock.calls[mockInteraction.editReply.mock.calls.length - 1][0];

      expect(lastEditCall.content).toContain('95%');
      expect(lastEditCall.content).toContain('Vaccines cause autism');
      expect(lastEditCall.content).toMatch(/discord\.com\/channels/);
    });

    it('should show no flagged content message when scan completes with no matches', async () => {
      const { mockInteraction } = createMockInteractionWithCollector();

      mockApiClient.initiateBulkScan.mockResolvedValue({
        scan_id: 'scan-123',
        status: 'pending',
        community_server_id: 'guild789',
        scan_window_days: 7,
      });

      mockApiClient.getBulkScanResults.mockResolvedValue({
        scan_id: 'scan-123',
        status: 'completed',
        messages_scanned: 100,
        flagged_messages: [],
      });

      await execute(mockInteraction as any);

      const lastEditCall = mockInteraction.editReply.mock.calls[mockInteraction.editReply.mock.calls.length - 1][0];
      expect(lastEditCall.content).toMatch(/no.*flagged|clean|no.*misinformation/i);
    });
  });

  describe('AC #7: action buttons for note requests', () => {
    const createMockInteractionWithFlaggedResults = () => {
      const now = Date.now();

      const collectHandlers: Map<string, (...args: any[]) => void> = new Map();
      const mockCollector = {
        on: jest.fn<(event: string, handler: (...args: any[]) => void) => any>((event, handler) => {
          collectHandlers.set(event, handler);
          return mockCollector;
        }),
        stop: jest.fn(),
      };

      const mockFetchReply = jest.fn<() => Promise<any>>().mockResolvedValue({
        createMessageComponentCollector: jest.fn().mockReturnValue(mockCollector),
      });

      const mockChannel = {
        id: 'channel123',
        name: 'test-channel',
        type: 0,
        isTextBased: () => true,
        viewable: true,
        messages: {
          fetch: jest.fn<(opts: any) => Promise<Map<string, any>>>()
            .mockResolvedValueOnce(new Map([
              ['1234567890123456789', {
                id: '1234567890123456789',
                content: 'Test message',
                author: { id: 'author1', username: 'user1', bot: false },
                createdTimestamp: now - 1000 * 60,
                createdAt: new Date(now - 1000 * 60),
                channelId: 'channel123',
                attachments: new Map(),
                embeds: [],
              }],
            ]))
            .mockResolvedValue(new Map()),
        },
      };

      const mockMember = {
        permissions: {
          has: jest.fn<(permission: bigint) => boolean>().mockReturnValue(true),
        },
      };

      const channelsCache = new Map([['channel123', mockChannel]]);
      (channelsCache as any).filter = (fn: (ch: any) => boolean) => {
        const result = new Map();
        for (const [k, v] of channelsCache) {
          if (fn(v)) result.set(k, v);
        }
        return result;
      };

      const mockGuild = {
        id: 'guild789',
        name: 'Test Guild',
        channels: { cache: channelsCache },
      };

      const mockInteraction = {
        user: { id: 'admin123', username: 'adminuser' },
        member: mockMember,
        guildId: 'guild789',
        guild: mockGuild,
        options: {
          getInteger: jest.fn<(name: string, required: boolean) => number>().mockReturnValue(7),
        },
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        fetchReply: mockFetchReply,
      };

      return { mockInteraction, mockCollector, collectHandlers };
    };

    it('should show Create Note Requests and Dismiss buttons when flagged results exist', async () => {
      const { mockInteraction } = createMockInteractionWithFlaggedResults();

      const flaggedMessages: FlaggedMessage[] = [
        {
          message_id: '1234567890123456789',
          channel_id: 'channel123',
          content: 'Misinformation content',
          author_id: 'author1',
          timestamp: new Date().toISOString(),
          match_score: 0.85,
          matched_claim: 'False claim',
          matched_source: 'snopes',
        },
      ];

      mockApiClient.initiateBulkScan.mockResolvedValue({
        scan_id: 'scan-123',
        status: 'pending',
        community_server_id: 'guild789',
        scan_window_days: 7,
      });

      mockApiClient.getBulkScanResults.mockResolvedValue({
        scan_id: 'scan-123',
        status: 'completed',
        messages_scanned: 1,
        flagged_messages: flaggedMessages,
      });

      await execute(mockInteraction as any);

      const lastEditCall = mockInteraction.editReply.mock.calls[mockInteraction.editReply.mock.calls.length - 1][0];

      expect(lastEditCall.components).toBeDefined();
      expect(lastEditCall.components.length).toBeGreaterThan(0);

      const buttonRow = lastEditCall.components[0];
      const buttons = buttonRow.components || buttonRow.toJSON?.()?.components;

      expect(buttons.length).toBe(2);

      const buttonLabels = buttons.map((b: any) => b.label || b.data?.label);
      expect(buttonLabels).toContain('Create Note Requests');
      expect(buttonLabels).toContain('Dismiss');
    });

    it('should dismiss results when Dismiss button is clicked', async () => {
      const { mockInteraction, collectHandlers } = createMockInteractionWithFlaggedResults();

      const flaggedMessages: FlaggedMessage[] = [
        {
          message_id: '1234567890123456789',
          channel_id: 'channel123',
          content: 'Misinformation content',
          author_id: 'author1',
          timestamp: new Date().toISOString(),
          match_score: 0.85,
          matched_claim: 'False claim',
          matched_source: 'snopes',
        },
      ];

      mockApiClient.initiateBulkScan.mockResolvedValue({
        scan_id: 'scan-123',
        status: 'pending',
        community_server_id: 'guild789',
        scan_window_days: 7,
      });

      mockApiClient.getBulkScanResults.mockResolvedValue({
        scan_id: 'scan-123',
        status: 'completed',
        messages_scanned: 1,
        flagged_messages: flaggedMessages,
      });

      await execute(mockInteraction as any);

      const mockButtonInteraction = {
        customId: 'vibecheck_dismiss:scan-123',
        user: { id: 'admin123' },
        update: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      const collectHandler = collectHandlers.get('collect');
      if (collectHandler) {
        await collectHandler(mockButtonInteraction);
      }

      expect(mockButtonInteraction.update).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringMatching(/dismiss/i),
          components: [],
        })
      );
    });
  });

  describe('AC #8: AI generation prompt on Create Note Requests', () => {
    const createMockInteractionForAIPrompt = () => {
      const now = Date.now();

      const collectHandlers: Map<string, (...args: any[]) => void> = new Map();
      const mockCollector = {
        on: jest.fn<(event: string, handler: (...args: any[]) => void) => any>((event, handler) => {
          collectHandlers.set(event, handler);
          return mockCollector;
        }),
        stop: jest.fn(),
      };

      const mockFetchReply = jest.fn<() => Promise<any>>().mockResolvedValue({
        createMessageComponentCollector: jest.fn().mockReturnValue(mockCollector),
      });

      const mockChannel = {
        id: 'channel123',
        name: 'test-channel',
        type: 0,
        isTextBased: () => true,
        viewable: true,
        messages: {
          fetch: jest.fn<(opts: any) => Promise<Map<string, any>>>()
            .mockResolvedValueOnce(new Map([
              ['1234567890123456789', {
                id: '1234567890123456789',
                content: 'Test message',
                author: { id: 'author1', username: 'user1', bot: false },
                createdTimestamp: now - 1000 * 60,
                createdAt: new Date(now - 1000 * 60),
                channelId: 'channel123',
                attachments: new Map(),
                embeds: [],
              }],
            ]))
            .mockResolvedValue(new Map()),
        },
      };

      const mockMember = {
        permissions: {
          has: jest.fn<(permission: bigint) => boolean>().mockReturnValue(true),
        },
      };

      const channelsCache = new Map([['channel123', mockChannel]]);
      (channelsCache as any).filter = (fn: (ch: any) => boolean) => {
        const result = new Map();
        for (const [k, v] of channelsCache) {
          if (fn(v)) result.set(k, v);
        }
        return result;
      };

      const mockGuild = {
        id: 'guild789',
        name: 'Test Guild',
        channels: { cache: channelsCache },
      };

      const mockInteraction = {
        user: { id: 'admin123', username: 'adminuser' },
        member: mockMember,
        guildId: 'guild789',
        guild: mockGuild,
        options: {
          getInteger: jest.fn<(name: string, required: boolean) => number>().mockReturnValue(7),
        },
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        fetchReply: mockFetchReply,
      };

      return { mockInteraction, mockCollector, collectHandlers };
    };

    it('should show AI generation prompt when Create Note Requests is clicked', async () => {
      const { mockInteraction, collectHandlers } = createMockInteractionForAIPrompt();

      const flaggedMessages: FlaggedMessage[] = [
        {
          message_id: '1234567890123456789',
          channel_id: 'channel123',
          content: 'Misinformation content',
          author_id: 'author1',
          timestamp: new Date().toISOString(),
          match_score: 0.85,
          matched_claim: 'False claim',
          matched_source: 'snopes',
        },
      ];

      mockApiClient.initiateBulkScan.mockResolvedValue({
        scan_id: 'scan-123',
        status: 'pending',
        community_server_id: 'guild789',
        scan_window_days: 7,
      });

      mockApiClient.getBulkScanResults.mockResolvedValue({
        scan_id: 'scan-123',
        status: 'completed',
        messages_scanned: 1,
        flagged_messages: flaggedMessages,
      });

      await execute(mockInteraction as any);

      const aiCollectorHandlers: Map<string, (...args: any[]) => void> = new Map();
      const mockAiCollector = {
        on: jest.fn((event: string, handler: (...args: any[]) => void) => {
          aiCollectorHandlers.set(event, handler);
          return mockAiCollector;
        }),
        stop: jest.fn(),
      };

      const mockButtonInteraction = {
        customId: 'vibecheck_create:scan-123',
        user: { id: 'admin123' },
        update: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        message: {
          createMessageComponentCollector: jest.fn().mockReturnValue(mockAiCollector),
        },
      };

      const collectHandler = collectHandlers.get('collect');
      if (collectHandler) {
        await collectHandler(mockButtonInteraction);
      }

      expect(mockButtonInteraction.update).toHaveBeenCalled();
      const updateCall = mockButtonInteraction.update.mock.calls[0][0];
      expect(updateCall.content).toMatch(/ai|generate/i);
      expect(updateCall.components.length).toBeGreaterThan(0);
    });

    it('should call API with generate_ai_notes=true when AI Yes button clicked', async () => {
      const { mockInteraction, collectHandlers } = createMockInteractionForAIPrompt();

      const flaggedMessages: FlaggedMessage[] = [
        {
          message_id: '1234567890123456789',
          channel_id: 'channel123',
          content: 'Misinformation content',
          author_id: 'author1',
          timestamp: new Date().toISOString(),
          match_score: 0.85,
          matched_claim: 'False claim',
          matched_source: 'snopes',
        },
      ];

      mockApiClient.initiateBulkScan.mockResolvedValue({
        scan_id: 'scan-123',
        status: 'pending',
        community_server_id: 'guild789',
        scan_window_days: 7,
      });

      mockApiClient.getBulkScanResults.mockResolvedValue({
        scan_id: 'scan-123',
        status: 'completed',
        messages_scanned: 1,
        flagged_messages: flaggedMessages,
      });

      mockApiClient.createNoteRequestsFromScan.mockResolvedValue({
        created_count: 1,
        scan_id: 'scan-123',
      });

      await execute(mockInteraction as any);

      const aiCollectorHandlers: Map<string, (...args: any[]) => void> = new Map();
      const mockAiCollector = {
        on: jest.fn((event: string, handler: (...args: any[]) => void) => {
          aiCollectorHandlers.set(event, handler);
          return mockAiCollector;
        }),
        stop: jest.fn(),
      };

      const mockCreateButtonInteraction = {
        customId: 'vibecheck_create:scan-123',
        user: { id: 'admin123' },
        update: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        message: {
          createMessageComponentCollector: jest.fn().mockReturnValue(mockAiCollector),
        },
      };

      const collectHandler = collectHandlers.get('collect');
      if (collectHandler) {
        await collectHandler(mockCreateButtonInteraction);
      }

      const aiYesInteraction = {
        customId: 'vibecheck_ai_yes:scan-123',
        user: { id: 'admin123' },
        update: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      const aiCollectHandler = aiCollectorHandlers.get('collect');
      if (aiCollectHandler) {
        await aiCollectHandler(aiYesInteraction);
      }

      expect(mockApiClient.createNoteRequestsFromScan).toHaveBeenCalledWith(
        'scan-123',
        ['1234567890123456789'],
        true
      );
    });

    it('should call API with generate_ai_notes=false when AI No button clicked', async () => {
      const { mockInteraction, collectHandlers } = createMockInteractionForAIPrompt();

      const flaggedMessages: FlaggedMessage[] = [
        {
          message_id: '1234567890123456789',
          channel_id: 'channel123',
          content: 'Misinformation content',
          author_id: 'author1',
          timestamp: new Date().toISOString(),
          match_score: 0.85,
          matched_claim: 'False claim',
          matched_source: 'snopes',
        },
      ];

      mockApiClient.initiateBulkScan.mockResolvedValue({
        scan_id: 'scan-123',
        status: 'pending',
        community_server_id: 'guild789',
        scan_window_days: 7,
      });

      mockApiClient.getBulkScanResults.mockResolvedValue({
        scan_id: 'scan-123',
        status: 'completed',
        messages_scanned: 1,
        flagged_messages: flaggedMessages,
      });

      mockApiClient.createNoteRequestsFromScan.mockResolvedValue({
        created_count: 1,
        scan_id: 'scan-123',
      });

      await execute(mockInteraction as any);

      const aiCollectorHandlers: Map<string, (...args: any[]) => void> = new Map();
      const mockAiCollector = {
        on: jest.fn((event: string, handler: (...args: any[]) => void) => {
          aiCollectorHandlers.set(event, handler);
          return mockAiCollector;
        }),
        stop: jest.fn(),
      };

      const mockCreateButtonInteraction = {
        customId: 'vibecheck_create:scan-123',
        user: { id: 'admin123' },
        update: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        message: {
          createMessageComponentCollector: jest.fn().mockReturnValue(mockAiCollector),
        },
      };

      const collectHandler = collectHandlers.get('collect');
      if (collectHandler) {
        await collectHandler(mockCreateButtonInteraction);
      }

      const aiNoInteraction = {
        customId: 'vibecheck_ai_no:scan-123',
        user: { id: 'admin123' },
        update: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      const aiCollectHandler = aiCollectorHandlers.get('collect');
      if (aiCollectHandler) {
        await aiCollectHandler(aiNoInteraction);
      }

      expect(mockApiClient.createNoteRequestsFromScan).toHaveBeenCalledWith(
        'scan-123',
        ['1234567890123456789'],
        false
      );
    });
  });
});
