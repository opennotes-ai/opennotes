import { jest } from '@jest/globals';
import type { ScoreUpdateEvent } from '../../src/events/types.js';
import { Client, TextChannel, PermissionsBitField, PermissionFlagsBits, ChannelType } from 'discord.js';
import type { NoteContext } from '../../src/services/NoteContextService.js';
import type { NotePublisherConfig } from '../../src/services/NotePublisherConfigService.js';
import { TEST_SCORE_THRESHOLD, TEST_SCORE_ABOVE_THRESHOLD, TEST_SCORE_BELOW_THRESHOLD } from '../test-constants.js';

const mockLogger = {
  debug: jest.fn<(...args: unknown[]) => void>(),
  info: jest.fn<(...args: unknown[]) => void>(),
  warn: jest.fn<(...args: unknown[]) => void>(),
  error: jest.fn<(...args: unknown[]) => void>(),
};

const mockNoteContextService = {
  getNoteContext: jest.fn<() => Promise<NoteContext | null>>(),
  storeNoteContext: jest.fn<() => Promise<void>>(),
};

const mockConfigService = {
  getDefaultThreshold: jest.fn<() => number>(),
  getConfig: jest.fn<() => Promise<NotePublisherConfig>>(),
  setConfig: jest.fn<() => Promise<void>>(),
};

const mockApiClient = {
  checkNoteDuplicate: jest.fn<() => Promise<any>>(),
  getLastNotePost: jest.fn<() => Promise<any>>(),
  getNote: jest.fn<() => Promise<any>>(),
  recordNotePublisher: jest.fn<() => Promise<void>>(),
};

jest.unstable_mockModule('../../src/services/NoteContextService.js', () => ({
  NoteContextService: jest.fn(() => mockNoteContextService),
}));

jest.unstable_mockModule('../../src/services/NotePublisherConfigService.js', () => ({
  NotePublisherConfigService: jest.fn(() => mockConfigService),
}));

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
}));

jest.unstable_mockModule('../../src/api-client.js', () => ({
  apiClient: mockApiClient,
}));

const { NotePublisherService } = await import('../../src/services/NotePublisherService.js');

