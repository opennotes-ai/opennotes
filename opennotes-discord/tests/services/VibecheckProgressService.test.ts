import { jest } from '@jest/globals';
import { Client, Collection, ChannelType, EmbedBuilder } from 'discord.js';
import type { BulkScanProgressEvent } from '../../src/types/bulk-scan.js';
import { ConfigKey } from '../../src/lib/config-schema.js';

const mockLogger = {
  debug: jest.fn<(...args: unknown[]) => void>(),
  info: jest.fn<(...args: unknown[]) => void>(),
  warn: jest.fn<(...args: unknown[]) => void>(),
  error: jest.fn<(...args: unknown[]) => void>(),
};

const mockGuildConfigService = {
  get: jest.fn<(guildId: string, key: string) => Promise<any>>(),
  getAll: jest.fn<(guildId: string) => Promise<any>>(),
  set: jest.fn<(guildId: string, key: string, value: any, updatedBy: string) => Promise<void>>(),
  reset: jest.fn<(guildId: string, key?: string) => Promise<void>>(),
};

const mockBotChannelService = {
  findChannel: jest.fn<(guild: any, channelName: string) => any>(),
};

const mockApiClient = {
  getGuildConfig: jest.fn<(guildId: string) => Promise<Record<string, any>>>(),
  setGuildConfig: jest.fn<(guildId: string, key: string, value: any, updatedBy: string) => Promise<void>>(),
  resetGuildConfig: jest.fn<(guildId: string) => Promise<void>>(),
};

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
}));

jest.unstable_mockModule('../../src/services/GuildConfigService.js', () => {
  const MockGuildConfigService = function() {
    return mockGuildConfigService;
  };
  return { GuildConfigService: MockGuildConfigService };
});

jest.unstable_mockModule('../../src/services/BotChannelService.js', () => {
  const MockBotChannelService = function() {
    return mockBotChannelService;
  };
  return { BotChannelService: MockBotChannelService };
});

jest.unstable_mockModule('../../src/api-client.js', () => ({
  apiClient: mockApiClient,
}));

const { VibecheckProgressService } = await import('../../src/services/VibecheckProgressService.js');

function createMockProgressEvent(overrides: Partial<BulkScanProgressEvent> = {}): BulkScanProgressEvent {
  return {
    event_id: 'evt-123',
    event_type: 'bulk_scan.progress',
    version: '1.0',
    timestamp: new Date().toISOString(),
    metadata: {},
    scan_id: 'scan-abc-123',
    community_server_id: 'cs-uuid-123',
    platform_id: 'guild-123',
    batch_number: 1,
    messages_in_batch: 10,
    messages_processed: 100,
    channel_ids: ['ch-123'],
    message_scores: [
      {
        message_id: 'msg-001',
        channel_id: 'ch-123',
        similarity_score: 0.85,
        threshold: 0.75,
        is_flagged: true,
        matched_claim: 'This is a test claim that was matched',
      },
      {
        message_id: 'msg-002',
        channel_id: 'ch-123',
        similarity_score: 0.45,
        threshold: 0.75,
        is_flagged: false,
      },
    ],
    threshold_used: 0.75,
    ...overrides,
  };
}

function createMockGuild(id: string = 'guild-123') {
  return {
    id,
    name: 'Test Guild',
    channels: {
      cache: new Collection(),
    },
  };
}

function createMockChannel(name: string = 'opennotes-bot') {
  return {
    id: 'channel-456',
    name,
    type: ChannelType.GuildText,
    send: jest.fn<(options: any) => Promise<any>>().mockResolvedValue({}),
  };
}

function createMockClient(guilds: ReturnType<typeof createMockGuild>[] = []) {
  const guildsCollection = new Collection<string, ReturnType<typeof createMockGuild>>();
  guilds.forEach((guild) => guildsCollection.set(guild.id, guild));

  return {
    guilds: {
      cache: guildsCollection,
    },
  } as unknown as Client;
}

