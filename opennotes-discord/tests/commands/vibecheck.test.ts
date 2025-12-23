import { jest, describe, it, expect, beforeEach } from '@jest/globals';
import { MessageFlags, PermissionFlagsBits, ButtonStyle } from 'discord.js';
import { VIBE_CHECK_DAYS_OPTIONS } from '../../src/types/bulk-scan.js';
import type { BulkScanResult } from '../../src/lib/bulk-scan-executor.js';
import type {
  LatestScanResponse,
  FlaggedMessageResource,
  CommunityServerJSONAPIResponse,
  NoteRequestsResultResponse,
} from '../../src/lib/api-client.js';

const mockLogger = {
  info: jest.fn<(...args: unknown[]) => void>(),
  error: jest.fn<(...args: unknown[]) => void>(),
  warn: jest.fn<(...args: unknown[]) => void>(),
  debug: jest.fn<(...args: unknown[]) => void>(),
};

function createFlaggedMessageResource(id: string, channelId: string, content: string, matchScore: number, matchedClaim: string): FlaggedMessageResource {
  return {
    type: 'flagged-messages',
    id,
    attributes: {
      channel_id: channelId,
      content,
      author_id: 'author1',
      timestamp: new Date().toISOString(),
      match_score: matchScore,
      matched_claim: matchedClaim,
      matched_source: 'snopes',
      scan_type: 'bulk',
    },
  };
}

function createLatestScanResponse(scanId: string, status: string, messagesScanned: number, flaggedMessages: FlaggedMessageResource[] = []): LatestScanResponse {
  return {
    data: {
      type: 'bulk-scans',
      id: scanId,
      attributes: {
        status,
        initiated_at: new Date().toISOString(),
        messages_scanned: messagesScanned,
        messages_flagged: flaggedMessages.length,
      },
    },
    included: flaggedMessages,
    jsonapi: { version: '1.1' },
  };
}

function createNoteRequestsResultResponse(createdCount: number, requestIds: string[] = []): NoteRequestsResultResponse {
  return {
    data: {
      type: 'note-request-batches',
      id: 'batch-123',
      attributes: {
        created_count: createdCount,
        request_ids: requestIds,
      },
    },
    jsonapi: { version: '1.1' },
  };
}

const mockApiClient = {
  healthCheck: jest.fn<() => Promise<any>>(),
  getCommunityServerByPlatformId: jest.fn<(platformId: string) => Promise<CommunityServerJSONAPIResponse>>(),
  initiateBulkScan: jest.fn<(guildId: string, days: number) => Promise<any>>(),
  getBulkScanResults: jest.fn<(scanId: string) => Promise<any>>(),
  createNoteRequestsFromScan: jest.fn<(scanId: string, messageIds: string[], generateAiNotes: boolean) => Promise<NoteRequestsResultResponse>>(),
  getLatestScan: jest.fn<(communityServerId: string) => Promise<LatestScanResponse>>(),
};

const mockCache = {
  get: jest.fn<(key: string) => unknown>(),
  set: jest.fn<(key: string, value: unknown, ttl?: number) => void>(),
  delete: jest.fn<(key: string) => void>(),
};

const mockExecuteBulkScan = jest.fn<(options: any) => Promise<BulkScanResult>>().mockResolvedValue({
  scanId: 'default-scan-123',
  messagesScanned: 0,
  channelsScanned: 0,
  batchesPublished: 0,
  failedBatches: 0,
  status: 'completed',
  flaggedMessages: [],
});

const mockBotChannelService = {
  findChannel: jest.fn<(guild: any, channelName: string) => any>(),
};

const mockGuildConfigService = {
  get: jest.fn<(guildId: string, key: string) => Promise<string>>(),
};

const mockServiceProvider = {
  getGuildConfigService: jest.fn(() => mockGuildConfigService),
};

jest.unstable_mockModule('../../src/types/bulk-scan.js', () => ({
  VIBE_CHECK_DAYS_OPTIONS: VIBE_CHECK_DAYS_OPTIONS,
  BULK_SCAN_BATCH_SIZE: 100,
  NATS_SUBJECTS: {
    BULK_SCAN_BATCH: 'OPENNOTES.bulk_scan_message_batch',
    BULK_SCAN_ALL_BATCHES_TRANSMITTED: 'OPENNOTES.bulk_scan_all_batches_transmitted',
    BULK_SCAN_RESULT: 'OPENNOTES.bulk_scan_results',
  },
  EventType: {
    BULK_SCAN_MESSAGE_BATCH: 'bulk_scan.message_batch',
    BULK_SCAN_ALL_BATCHES_TRANSMITTED: 'bulk_scan.all_batches_transmitted',
    BULK_SCAN_RESULTS: 'bulk_scan.results',
  },
}));

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
}));