describe('NotePublisherService', () => {
  let notePublisherService: InstanceType<typeof NotePublisherService>;
  let mockClient: Client;
  let mockChannel: TextChannel;

  beforeEach(() => {
    mockClient = {
      user: { id: 'bot-123' },
      channels: {
        cache: new Map(),
        fetch: jest.fn<(...args: any[]) => Promise<any>>(),
      },
    } as any;

    mockChannel = Object.create(TextChannel.prototype);
    mockChannel.id = 'channel-456';
    mockChannel.type = ChannelType.GuildText;
    (mockChannel as any).isThread = jest.fn<() => any>().mockReturnValue(false);
    (mockChannel as any).isTextBased = jest.fn<() => any>().mockReturnValue(true);
    (mockChannel as any).isDMBased = jest.fn<() => any>().mockReturnValue(false);
    mockChannel.permissionsFor = jest.fn<(...args: any[]) => any>();
    mockChannel.send = jest.fn<(...args: any[]) => Promise<any>>();

    mockConfigService.getDefaultThreshold.mockReturnValue(TEST_SCORE_THRESHOLD);
    mockConfigService.getConfig.mockResolvedValue({
      guildId: 'guild-123',
      enabled: true,
      threshold: TEST_SCORE_THRESHOLD,
    });

    notePublisherService = new NotePublisherService(
      mockClient,
      mockNoteContextService as any,
      mockConfigService as any
    );

    notePublisherService.clearPermissionCache();
    jest.clearAllMocks();
  });

  describe('threshold validation (AC #2)', () => {
    it('should reject events below threshold', async () => {
      const event: ScoreUpdateEvent = {
        note_id: 1,
        score: TEST_SCORE_BELOW_THRESHOLD,
        confidence: 'standard',
        algorithm: 'BayesianAverage',
        rating_count: 10,
        tier: 0,
        tier_name: 'Tier 0',
        timestamp: new Date().toISOString(),
        original_message_id: 'msg-123',
        channel_id: 'channel-456',
        community_server_id: 'guild-123',
      };

      await notePublisherService.handleScoreUpdate(event);

      expect(mockNoteContextService.getNoteContext).not.toHaveBeenCalled();
    });

    it('should reject events with non-standard confidence', async () => {
      const event: ScoreUpdateEvent = {
        note_id: 1,
        score: TEST_SCORE_ABOVE_THRESHOLD,
        confidence: 'provisional',
        algorithm: 'BayesianAverage',
        rating_count: 3,
        tier: 0,
        tier_name: 'Tier 0',
        timestamp: new Date().toISOString(),
        original_message_id: 'msg-123',
        channel_id: 'channel-456',
        community_server_id: 'guild-123',
      };

      await notePublisherService.handleScoreUpdate(event);

      expect(mockNoteContextService.getNoteContext).not.toHaveBeenCalled();
    });

    it('should accept events meeting threshold with standard confidence', async () => {
      const event: ScoreUpdateEvent = {
        note_id: 1,
        score: TEST_SCORE_ABOVE_THRESHOLD,
        confidence: 'standard',
        algorithm: 'MFCoreScorer',
        rating_count: 10,
        tier: 2,
        tier_name: 'Tier 2',
        timestamp: new Date().toISOString(),
        original_message_id: 'msg-123',
        channel_id: 'channel-456',
        community_server_id: 'guild-123',
      };

      mockApiClient.checkNoteDuplicate.mockResolvedValueOnce({ exists: false });
      mockApiClient.getLastNotePost.mockRejectedValueOnce(new Error('404'));

      mockClient.channels.cache.set('channel-456', mockChannel);
      (mockChannel.permissionsFor as jest.Mock).mockReturnValue(
        new PermissionsBitField(['SendMessages', 'CreatePublicThreads'])
      );
      (mockClient.channels.fetch as any).mockResolvedValue(mockChannel);

      mockApiClient.getNote.mockResolvedValueOnce({ summary: 'Test note content' });

      mockChannel.send = jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({ id: 'reply-789' });
      mockApiClient.recordNotePublisher.mockResolvedValue(undefined);

      await notePublisherService.handleScoreUpdate(event);

      expect(mockChannel.send).toHaveBeenCalled();
    });
  });

  describe('duplicate prevention (AC #7)', () => {
    it('should skip if auto-post already exists for message', async () => {
      const event: ScoreUpdateEvent = {
        note_id: 1,
        score: TEST_SCORE_ABOVE_THRESHOLD,
        confidence: 'standard',
        algorithm: 'MFCoreScorer',
        rating_count: 10,
        tier: 2,
        tier_name: 'Tier 2',
        timestamp: new Date().toISOString(),
        original_message_id: 'msg-123',
        channel_id: 'channel-456',
        community_server_id: 'guild-123',
      };

      mockApiClient.checkNoteDuplicate.mockResolvedValueOnce({ exists: true, note_publisher_post_id: 5 });

      await notePublisherService.handleScoreUpdate(event);

      expect(mockChannel.send).not.toHaveBeenCalled();
    });
  });

  describe('cooldown system (AC #8)', () => {
    it('should skip if channel is on cooldown', async () => {
      const event: ScoreUpdateEvent = {
        note_id: 1,
        score: TEST_SCORE_ABOVE_THRESHOLD,
        confidence: 'standard',
        algorithm: 'MFCoreScorer',
        rating_count: 10,
        tier: 2,
        tier_name: 'Tier 2',
        timestamp: new Date().toISOString(),
        original_message_id: 'msg-123',
        channel_id: 'channel-456',
        community_server_id: 'guild-123',
      };

      mockApiClient.checkNoteDuplicate.mockResolvedValueOnce({ exists: false });

      const twoMinutesAgo = new Date(Date.now() - 2 * 60 * 1000);
      mockApiClient.getLastNotePost.mockResolvedValueOnce({ posted_at: twoMinutesAgo.toISOString(), note_id: 1, channel_id: 'channel-456' });

      await notePublisherService.handleScoreUpdate(event);

      expect(mockChannel.send).not.toHaveBeenCalled();
    });

    it('should proceed if cooldown expired', async () => {
      const event: ScoreUpdateEvent = {
        note_id: 1,
        score: TEST_SCORE_ABOVE_THRESHOLD,
        confidence: 'standard',
        algorithm: 'MFCoreScorer',
        rating_count: 10,
        tier: 2,
        tier_name: 'Tier 2',
        timestamp: new Date().toISOString(),
        original_message_id: 'msg-123',
        channel_id: 'channel-456',
        community_server_id: 'guild-123',
      };

      mockApiClient.checkNoteDuplicate.mockResolvedValueOnce({ exists: false });

      const sixMinutesAgo = new Date(Date.now() - 6 * 60 * 1000);
      mockApiClient.getLastNotePost.mockResolvedValueOnce({ posted_at: sixMinutesAgo.toISOString(), note_id: 1, channel_id: 'channel-456' });

      mockClient.channels.cache.set('channel-456', mockChannel);
      (mockChannel.permissionsFor as jest.Mock).mockReturnValue(
        new PermissionsBitField(['SendMessages', 'CreatePublicThreads'])
      );
      (mockClient.channels.fetch as any).mockResolvedValue(mockChannel);

      mockApiClient.getNote.mockResolvedValueOnce({ summary: 'Test note' });

      mockChannel.send = jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({ id: 'reply-789' });
      mockApiClient.recordNotePublisher.mockResolvedValue(undefined);

      await notePublisherService.handleScoreUpdate(event);

      expect(mockChannel.send).toHaveBeenCalled();
    });
  });

  describe('configuration (AC #3)', () => {
    it('should skip if auto-posting disabled for server', async () => {
      const event: ScoreUpdateEvent = {
        note_id: 1,
        score: TEST_SCORE_ABOVE_THRESHOLD,
        confidence: 'standard',
        algorithm: 'MFCoreScorer',
        rating_count: 10,
        tier: 2,
        tier_name: 'Tier 2',
        timestamp: new Date().toISOString(),
        original_message_id: 'msg-123',
        channel_id: 'channel-456',
        community_server_id: 'guild-123',
      };

      mockApiClient.checkNoteDuplicate.mockResolvedValueOnce({ exists: false });
      mockApiClient.getLastNotePost.mockRejectedValueOnce(new Error('404'));

      mockConfigService.getConfig = jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({
        guildId: 'guild-123',
        enabled: false,
        threshold: TEST_SCORE_THRESHOLD,
      });

      await notePublisherService.handleScoreUpdate(event);

      expect(mockChannel.send).not.toHaveBeenCalled();
    });

    it('should skip if auto-posting disabled for channel', async () => {
      const event: ScoreUpdateEvent = {
        note_id: 1,
        score: TEST_SCORE_ABOVE_THRESHOLD,
        confidence: 'standard',
        algorithm: 'MFCoreScorer',
        rating_count: 10,
        tier: 2,
        tier_name: 'Tier 2',
        timestamp: new Date().toISOString(),
        original_message_id: 'msg-123',
        channel_id: 'channel-456',
        community_server_id: 'guild-123',
      };

      mockApiClient.checkNoteDuplicate.mockResolvedValueOnce({ exists: false });
      mockApiClient.getLastNotePost.mockRejectedValueOnce(new Error('404'));

      mockConfigService.getConfig = jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({
        guildId: 'guild-123',
        channelId: 'channel-456',
        enabled: false,
        threshold: TEST_SCORE_THRESHOLD,
      });

      await notePublisherService.handleScoreUpdate(event);

      expect(mockChannel.send).not.toHaveBeenCalled();
    });
  });

  describe('permission checks (AC #9)', () => {
    it('should skip if missing SEND_MESSAGES permission', async () => {
      const event: ScoreUpdateEvent = {
        note_id: 1,
        score: TEST_SCORE_ABOVE_THRESHOLD,
        confidence: 'standard',
        algorithm: 'MFCoreScorer',
        rating_count: 10,
        tier: 2,
        tier_name: 'Tier 2',
        timestamp: new Date().toISOString(),
        original_message_id: 'msg-123',
        channel_id: 'channel-456',
        community_server_id: 'guild-123',
      };

      mockApiClient.checkNoteDuplicate.mockResolvedValueOnce({ exists: false });
      mockApiClient.getLastNotePost.mockRejectedValueOnce(new Error('404'));

      mockClient.channels.cache.set('channel-456', mockChannel);
      (mockChannel.permissionsFor as jest.Mock).mockReturnValue(
        new PermissionsBitField(['CreatePublicThreads'])
      );

      await notePublisherService.handleScoreUpdate(event);

      expect(mockChannel.send).not.toHaveBeenCalled();
    });
  });

  describe('error handling (AC #10)', () => {
    it('should handle deleted original message gracefully', async () => {
      const event: ScoreUpdateEvent = {
        note_id: 1,
        score: TEST_SCORE_ABOVE_THRESHOLD,
        confidence: 'standard',
        algorithm: 'MFCoreScorer',
        rating_count: 10,
        tier: 2,
        tier_name: 'Tier 2',
        timestamp: new Date().toISOString(),
        original_message_id: 'msg-deleted',
        channel_id: 'channel-456',
        community_server_id: 'guild-123',
      };

      mockApiClient.checkNoteDuplicate.mockResolvedValueOnce({ exists: false });
      mockApiClient.getLastNotePost.mockRejectedValueOnce(new Error('404'));

      mockClient.channels.cache.set('channel-456', mockChannel);
      (mockChannel.permissionsFor as jest.Mock).mockReturnValue(
        new PermissionsBitField(['SendMessages', 'CreatePublicThreads'])
      );
      (mockClient.channels.fetch as any).mockResolvedValue(mockChannel);

      mockApiClient.getNote.mockResolvedValueOnce({ summary: 'Test note' });

      const discordError: any = new Error('Unknown Message');
      discordError.code = 10008;
      mockChannel.send = jest.fn<(...args: any[]) => Promise<any>>().mockRejectedValue(discordError);

      await notePublisherService.handleScoreUpdate(event);

      expect(mockChannel.send).toHaveBeenCalled();
    });
  });

  describe('message formatting (AC #6)', () => {
    it('should format message with all required components', async () => {
      const event: ScoreUpdateEvent = {
        note_id: 1,
        score: TEST_SCORE_ABOVE_THRESHOLD,
        confidence: 'standard',
        algorithm: 'MFCoreScorer',
        rating_count: 10,
        tier: 2,
        tier_name: 'Tier 2',
        timestamp: new Date().toISOString(),
        original_message_id: 'msg-123',
        channel_id: 'channel-456',
        community_server_id: 'guild-123',
      };

      mockApiClient.checkNoteDuplicate.mockResolvedValueOnce({ exists: false });
      mockApiClient.getLastNotePost.mockRejectedValueOnce(new Error('404'));

      mockClient.channels.cache.set('channel-456', mockChannel);
      (mockChannel.permissionsFor as jest.Mock).mockReturnValue(
        new PermissionsBitField(['SendMessages', 'CreatePublicThreads'])
      );
      (mockClient.channels.fetch as any).mockResolvedValue(mockChannel);

      mockApiClient.getNote.mockResolvedValueOnce({ summary: 'This is a helpful community note' });

      mockChannel.send = jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({ id: 'reply-789' });
      mockApiClient.recordNotePublisher.mockResolvedValue(undefined);

      await notePublisherService.handleScoreUpdate(event);

      const sentMessage = (mockChannel.send as jest.Mock).mock.calls[0][0] as { content: string };
      expect(sentMessage.content).toContain('🤖');
      expect(sentMessage.content).toContain(`${(TEST_SCORE_ABOVE_THRESHOLD * 100).toFixed(1)}%`);
      expect(sentMessage.content).toContain('standard');
      expect(sentMessage.content).toContain('10 ratings');
      expect(sentMessage.content).toContain('This is a helpful community note');
    });
  });

  describe('parallel API checks (task-386 AC #6)', () => {
    it('should execute isDuplicate, isOnCooldown, and getConfig in parallel', async () => {
      const event: ScoreUpdateEvent = {
        note_id: 1,
        score: TEST_SCORE_ABOVE_THRESHOLD,
        confidence: 'standard',
        algorithm: 'MFCoreScorer',
        rating_count: 10,
        tier: 2,
        tier_name: 'Tier 2',
        timestamp: new Date().toISOString(),
        original_message_id: 'msg-123',
        channel_id: 'channel-456',
        community_server_id: 'guild-123',
      };

      mockClient.channels.cache.set('channel-456', mockChannel);
      (mockChannel.permissionsFor as jest.Mock).mockReturnValue(
        new PermissionsBitField([PermissionFlagsBits.SendMessages, PermissionFlagsBits.CreatePublicThreads])
      );
      (mockClient.channels.fetch as any).mockResolvedValue(mockChannel);

      mockNoteContextService.getNoteContext.mockResolvedValue({
        noteId: '1',
        originalMessageId: 'msg-123',
        channelId: 'channel-456',
        guildId: 'guild-123',
        authorId: 'user-123',
      });

      mockConfigService.getConfig.mockResolvedValue({
        guildId: 'guild-123',
        channelId: 'channel-456',
        enabled: true,
        threshold: TEST_SCORE_THRESHOLD,
      });

      mockApiClient.checkNoteDuplicate.mockResolvedValueOnce({ exists: false });

      mockApiClient.getLastNotePost.mockResolvedValueOnce({
        posted_at: new Date(Date.now() - 10 * 60 * 1000).toISOString(),
        note_id: 1,
        channel_id: 'channel-456'
      });

      mockApiClient.getNote.mockResolvedValueOnce({ summary: 'Test note content' });

      mockChannel.send = jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({ id: 'reply-789' });
      mockApiClient.recordNotePublisher.mockResolvedValue(undefined);

      await notePublisherService.handleScoreUpdate(event);

      expect(mockChannel.send).toHaveBeenCalled();
      expect(mockConfigService.getConfig).toHaveBeenCalled();
    });
  });

  describe('error handling with Promise.all (task-386 AC #7)', () => {
    it('should handle errors in parallel checks gracefully', async () => {
      const event: ScoreUpdateEvent = {
        note_id: 1,
        score: TEST_SCORE_ABOVE_THRESHOLD,
        confidence: 'standard',
        algorithm: 'MFCoreScorer',
        rating_count: 10,
        tier: 2,
        tier_name: 'Tier 2',
        timestamp: new Date().toISOString(),
        original_message_id: 'msg-123',
        channel_id: 'channel-456',
        community_server_id: 'guild-123',
      };

      mockClient.channels.cache.set('channel-456', mockChannel);
      (mockChannel.permissionsFor as jest.Mock).mockReturnValue(
        new PermissionsBitField(['SendMessages', 'CreatePublicThreads'])
      );

      mockApiClient.checkNoteDuplicate.mockRejectedValueOnce(new Error('Network error'));

      await notePublisherService.handleScoreUpdate(event);

      expect(mockChannel.send).not.toHaveBeenCalled();
    });

    it('should handle partial failures in parallel checks', async () => {
      const event: ScoreUpdateEvent = {
        note_id: 1,
        score: TEST_SCORE_ABOVE_THRESHOLD,
        confidence: 'standard',
        algorithm: 'MFCoreScorer',
        rating_count: 10,
        tier: 2,
        tier_name: 'Tier 2',
        timestamp: new Date().toISOString(),
        original_message_id: 'msg-123',
        channel_id: 'channel-456',
        community_server_id: 'guild-123',
      };

      mockApiClient.checkNoteDuplicate.mockResolvedValueOnce({ exists: false });

      mockApiClient.getLastNotePost.mockRejectedValueOnce(new Error('500'));

      await notePublisherService.handleScoreUpdate(event);

      expect(mockChannel.send).not.toHaveBeenCalled();
    });
  });

  describe('permission caching (task-386 AC #3)', () => {
    it('should cache permission checks for 5 minutes', async () => {
      const event: ScoreUpdateEvent = {
        note_id: 1,
        score: TEST_SCORE_ABOVE_THRESHOLD,
        confidence: 'standard',
        algorithm: 'MFCoreScorer',
        rating_count: 10,
        tier: 2,
        tier_name: 'Tier 2',
        timestamp: new Date().toISOString(),
        original_message_id: 'msg-123',
        channel_id: 'channel-456',
        community_server_id: 'guild-123',
      };

      mockClient.channels.cache.set('channel-456', mockChannel);
      const permissionsForSpy = jest.fn<(...args: any[]) => any>().mockReturnValue(
        new PermissionsBitField(['SendMessages', 'CreatePublicThreads'])
      );
      mockChannel.permissionsFor = permissionsForSpy;

      mockApiClient.checkNoteDuplicate.mockResolvedValue({ exists: true });

      await notePublisherService.handleScoreUpdate(event);
      await notePublisherService.handleScoreUpdate(event);

      expect(permissionsForSpy).toHaveBeenCalledTimes(1);
    });
  });
});