describe('VibecheckProgressService', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('handleProgressEvent', () => {
    it('should skip if guild not found', async () => {
      const mockClient = createMockClient([]);
      const service = new VibecheckProgressService(mockClient);
      const event = createMockProgressEvent({ platform_id: 'unknown-guild' });

      await service.handleProgressEvent(event);

      expect(mockLogger.debug).toHaveBeenCalledWith(
        'Guild not found for progress event',
        expect.objectContaining({ platformId: 'unknown-guild' })
      );
      expect(mockGuildConfigService.get).not.toHaveBeenCalled();
    });

    it('should skip if debug mode is disabled', async () => {
      const mockGuild = createMockGuild('guild-123');
      const mockClient = createMockClient([mockGuild]);
      const service = new VibecheckProgressService(mockClient);
      const event = createMockProgressEvent();

      mockGuildConfigService.get.mockResolvedValue(false);

      await service.handleProgressEvent(event);

      expect(mockGuildConfigService.get).toHaveBeenCalledWith('guild-123', ConfigKey.VIBECHECK_DEBUG_MODE);
      expect(mockLogger.debug).toHaveBeenCalledWith(
        'Vibecheck debug mode not enabled for guild',
        expect.objectContaining({ guildId: 'guild-123' })
      );
    });

    it('should skip if bot channel not found', async () => {
      const mockGuild = createMockGuild('guild-123');
      const mockClient = createMockClient([mockGuild]);
      const service = new VibecheckProgressService(mockClient);
      const event = createMockProgressEvent();

      mockGuildConfigService.get
        .mockResolvedValueOnce(true) // debug mode enabled
        .mockResolvedValueOnce('opennotes-bot'); // channel name
      mockBotChannelService.findChannel.mockReturnValue(undefined);

      await service.handleProgressEvent(event);

      expect(mockLogger.warn).toHaveBeenCalledWith(
        'Bot channel not found for progress event',
        expect.objectContaining({ guildId: 'guild-123' })
      );
    });

    it('should send progress embed when debug mode is enabled', async () => {
      const mockGuild = createMockGuild('guild-123');
      const mockChannel = createMockChannel();
      const mockClient = createMockClient([mockGuild]);
      const service = new VibecheckProgressService(mockClient);
      const event = createMockProgressEvent();

      mockGuildConfigService.get
        .mockResolvedValueOnce(true) // debug mode enabled
        .mockResolvedValueOnce('opennotes-bot'); // channel name
      mockBotChannelService.findChannel.mockReturnValue(mockChannel);

      await service.handleProgressEvent(event);

      expect(mockChannel.send).toHaveBeenCalledWith({
        embeds: expect.arrayContaining([expect.any(EmbedBuilder)]),
      });
      expect(mockLogger.debug).toHaveBeenCalledWith(
        'Sent vibecheck progress to bot channel',
        expect.objectContaining({
          guildId: 'guild-123',
          scanId: 'scan-abc-123',
          batchNumber: 1,
        })
      );
    });

    it('should handle send errors gracefully', async () => {
      const mockGuild = createMockGuild('guild-123');
      const mockChannel = createMockChannel();
      const mockClient = createMockClient([mockGuild]);
      const service = new VibecheckProgressService(mockClient);
      const event = createMockProgressEvent();

      mockGuildConfigService.get
        .mockResolvedValueOnce(true)
        .mockResolvedValueOnce('opennotes-bot');
      mockBotChannelService.findChannel.mockReturnValue(mockChannel);
      mockChannel.send.mockRejectedValue(new Error('Discord API error'));

      await service.handleProgressEvent(event);

      expect(mockLogger.error).toHaveBeenCalledWith(
        'Failed to send progress to bot channel',
        expect.objectContaining({
          error: 'Discord API error',
          guildId: 'guild-123',
        })
      );
    });
  });

  describe('formatProgressEmbed', () => {
    it('should format embed with correct title and batch number', async () => {
      const mockGuild = createMockGuild('guild-123');
      const mockChannel = createMockChannel();
      const mockClient = createMockClient([mockGuild]);
      const service = new VibecheckProgressService(mockClient);
      const event = createMockProgressEvent({ batch_number: 5 });

      mockGuildConfigService.get
        .mockResolvedValueOnce(true)
        .mockResolvedValueOnce('opennotes-bot');
      mockBotChannelService.findChannel.mockReturnValue(mockChannel);

      await service.handleProgressEvent(event);

      const sendCall = mockChannel.send.mock.calls[0][0] as { embeds: EmbedBuilder[] };
      const embed = sendCall.embeds[0];
      expect(embed.data.title).toContain('Batch 5');
    });

    it('should show orange color when there are flagged messages', async () => {
      const mockGuild = createMockGuild('guild-123');
      const mockChannel = createMockChannel();
      const mockClient = createMockClient([mockGuild]);
      const service = new VibecheckProgressService(mockClient);
      const event = createMockProgressEvent({
        message_scores: [
          { message_id: 'msg-1', channel_id: 'ch-1', similarity_score: 0.9, threshold: 0.75, is_flagged: true },
        ],
      });

      mockGuildConfigService.get
        .mockResolvedValueOnce(true)
        .mockResolvedValueOnce('opennotes-bot');
      mockBotChannelService.findChannel.mockReturnValue(mockChannel);

      await service.handleProgressEvent(event);

      const sendCall = mockChannel.send.mock.calls[0][0] as { embeds: EmbedBuilder[] };
      const embed = sendCall.embeds[0];
      expect(embed.data.color).toBe(0xff9900); // orange
    });

    it('should show green color when no messages are flagged', async () => {
      const mockGuild = createMockGuild('guild-123');
      const mockChannel = createMockChannel();
      const mockClient = createMockClient([mockGuild]);
      const service = new VibecheckProgressService(mockClient);
      const event = createMockProgressEvent({
        message_scores: [
          { message_id: 'msg-1', channel_id: 'ch-1', similarity_score: 0.4, threshold: 0.75, is_flagged: false },
        ],
      });

      mockGuildConfigService.get
        .mockResolvedValueOnce(true)
        .mockResolvedValueOnce('opennotes-bot');
      mockBotChannelService.findChannel.mockReturnValue(mockChannel);

      await service.handleProgressEvent(event);

      const sendCall = mockChannel.send.mock.calls[0][0] as { embeds: EmbedBuilder[] };
      const embed = sendCall.embeds[0];
      expect(embed.data.color).toBe(0x00aa00); // green
    });

    it('should include threshold in description', async () => {
      const mockGuild = createMockGuild('guild-123');
      const mockChannel = createMockChannel();
      const mockClient = createMockClient([mockGuild]);
      const service = new VibecheckProgressService(mockClient);
      const event = createMockProgressEvent({ threshold_used: 0.80 });

      mockGuildConfigService.get
        .mockResolvedValueOnce(true)
        .mockResolvedValueOnce('opennotes-bot');
      mockBotChannelService.findChannel.mockReturnValue(mockChannel);

      await service.handleProgressEvent(event);

      const sendCall = mockChannel.send.mock.calls[0][0] as { embeds: EmbedBuilder[] };
      const embed = sendCall.embeds[0];
      expect(embed.data.description).toContain('80%');
    });

    it('should include scan ID in footer', async () => {
      const mockGuild = createMockGuild('guild-123');
      const mockChannel = createMockChannel();
      const mockClient = createMockClient([mockGuild]);
      const service = new VibecheckProgressService(mockClient);
      const event = createMockProgressEvent({ scan_id: 'abcd1234-5678-90ab-cdef' });

      mockGuildConfigService.get
        .mockResolvedValueOnce(true)
        .mockResolvedValueOnce('opennotes-bot');
      mockBotChannelService.findChannel.mockReturnValue(mockChannel);

      await service.handleProgressEvent(event);

      const sendCall = mockChannel.send.mock.calls[0][0] as { embeds: EmbedBuilder[] };
      const embed = sendCall.embeds[0];
      expect(embed.data.footer?.text).toContain('abcd1234'); // first 8 chars
    });

    it('should show channel names in description (AC #4)', async () => {
      const mockGuild = createMockGuild('guild-123');
      // Add channels to the guild's cache
      mockGuild.channels.cache.set('ch-123', { id: 'ch-123', name: 'general' });
      mockGuild.channels.cache.set('ch-456', { id: 'ch-456', name: 'random' });

      const mockChannel = createMockChannel();
      const mockClient = createMockClient([mockGuild]);
      const service = new VibecheckProgressService(mockClient);
      const event = createMockProgressEvent({
        channel_ids: ['ch-123', 'ch-456'],
        messages_processed: 250,
      });

      mockGuildConfigService.get
        .mockResolvedValueOnce(true)
        .mockResolvedValueOnce('opennotes-bot');
      mockBotChannelService.findChannel.mockReturnValue(mockChannel);

      await service.handleProgressEvent(event);

      const sendCall = mockChannel.send.mock.calls[0][0] as { embeds: EmbedBuilder[] };
      const embed = sendCall.embeds[0];
      expect(embed.data.description).toContain('#general');
      expect(embed.data.description).toContain('#random');
      expect(embed.data.description).toContain('250 messages');
    });

    it('should handle missing channels gracefully', async () => {
      const mockGuild = createMockGuild('guild-123');
      // Only add one channel, leave the other missing
      mockGuild.channels.cache.set('ch-123', { id: 'ch-123', name: 'general' });

      const mockChannel = createMockChannel();
      const mockClient = createMockClient([mockGuild]);
      const service = new VibecheckProgressService(mockClient);
      const event = createMockProgressEvent({
        channel_ids: ['ch-123', 'ch-missing'],
        messages_processed: 100,
      });

      mockGuildConfigService.get
        .mockResolvedValueOnce(true)
        .mockResolvedValueOnce('opennotes-bot');
      mockBotChannelService.findChannel.mockReturnValue(mockChannel);

      await service.handleProgressEvent(event);

      const sendCall = mockChannel.send.mock.calls[0][0] as { embeds: EmbedBuilder[] };
      const embed = sendCall.embeds[0];
      // Should still show the channel that exists
      expect(embed.data.description).toContain('#general');
      expect(embed.data.description).toContain('100 messages');
    });

    it('should truncate when more than 3 channels', async () => {
      const mockGuild = createMockGuild('guild-123');
      mockGuild.channels.cache.set('ch-1', { id: 'ch-1', name: 'general' });
      mockGuild.channels.cache.set('ch-2', { id: 'ch-2', name: 'random' });
      mockGuild.channels.cache.set('ch-3', { id: 'ch-3', name: 'announcements' });
      mockGuild.channels.cache.set('ch-4', { id: 'ch-4', name: 'off-topic' });

      const mockChannel = createMockChannel();
      const mockClient = createMockClient([mockGuild]);
      const service = new VibecheckProgressService(mockClient);
      const event = createMockProgressEvent({
        channel_ids: ['ch-1', 'ch-2', 'ch-3', 'ch-4'],
        messages_processed: 500,
      });

      mockGuildConfigService.get
        .mockResolvedValueOnce(true)
        .mockResolvedValueOnce('opennotes-bot');
      mockBotChannelService.findChannel.mockReturnValue(mockChannel);

      await service.handleProgressEvent(event);

      const sendCall = mockChannel.send.mock.calls[0][0] as { embeds: EmbedBuilder[] };
      const embed = sendCall.embeds[0];
      // Should show first 3 channels and ellipsis
      expect(embed.data.description).toContain('#general');
      expect(embed.data.description).toContain('#random');
      expect(embed.data.description).toContain('#announcements');
      expect(embed.data.description).toContain('...');
      expect(embed.data.description).not.toContain('#off-topic');
    });
  });
});