jest.unstable_mockModule('../../src/api-client.js', () => ({
  apiClient: mockApiClient,
}));

jest.unstable_mockModule('../../src/cache.js', () => ({
  cache: mockCache,
}));

const mockNatsPublisher = {
  publishBulkScanBatch: jest.fn<(subject: string, batch: any) => Promise<void>>().mockResolvedValue(undefined),
  publishAllBatchesTransmitted: jest.fn<(data: any) => Promise<void>>().mockResolvedValue(undefined),
};

jest.unstable_mockModule('../../src/events/NatsPublisher.js', () => ({
  natsPublisher: mockNatsPublisher,
}));

jest.unstable_mockModule('../../src/lib/bulk-scan-executor.js', () => ({
  executeBulkScan: mockExecuteBulkScan,
  pollForResults: jest.fn(),
  formatMatchScore: (score: number) => `${Math.round(score * 100)}%`,
  formatMessageLink: (guildId: string, channelId: string, messageId: string) =>
    `https://discord.com/channels/${guildId}/${channelId}/${messageId}`,
  truncateContent: (content: string, maxLength: number = 100) => {
    if (content.length <= maxLength) return content;
    return content.slice(0, maxLength - 3) + '...';
  },
  POLL_TIMEOUT_MS: 60000,
  BACKOFF_INITIAL_MS: 1000,
  BACKOFF_MULTIPLIER: 2,
  BACKOFF_MAX_MS: 30000,
}));

const mockFormatScanStatus = jest.fn<(options: any) => { content: string; components?: any[] }>();

jest.unstable_mockModule('../../src/lib/scan-status-formatter.js', () => ({
  formatScanStatus: mockFormatScanStatus,
}));

const MockBotChannelServiceConstructor = jest.fn().mockImplementation(() => mockBotChannelService);

jest.unstable_mockModule('../../src/services/BotChannelService.js', () => ({
  BotChannelService: MockBotChannelServiceConstructor,
}));

jest.unstable_mockModule('../../src/services/index.js', () => ({
  serviceProvider: mockServiceProvider,
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

jest.unstable_mockModule('../../src/lib/permissions.js', () => ({
  hasManageGuildPermission: (member: any) => {
    if (!member) return false;
    return member.permissions?.has?.(BigInt(0x20)) ?? false;
  },
}));

jest.unstable_mockModule('../../src/lib/config-schema.js', () => ({
  ConfigKey: {
    BOT_CHANNEL_NAME: 'bot_channel_name',
    CONTENT_MONITOR_ENABLED: 'content_monitor_enabled',
    NOTE_PUBLISHER_ENABLED: 'note_publisher_enabled',
    LLM_PROVIDER: 'llm_provider',
  },
}));

const { data, execute, VIBECHECK_COOLDOWN_MS, getVibecheckCooldownKey } = await import('../../src/commands/vibecheck.js');

describe('vibecheck command', () => {
  beforeEach(() => {
    jest.clearAllMocks();

    // Set up cache mock to return null (no cooldown)
    mockCache.get.mockReturnValue(null);

    mockApiClient.getCommunityServerByPlatformId.mockResolvedValue({
      data: {
        type: 'community-servers',
        id: 'community-server-uuid-123',
        attributes: {
          platform: 'discord',
          platform_id: 'guild789',
          name: 'Test Server',
          is_active: true,
          is_public: true,
        },
      },
      jsonapi: { version: '1.1' },
    });

    mockApiClient.getLatestScan.mockResolvedValue(
      createLatestScanResponse('test-scan-123', 'completed', 100)
    );

    mockApiClient.createNoteRequestsFromScan.mockResolvedValue(
      createNoteRequestsResultResponse(0)
    );

    mockExecuteBulkScan.mockResolvedValue({
      scanId: 'test-scan-123',
      messagesScanned: 100,
      channelsScanned: 5,
      batchesPublished: 2,
      failedBatches: 0,
      status: 'completed',
      flaggedMessages: [],
    });

    MockBotChannelServiceConstructor.mockImplementation(() => mockBotChannelService);
    mockServiceProvider.getGuildConfigService.mockReturnValue(mockGuildConfigService);
    mockGuildConfigService.get.mockResolvedValue('opennotes');
    mockBotChannelService.findChannel.mockReturnValue(undefined);

    mockFormatScanStatus.mockReturnValue({
      content: '**Scan Complete**\n\n**Scan ID:** `test-scan-123`\n**Messages scanned:** 100\n\nNo potential misinformation was detected.',
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

    it('should have scan and status subcommands', () => {
      const options = data.options;
      expect(options).toBeDefined();
      expect(options.length).toBe(2);

      const subcommandNames = options.map((opt: any) => opt.name);
      expect(subcommandNames).toContain('scan');
      expect(subcommandNames).toContain('status');
    });

    it('should have days parameter on scan subcommand with correct choices', () => {
      const options = data.options;
      const scanSubcommand = options.find((opt: any) => opt.name === 'scan') as any;

      expect(scanSubcommand).toBeDefined();

      const daysOption = scanSubcommand.options?.find((opt: any) => opt.name === 'days') as any;
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
          getSubcommand: jest.fn().mockReturnValue('scan'),
          getSubcommandGroup: jest.fn().mockReturnValue(null),
          getChannel: jest.fn().mockReturnValue(null),
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
      const mockMember = {
        permissions: {
          has: jest.fn<(permission: bigint) => boolean>().mockReturnValue(true),
        },
      };

      const channelsCache = new Map();
      (channelsCache as any).filter = () => new Map();

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
          getSubcommand: jest.fn().mockReturnValue('scan'),
          getSubcommandGroup: jest.fn().mockReturnValue(null),
          getChannel: jest.fn().mockReturnValue(null),
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
          getSubcommand: jest.fn().mockReturnValue('scan'),
          getSubcommandGroup: jest.fn().mockReturnValue(null),
          getChannel: jest.fn().mockReturnValue(null),
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

  describe('scan subcommand', () => {
    it('should call executeBulkScan with correct parameters', async () => {
      const mockMember = {
        permissions: {
          has: jest.fn<(permission: bigint) => boolean>().mockReturnValue(true),
        },
      };

      const channelsCache = new Map();
      (channelsCache as any).filter = () => new Map();

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
          getSubcommand: jest.fn().mockReturnValue('scan'),
          getSubcommandGroup: jest.fn().mockReturnValue(null),
          getChannel: jest.fn().mockReturnValue(null),
        },
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      expect(mockExecuteBulkScan).toHaveBeenCalledWith(
        expect.objectContaining({
          guild: mockGuild,
          days: 7,
          initiatorId: 'admin123',
        })
      );
    });

    it('should show no channels message when no accessible channels found', async () => {
      const mockMember = {
        permissions: {
          has: jest.fn<(permission: bigint) => boolean>().mockReturnValue(true),
        },
      };

      const channelsCache = new Map();
      (channelsCache as any).filter = () => new Map();

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
          getSubcommand: jest.fn().mockReturnValue('scan'),
          getSubcommandGroup: jest.fn().mockReturnValue(null),
          getChannel: jest.fn().mockReturnValue(null),
        },
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      mockExecuteBulkScan.mockResolvedValueOnce({
        scanId: '',
        messagesScanned: 0,
        channelsScanned: 0,
        batchesPublished: 0,
        failedBatches: 0,
        status: 'completed',
        flaggedMessages: [],
      });

      await execute(mockInteraction as any);

      const lastEditCall = mockInteraction.editReply.mock.calls[mockInteraction.editReply.mock.calls.length - 1][0];
      expect(lastEditCall.content).toMatch(/no.*channel/i);
    });

    it('should show completion message with scan summary', async () => {
      const mockMember = {
        permissions: {
          has: jest.fn<(permission: bigint) => boolean>().mockReturnValue(true),
        },
      };

      const channelsCache = new Map();
      (channelsCache as any).filter = () => new Map();

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
          getSubcommand: jest.fn().mockReturnValue('scan'),
          getSubcommandGroup: jest.fn().mockReturnValue(null),
          getChannel: jest.fn().mockReturnValue(null),
        },
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      mockExecuteBulkScan.mockResolvedValueOnce({
        scanId: 'test-scan-123',
        messagesScanned: 50,
        channelsScanned: 3,
        batchesPublished: 1,
        failedBatches: 0,
        status: 'completed',
        flaggedMessages: [],
      });

      await execute(mockInteraction as any);

      const lastEditCall = mockInteraction.editReply.mock.calls[mockInteraction.editReply.mock.calls.length - 1][0];
      expect(lastEditCall.content).toMatch(/complete|scan/i);
    });
  });

  describe('scan results display', () => {
    const createMockInteractionWithCollector = () => {
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

      const mockMember = {
        permissions: {
          has: jest.fn<(permission: bigint) => boolean>().mockReturnValue(true),
        },
      };

      const channelsCache = new Map();
      (channelsCache as any).filter = () => new Map();

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
          getSubcommand: jest.fn().mockReturnValue('scan'),
          getSubcommandGroup: jest.fn().mockReturnValue(null),
          getChannel: jest.fn().mockReturnValue(null),
        },
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        fetchReply: mockFetchReply,
      };

      return { mockInteraction, mockCollector, collectHandlers };
    };

    it('should display flagged results with message link, confidence score, and matched claim', async () => {
      const { mockInteraction } = createMockInteractionWithCollector();

      const flaggedMessages: FlaggedMessageResource[] = [
        createFlaggedMessageResource('1234567890123456789', 'channel123', 'This vaccine causes autism', 0.95, 'Vaccines cause autism'),
      ];

      mockExecuteBulkScan.mockResolvedValueOnce({
        scanId: 'scan-123',
        messagesScanned: 100,
        channelsScanned: 5,
        batchesPublished: 2,
        failedBatches: 0,
        status: 'completed',
        flaggedMessages: flaggedMessages,
      });

      mockFormatScanStatus.mockReturnValueOnce({
        content: '**Scan Complete**\n\n**Flagged:** 1\n\n[Message](https://discord.com/channels/guild789/channel123/1234567890123456789)\nConfidence: **95%**\nMatched: "Vaccines cause autism"',
        components: [],
      });

      await execute(mockInteraction as any);

      const lastEditCall = mockInteraction.editReply.mock.calls[mockInteraction.editReply.mock.calls.length - 1][0];

      expect(lastEditCall.content).toContain('95%');
      expect(lastEditCall.content).toContain('Vaccines cause autism');
      expect(lastEditCall.content).toMatch(/discord\.com\/channels/);
    });

    it('should show no flagged content message when scan completes with no matches', async () => {
      const { mockInteraction } = createMockInteractionWithCollector();

      mockExecuteBulkScan.mockResolvedValueOnce({
        scanId: 'scan-123',
        messagesScanned: 100,
        channelsScanned: 5,
        batchesPublished: 2,
        failedBatches: 0,
        status: 'completed',
        flaggedMessages: [],
      });

      await execute(mockInteraction as any);

      const lastEditCall = mockInteraction.editReply.mock.calls[mockInteraction.editReply.mock.calls.length - 1][0];
      expect(lastEditCall.content).toMatch(/no.*flagged|no.*misinformation/i);
    });
  });

  describe('action buttons for note requests', () => {
    const createMockInteractionWithFlaggedResults = () => {
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

      const mockMember = {
        permissions: {
          has: jest.fn<(permission: bigint) => boolean>().mockReturnValue(true),
        },
      };

      const channelsCache = new Map();
      (channelsCache as any).filter = () => new Map();

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
          getSubcommand: jest.fn().mockReturnValue('scan'),
          getSubcommandGroup: jest.fn().mockReturnValue(null),
          getChannel: jest.fn().mockReturnValue(null),
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

      const flaggedMessages: FlaggedMessageResource[] = [
        createFlaggedMessageResource('1234567890123456789', 'channel123', 'Misinformation content', 0.85, 'False claim'),
      ];

      mockExecuteBulkScan.mockResolvedValueOnce({
        scanId: 'scan-123',
        messagesScanned: 100,
        channelsScanned: 5,
        batchesPublished: 2,
        failedBatches: 0,
        status: 'completed',
        flaggedMessages: flaggedMessages,
      });

      const mockButtonRow = {
        components: [
          { data: { custom_id: 'vibecheck_create:scan-123', label: 'Create Note Requests', style: ButtonStyle.Primary } },
          { data: { custom_id: 'vibecheck_dismiss:scan-123', label: 'Dismiss', style: ButtonStyle.Secondary } },
        ],
      };

      mockFormatScanStatus.mockReturnValueOnce({
        content: '**Scan Complete**\n\n**Flagged:** 1',
        components: [mockButtonRow],
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

      const flaggedMessages: FlaggedMessageResource[] = [
        createFlaggedMessageResource('1234567890123456789', 'channel123', 'Misinformation content', 0.85, 'False claim'),
      ];

      mockExecuteBulkScan.mockResolvedValueOnce({
        scanId: 'scan-123',
        messagesScanned: 100,
        channelsScanned: 5,
        batchesPublished: 2,
        failedBatches: 0,
        status: 'completed',
        flaggedMessages: flaggedMessages,
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

  describe('AI generation prompt on Create Note Requests', () => {
    const createMockInteractionForAIPrompt = () => {
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

      const mockMember = {
        permissions: {
          has: jest.fn<(permission: bigint) => boolean>().mockReturnValue(true),
        },
      };

      const channelsCache = new Map();
      (channelsCache as any).filter = () => new Map();

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
          getSubcommand: jest.fn().mockReturnValue('scan'),
          getSubcommandGroup: jest.fn().mockReturnValue(null),
          getChannel: jest.fn().mockReturnValue(null),
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

      const flaggedMessages: FlaggedMessageResource[] = [
        createFlaggedMessageResource('1234567890123456789', 'channel123', 'Misinformation content', 0.85, 'False claim'),
      ];

      mockExecuteBulkScan.mockResolvedValueOnce({
        scanId: 'scan-123',
        messagesScanned: 100,
        channelsScanned: 5,
        batchesPublished: 2,
        failedBatches: 0,
        status: 'completed',
        flaggedMessages: flaggedMessages,
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

      const flaggedMessages: FlaggedMessageResource[] = [
        createFlaggedMessageResource('1234567890123456789', 'channel123', 'Misinformation content', 0.85, 'False claim'),
      ];

      mockExecuteBulkScan.mockResolvedValueOnce({
        scanId: 'scan-123',
        messagesScanned: 100,
        channelsScanned: 5,
        batchesPublished: 2,
        failedBatches: 0,
        status: 'completed',
        flaggedMessages: flaggedMessages,
      });

      mockApiClient.createNoteRequestsFromScan.mockResolvedValue(
        createNoteRequestsResultResponse(1)
      );

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

      await new Promise(resolve => setTimeout(resolve, 10));

      expect(mockApiClient.createNoteRequestsFromScan).toHaveBeenCalledWith(
        'scan-123',
        ['1234567890123456789'],
        true
      );
    });

    it('should call API with generate_ai_notes=false when AI No button clicked', async () => {
      const { mockInteraction, collectHandlers } = createMockInteractionForAIPrompt();

      const flaggedMessages: FlaggedMessageResource[] = [
        createFlaggedMessageResource('1234567890123456789', 'channel123', 'Misinformation content', 0.85, 'False claim'),
      ];

      mockExecuteBulkScan.mockResolvedValueOnce({
        scanId: 'scan-123',
        messagesScanned: 100,
        channelsScanned: 5,
        batchesPublished: 2,
        failedBatches: 0,
        status: 'completed',
        flaggedMessages: flaggedMessages,
      });

      mockApiClient.createNoteRequestsFromScan.mockResolvedValue(
        createNoteRequestsResultResponse(1)
      );

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

      await new Promise(resolve => setTimeout(resolve, 10));

      expect(mockApiClient.createNoteRequestsFromScan).toHaveBeenCalledWith(
        'scan-123',
        ['1234567890123456789'],
        false
      );
    });
  });

  describe('User ID authorization for button collectors', () => {
    const createMockInteractionForUserIdTest = () => {
      let capturedFilter: ((interaction: any) => boolean) | undefined;

      const collectHandlers: Map<string, (...args: any[]) => void> = new Map();
      const mockCollector = {
        on: jest.fn<(event: string, handler: (...args: any[]) => void) => any>((event, handler) => {
          collectHandlers.set(event, handler);
          return mockCollector;
        }),
        stop: jest.fn(),
      };

      const mockFetchReply = jest.fn<() => Promise<any>>().mockResolvedValue({
        createMessageComponentCollector: jest.fn((options: any) => {
          capturedFilter = options?.filter;
          return mockCollector;
        }),
      });

      const mockMember = {
        permissions: {
          has: jest.fn<(permission: bigint) => boolean>().mockReturnValue(true),
        },
      };

      const channelsCache = new Map();
      (channelsCache as any).filter = () => new Map();

      const mockGuild = {
        id: 'guild789',
        name: 'Test Guild',
        channels: { cache: channelsCache },
      };

      const originalUserId = 'admin123';

      const mockInteraction = {
        user: { id: originalUserId, username: 'adminuser' },
        member: mockMember,
        guildId: 'guild789',
        guild: mockGuild,
        options: {
          getInteger: jest.fn<(name: string, required: boolean) => number>().mockReturnValue(7),
          getSubcommand: jest.fn().mockReturnValue('scan'),
          getSubcommandGroup: jest.fn().mockReturnValue(null),
          getChannel: jest.fn().mockReturnValue(null),
        },
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        fetchReply: mockFetchReply,
      };

      return { mockInteraction, mockCollector, collectHandlers, getCapturedFilter: () => capturedFilter, originalUserId };
    };

    describe('main button collector (Create/Dismiss)', () => {
      it('should filter button interactions by original user ID', async () => {
        const { mockInteraction, getCapturedFilter, originalUserId } = createMockInteractionForUserIdTest();

        const flaggedMessages: FlaggedMessageResource[] = [
          createFlaggedMessageResource('1234567890123456789', 'channel123', 'Misinformation content', 0.85, 'False claim'),
        ];

        mockExecuteBulkScan.mockResolvedValueOnce({
          scanId: 'scan-123',
          messagesScanned: 100,
          channelsScanned: 5,
          batchesPublished: 2,
          failedBatches: 0,
          status: 'completed',
          flaggedMessages: flaggedMessages,
        });

        await execute(mockInteraction as any);

        const filter = getCapturedFilter();
        expect(filter).toBeDefined();

        const originalUserInteraction = {
          user: { id: originalUserId },
          customId: 'vibecheck_dismiss:scan-123',
        };
        expect(filter!(originalUserInteraction)).toBe(true);

        const differentUserInteraction = {
          user: { id: 'different-user-456' },
          customId: 'vibecheck_dismiss:scan-123',
        };
        expect(filter!(differentUserInteraction)).toBe(false);
      });

      it('should allow original user to dismiss results', async () => {
        const { mockInteraction, collectHandlers, getCapturedFilter, originalUserId } = createMockInteractionForUserIdTest();

        const flaggedMessages: FlaggedMessageResource[] = [
          createFlaggedMessageResource('1234567890123456789', 'channel123', 'Misinformation content', 0.85, 'False claim'),
        ];

        mockExecuteBulkScan.mockResolvedValueOnce({
          scanId: 'scan-123',
          messagesScanned: 100,
          channelsScanned: 5,
          batchesPublished: 2,
          failedBatches: 0,
          status: 'completed',
          flaggedMessages: flaggedMessages,
        });

        await execute(mockInteraction as any);

        const filter = getCapturedFilter();
        expect(filter).toBeDefined();

        const originalUserInteraction = {
          customId: 'vibecheck_dismiss:scan-123',
          user: { id: originalUserId },
          update: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
          reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        };

        expect(filter!(originalUserInteraction)).toBe(true);

        const collectHandler = collectHandlers.get('collect');
        if (collectHandler) {
          await collectHandler(originalUserInteraction);
        }

        expect(originalUserInteraction.update).toHaveBeenCalledWith(
          expect.objectContaining({
            content: expect.stringMatching(/dismiss/i),
            components: [],
          })
        );
      });
    });

    describe('AI generation button collector', () => {
      it('should filter AI button interactions by original user ID', async () => {
        const { mockInteraction, collectHandlers, originalUserId } = createMockInteractionForUserIdTest();

        const flaggedMessages: FlaggedMessageResource[] = [
          createFlaggedMessageResource('1234567890123456789', 'channel123', 'Misinformation content', 0.85, 'False claim'),
        ];

        mockExecuteBulkScan.mockResolvedValueOnce({
          scanId: 'scan-123',
          messagesScanned: 100,
          channelsScanned: 5,
          batchesPublished: 2,
          failedBatches: 0,
          status: 'completed',
          flaggedMessages: flaggedMessages,
        });

        await execute(mockInteraction as any);

        let capturedAiFilter: ((interaction: any) => boolean) | undefined;
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
          user: { id: originalUserId },
          update: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
          message: {
            createMessageComponentCollector: jest.fn((options: any) => {
              capturedAiFilter = options?.filter;
              return mockAiCollector;
            }),
          },
        };

        const collectHandler = collectHandlers.get('collect');
        if (collectHandler) {
          await collectHandler(mockCreateButtonInteraction);
        }

        expect(capturedAiFilter).toBeDefined();

        const originalUserAiInteraction = {
          user: { id: originalUserId },
          customId: 'vibecheck_ai_yes:scan-123',
        };
        expect(capturedAiFilter!(originalUserAiInteraction)).toBe(true);

        const differentUserAiInteraction = {
          user: { id: 'unauthorized-user-789' },
          customId: 'vibecheck_ai_yes:scan-123',
        };
        expect(capturedAiFilter!(differentUserAiInteraction)).toBe(false);
      });
    });
  });

  describe('per-guild cooldown', () => {
    it('should export cooldown constant', () => {
      expect(VIBECHECK_COOLDOWN_MS).toBe(5 * 60 * 1000);
    });

    it('should generate correct cooldown key format', () => {
      const key = getVibecheckCooldownKey('guild123');
      expect(key).toBe('vibecheck:cooldown:guild123');
    });

    it('should reject scan if guild is in cooldown period', async () => {
      const mockMember = {
        permissions: {
          has: jest.fn<(permission: bigint) => boolean>().mockReturnValue(true),
        },
      };

      const channelsCache = new Map();
      (channelsCache as any).filter = () => new Map();

      const mockGuild = {
        id: 'guild-cooldown-test',
        name: 'Test Guild',
        channels: { cache: channelsCache },
      };

      const mockInteraction = {
        user: { id: 'admin123', username: 'adminuser' },
        member: mockMember,
        guildId: 'guild-cooldown-test',
        guild: mockGuild,
        options: {
          getInteger: jest.fn<(name: string, required: boolean) => number>().mockReturnValue(7),
          getSubcommand: jest.fn().mockReturnValue('scan'),
          getSubcommandGroup: jest.fn().mockReturnValue(null),
          getChannel: jest.fn().mockReturnValue(null),
        },
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      mockCache.get.mockReturnValue(Date.now() - 60000);

      await execute(mockInteraction as any);

      expect(mockInteraction.reply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringMatching(/cooldown|wait|recently/i),
        })
      );
    });

    it('should allow scan if guild cooldown has expired', async () => {
      const now = Date.now();
      const mockMember = {
        permissions: {
          has: jest.fn<(permission: bigint) => boolean>().mockReturnValue(true),
        },
      };

      const channelsCache = new Map();
      (channelsCache as any).filter = () => new Map();

      const mockGuild = {
        id: 'guild-expired-cooldown',
        name: 'Test Guild',
        channels: { cache: channelsCache },
      };

      const mockInteraction = {
        user: { id: 'admin123', username: 'adminuser' },
        member: mockMember,
        guildId: 'guild-expired-cooldown',
        guild: mockGuild,
        options: {
          getInteger: jest.fn<(name: string, required: boolean) => number>().mockReturnValue(7),
          getSubcommand: jest.fn().mockReturnValue('scan'),
          getSubcommandGroup: jest.fn().mockReturnValue(null),
          getChannel: jest.fn().mockReturnValue(null),
        },
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      mockCache.get.mockReturnValue(now - VIBECHECK_COOLDOWN_MS - 1000);

      await execute(mockInteraction as any);

      expect(mockInteraction.deferReply).toHaveBeenCalled();
    });

    it('should allow scan if no cooldown exists for guild', async () => {
      const mockMember = {
        permissions: {
          has: jest.fn<(permission: bigint) => boolean>().mockReturnValue(true),
        },
      };

      const channelsCache = new Map();
      (channelsCache as any).filter = () => new Map();

      const mockGuild = {
        id: 'guild-no-cooldown',
        name: 'Test Guild',
        channels: { cache: channelsCache },
      };

      const mockInteraction = {
        user: { id: 'admin123', username: 'adminuser' },
        member: mockMember,
        guildId: 'guild-no-cooldown',
        guild: mockGuild,
        options: {
          getInteger: jest.fn<(name: string, required: boolean) => number>().mockReturnValue(7),
          getSubcommand: jest.fn().mockReturnValue('scan'),
          getSubcommandGroup: jest.fn().mockReturnValue(null),
          getChannel: jest.fn().mockReturnValue(null),
        },
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      mockCache.get.mockReturnValue(null);

      await execute(mockInteraction as any);

      expect(mockInteraction.deferReply).toHaveBeenCalled();
    });

    it('should set cooldown after successful scan initiation', async () => {
      const mockMember = {
        permissions: {
          has: jest.fn<(permission: bigint) => boolean>().mockReturnValue(true),
        },
      };

      const channelsCache = new Map();
      (channelsCache as any).filter = () => new Map();

      const mockGuild = {
        id: 'guild-set-cooldown',
        name: 'Test Guild',
        channels: { cache: channelsCache },
      };

      const mockInteraction = {
        user: { id: 'admin123', username: 'adminuser' },
        member: mockMember,
        guildId: 'guild-set-cooldown',
        guild: mockGuild,
        options: {
          getInteger: jest.fn<(name: string, required: boolean) => number>().mockReturnValue(7),
          getSubcommand: jest.fn().mockReturnValue('scan'),
          getSubcommandGroup: jest.fn().mockReturnValue(null),
          getChannel: jest.fn().mockReturnValue(null),
        },
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      mockCache.get.mockReturnValue(null);

      await execute(mockInteraction as any);

      expect(mockCache.set).toHaveBeenCalledWith(
        'vibecheck:cooldown:guild-set-cooldown',
        expect.any(Number),
        VIBECHECK_COOLDOWN_MS / 1000
      );
    });

    it('should have independent cooldowns per guild', async () => {
      const keyGuildA = getVibecheckCooldownKey('guildA');
      const keyGuildB = getVibecheckCooldownKey('guildB');

      expect(keyGuildA).toBe('vibecheck:cooldown:guildA');
      expect(keyGuildB).toBe('vibecheck:cooldown:guildB');
      expect(keyGuildA).not.toBe(keyGuildB);
    });
  });

  describe('status subcommand', () => {
    it('should fetch latest scan for the guild', async () => {
      const mockMember = {
        permissions: {
          has: jest.fn<(permission: bigint) => boolean>().mockReturnValue(true),
        },
      };

      const channelsCache = new Map();
      (channelsCache as any).filter = () => new Map();

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
          getSubcommand: jest.fn().mockReturnValue('status'),
          getSubcommandGroup: jest.fn().mockReturnValue(null),
          getChannel: jest.fn().mockReturnValue(null),
        },
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      expect(mockApiClient.getCommunityServerByPlatformId).toHaveBeenCalledWith('guild789');
      expect(mockApiClient.getLatestScan).toHaveBeenCalledWith('community-server-uuid-123');
    });

    it('should display completed scan status', async () => {
      const mockMember = {
        permissions: {
          has: jest.fn<(permission: bigint) => boolean>().mockReturnValue(true),
        },
      };

      const channelsCache = new Map();
      (channelsCache as any).filter = () => new Map();

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
          getSubcommand: jest.fn().mockReturnValue('status'),
          getSubcommandGroup: jest.fn().mockReturnValue(null),
          getChannel: jest.fn().mockReturnValue(null),
        },
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      mockApiClient.getLatestScan.mockResolvedValueOnce(
        createLatestScanResponse('test-scan-456', 'completed', 250)
      );

      await execute(mockInteraction as any);

      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('Complete'),
        })
      );
    });

    it('should show message when no scans exist', async () => {
      const mockMember = {
        permissions: {
          has: jest.fn<(permission: bigint) => boolean>().mockReturnValue(true),
        },
      };

      const channelsCache = new Map();
      (channelsCache as any).filter = () => new Map();

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
          getSubcommand: jest.fn().mockReturnValue('status'),
          getSubcommandGroup: jest.fn().mockReturnValue(null),
          getChannel: jest.fn().mockReturnValue(null),
        },
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      const { ApiError } = await import('../../src/lib/errors.js') as any;
      mockApiClient.getLatestScan.mockRejectedValueOnce(new ApiError('Not found', '/api/scans', 404));

      await execute(mockInteraction as any);

      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringMatching(/no scans|run.*scan/i),
        })
      );
    });
  });
});
