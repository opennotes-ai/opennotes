import { jest } from '@jest/globals';
import type { ScoreUpdateEvent } from '../../src/events/types.js';
import { Client, TextChannel, PermissionsBitField, PermissionFlagsBits, ChannelType, MessageFlags } from 'discord.js';
import type { NoteContext } from '../../src/services/NoteContextService.js';
import type { NotePublisherConfig } from '../../src/services/NotePublisherConfigService.js';
import { TEST_SCORE_THRESHOLD, TEST_SCORE_ABOVE_THRESHOLD, TEST_SCORE_BELOW_THRESHOLD } from '../test-constants.js';
import { V2_COLORS } from '../../src/utils/v2-components.js';
import { loggerFactory, apiClientFactory, discordChannelFactory, type MockApiClient } from '../factories/index.js';

const mockLogger = loggerFactory.build();

const mockNoteContextService = {
  getNoteContext: jest.fn<() => Promise<NoteContext | null>>(),
  storeNoteContext: jest.fn<() => Promise<void>>(),
};

const mockConfigService = {
  getDefaultThreshold: jest.fn<() => number>(),
  getConfig: jest.fn<() => Promise<NotePublisherConfig>>(),
  setConfig: jest.fn<() => Promise<void>>(),
};

const mockApiClient = apiClientFactory.build();

const mockResolveCommunityServerId = jest.fn<(guildId: string) => Promise<string>>();

jest.unstable_mockModule('../../src/lib/community-server-resolver.js', () => ({
  resolveCommunityServerId: mockResolveCommunityServerId,
}));

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

function createMockNoteJSONAPIResponse(overrides: {
  id?: string;
  summary?: string;
  imageUrls?: string[];
} = {}): any {
  return {
    data: {
      type: 'notes',
      id: overrides.id ?? '1',
      attributes: {
        summary: overrides.summary ?? 'Test note content',
        classification: 'NOT_MISLEADING',
        status: 'NEEDS_MORE_RATINGS',
        helpfulness_score: 0,
        author_id: 'user-123',
        community_server_id: 'guild-123',
        channel_id: 'channel-456',
        request_id: null,
        ratings_count: 0,
        force_published: false,
        force_published_at: null,
        ai_generated: false,
        ai_provider: null,
        created_at: new Date().toISOString(),
        updated_at: null,
        ...(overrides.imageUrls && { image_urls: overrides.imageUrls }),
      },
    },
    jsonapi: { version: '1.1' },
  };
}

function createMockDuplicateCheckResponse(exists: boolean, notePublisherPostId?: string): any {
  if (!exists) {
    return { data: [], jsonapi: { version: '1.1' } };
  }
  return {
    data: [{
      type: 'note-publisher-posts',
      id: notePublisherPostId ?? '1',
      attributes: {
        note_id: '1',
        original_message_id: 'msg-123',
        channel_id: 'channel-456',
        community_server_id: 'guild-123',
        posted_at: new Date().toISOString(),
        success: true,
      },
    }],
    jsonapi: { version: '1.1' },
  };
}

function createMockLastNotePostResponse(postedAt: string, noteId: string, channelId: string): any {
  return {
    data: [{
      type: 'note-publisher-posts',
      id: '1',
      attributes: {
        note_id: noteId,
        original_message_id: 'msg-123',
        channel_id: channelId,
        community_server_id: 'guild-123',
        posted_at: postedAt,
        success: true,
      },
    }],
    jsonapi: { version: '1.1' },
  };
}

function createEmptyListResponse(): any {
  return { data: [], jsonapi: { version: '1.1' } };
}

describe('NotePublisherService', () => {
  let notePublisherService: InstanceType<typeof NotePublisherService>;
  let mockClient: Client;
  let mockChannel: ReturnType<typeof discordChannelFactory.build>;

  beforeEach(() => {
    mockClient = {
      user: { id: 'bot-123' },
      channels: {
        cache: new Map(),
        fetch: jest.fn<(...args: any[]) => Promise<any>>(),
      },
    } as any;

    mockChannel = discordChannelFactory.build({}, { transient: { hasPermissions: true } });
    Object.assign(mockChannel, {
      type: ChannelType.GuildText,
      id: 'channel-456',
    });

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

      mockApiClient.checkNoteDuplicate.mockResolvedValueOnce(createMockDuplicateCheckResponse(false));
      mockApiClient.getLastNotePost.mockResolvedValueOnce(createEmptyListResponse());

      mockClient.channels.cache.set('channel-456', mockChannel as any);
      mockChannel.permissionsFor.mockReturnValue(
        new PermissionsBitField(['SendMessages', 'CreatePublicThreads'])
      );
      (mockClient.channels.fetch as any).mockResolvedValue(mockChannel);

      mockApiClient.getNote.mockResolvedValueOnce(createMockNoteJSONAPIResponse({ summary: 'Test note content' }));

      mockChannel.send.mockResolvedValue({ id: 'reply-789' });
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

      mockApiClient.checkNoteDuplicate.mockResolvedValueOnce(createMockDuplicateCheckResponse(true, '5'));

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

      mockApiClient.checkNoteDuplicate.mockResolvedValueOnce(createMockDuplicateCheckResponse(false));

      const twoMinutesAgo = new Date(Date.now() - 2 * 60 * 1000);
      mockApiClient.getLastNotePost.mockResolvedValueOnce(createMockLastNotePostResponse(twoMinutesAgo.toISOString(), '1', 'channel-456'));

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

      mockApiClient.checkNoteDuplicate.mockResolvedValueOnce(createMockDuplicateCheckResponse(false));

      const sixMinutesAgo = new Date(Date.now() - 6 * 60 * 1000);
      mockApiClient.getLastNotePost.mockResolvedValueOnce(createMockLastNotePostResponse(sixMinutesAgo.toISOString(), '1', 'channel-456'));

      mockClient.channels.cache.set('channel-456', mockChannel as any);
      mockChannel.permissionsFor.mockReturnValue(
        new PermissionsBitField(['SendMessages', 'CreatePublicThreads'])
      );
      (mockClient.channels.fetch as any).mockResolvedValue(mockChannel);

      mockApiClient.getNote.mockResolvedValueOnce(createMockNoteJSONAPIResponse({ summary: 'Test note' }));

      mockChannel.send.mockResolvedValue({ id: 'reply-789' });
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

      mockApiClient.checkNoteDuplicate.mockResolvedValueOnce(createMockDuplicateCheckResponse(false));
      mockApiClient.getLastNotePost.mockResolvedValueOnce(createEmptyListResponse());

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

      mockApiClient.checkNoteDuplicate.mockResolvedValueOnce(createMockDuplicateCheckResponse(false));
      mockApiClient.getLastNotePost.mockResolvedValueOnce(createEmptyListResponse());

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

      mockApiClient.checkNoteDuplicate.mockResolvedValueOnce(createMockDuplicateCheckResponse(false));
      mockApiClient.getLastNotePost.mockResolvedValueOnce(createEmptyListResponse());

      mockClient.channels.cache.set('channel-456', mockChannel as any);
      mockChannel.permissionsFor.mockReturnValue(
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

      mockApiClient.checkNoteDuplicate.mockResolvedValueOnce(createMockDuplicateCheckResponse(false));
      mockApiClient.getLastNotePost.mockResolvedValueOnce(createEmptyListResponse());

      mockClient.channels.cache.set('channel-456', mockChannel as any);
      mockChannel.permissionsFor.mockReturnValue(
        new PermissionsBitField(['SendMessages', 'CreatePublicThreads'])
      );
      (mockClient.channels.fetch as any).mockResolvedValue(mockChannel);

      mockApiClient.getNote.mockResolvedValueOnce(createMockNoteJSONAPIResponse({ summary: 'Test note' }));

      const discordError: any = new Error('Unknown Message');
      discordError.code = 10008;
      mockChannel.send.mockRejectedValue(discordError);

      await notePublisherService.handleScoreUpdate(event);

      expect(mockChannel.send).toHaveBeenCalled();
    });
  });

  describe('message formatting (AC #6 - updated for Components v2)', () => {
    it('should format message with all required components using v2 format', async () => {
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

      mockConfigService.getDefaultThreshold.mockReturnValue(TEST_SCORE_THRESHOLD);
      mockConfigService.getConfig.mockResolvedValue({
        guildId: 'guild-123',
        enabled: true,
        threshold: TEST_SCORE_THRESHOLD,
      });

      mockApiClient.checkNoteDuplicate.mockResolvedValueOnce(createMockDuplicateCheckResponse(false));
      mockApiClient.getLastNotePost.mockResolvedValueOnce(createEmptyListResponse());

      mockClient.channels.cache.set('channel-456', mockChannel as any);
      mockChannel.permissionsFor.mockReturnValue(
        new PermissionsBitField(['SendMessages', 'CreatePublicThreads'])
      );
      (mockClient.channels.fetch as any).mockResolvedValue(mockChannel);

      mockApiClient.getNote.mockResolvedValueOnce(createMockNoteJSONAPIResponse({ summary: 'This is a helpful community note' }));

      mockChannel.send.mockResolvedValue({ id: 'reply-789' });
      mockApiClient.recordNotePublisher.mockResolvedValue(undefined);

      await notePublisherService.handleScoreUpdate(event);

      const sentMessage = (mockChannel.send as jest.Mock).mock.calls[0][0] as { components?: any[]; flags?: number };
      const messageJson = JSON.stringify(sentMessage.components);

      expect(sentMessage.components).toBeDefined();
      expect(sentMessage.flags).toBeDefined();
      expect((sentMessage.flags! & MessageFlags.IsComponentsV2) !== 0).toBe(true);
      expect(messageJson).toContain(`${(TEST_SCORE_ABOVE_THRESHOLD * 100).toFixed(1)}%`);
      expect(messageJson).toContain('standard');
      expect(messageJson).toContain('10 ratings');
      expect(messageJson).toContain('This is a helpful community note');
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

      mockClient.channels.cache.set('channel-456', mockChannel as any);
      mockChannel.permissionsFor.mockReturnValue(
        new PermissionsBitField([PermissionFlagsBits.SendMessages, PermissionFlagsBits.CreatePublicThreads])
      );
      (mockClient.channels.fetch as any).mockResolvedValue(mockChannel);

      mockNoteContextService.getNoteContext.mockResolvedValue({
        noteId: '1',
        originalMessageId: 'msg-123',
        channelId: 'channel-456',
        guildId: 'guild-123',
        authorId: '00000000-0000-0001-aaaa-123',
      });

      mockConfigService.getConfig.mockResolvedValue({
        guildId: 'guild-123',
        channelId: 'channel-456',
        enabled: true,
        threshold: TEST_SCORE_THRESHOLD,
      });

      mockApiClient.checkNoteDuplicate.mockResolvedValueOnce(createMockDuplicateCheckResponse(false));

      const tenMinutesAgo = new Date(Date.now() - 10 * 60 * 1000);
      mockApiClient.getLastNotePost.mockResolvedValueOnce(createMockLastNotePostResponse(tenMinutesAgo.toISOString(), '1', 'channel-456'));

      mockApiClient.getNote.mockResolvedValueOnce(createMockNoteJSONAPIResponse({ summary: 'Test note content' }));

      mockChannel.send.mockResolvedValue({ id: 'reply-789' });
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

      mockClient.channels.cache.set('channel-456', mockChannel as any);
      mockChannel.permissionsFor.mockReturnValue(
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

      mockApiClient.checkNoteDuplicate.mockResolvedValueOnce(createMockDuplicateCheckResponse(false));

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

      mockClient.channels.cache.set('channel-456', mockChannel as any);
      mockChannel.permissionsFor.mockReturnValue(
        new PermissionsBitField(['SendMessages', 'CreatePublicThreads'])
      );

      mockApiClient.checkNoteDuplicate.mockResolvedValue(createMockDuplicateCheckResponse(true));

      await notePublisherService.handleScoreUpdate(event);
      await notePublisherService.handleScoreUpdate(event);

      expect(mockChannel.permissionsFor).toHaveBeenCalledTimes(1);
    });
  });

  describe('Components v2 migration (task-821)', () => {
    beforeEach(() => {
      mockConfigService.getDefaultThreshold.mockReturnValue(TEST_SCORE_THRESHOLD);
      mockConfigService.getConfig.mockResolvedValue({
        guildId: 'guild-123',
        enabled: true,
        threshold: TEST_SCORE_THRESHOLD,
      });
    });

    describe('AC #1: Convert auto-post embed to ContainerBuilder', () => {
      it('should send message with ContainerBuilder components', async () => {
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

        mockApiClient.checkNoteDuplicate.mockResolvedValueOnce(createMockDuplicateCheckResponse(false));
        mockApiClient.getLastNotePost.mockResolvedValueOnce(createEmptyListResponse());

        mockClient.channels.cache.set('channel-456', mockChannel as any);
        mockChannel.permissionsFor.mockReturnValue(
          new PermissionsBitField(['SendMessages', 'CreatePublicThreads'])
        );
        (mockClient.channels.fetch as any).mockResolvedValue(mockChannel);

        mockApiClient.getNote.mockResolvedValueOnce(createMockNoteJSONAPIResponse({ summary: 'Test note content' }));

        mockChannel.send.mockResolvedValue({ id: 'reply-789' });
        mockApiClient.recordNotePublisher.mockResolvedValue(undefined);

        await notePublisherService.handleScoreUpdate(event);

        expect(mockChannel.send).toHaveBeenCalled();
        const sentMessage = (mockChannel.send as jest.Mock).mock.calls[0][0] as {
          components?: any[];
          flags?: number;
        };

        expect(sentMessage.components).toBeDefined();
        expect(sentMessage.components?.length).toBeGreaterThan(0);
      });
    });

    describe('AC #2: Add visual score indicator using TextDisplayBuilder', () => {
      it('should include score percentage in message components', async () => {
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

        mockApiClient.checkNoteDuplicate.mockResolvedValueOnce(createMockDuplicateCheckResponse(false));
        mockApiClient.getLastNotePost.mockResolvedValueOnce(createEmptyListResponse());

        mockClient.channels.cache.set('channel-456', mockChannel as any);
        mockChannel.permissionsFor.mockReturnValue(
          new PermissionsBitField(['SendMessages', 'CreatePublicThreads'])
        );
        (mockClient.channels.fetch as any).mockResolvedValue(mockChannel);

        mockApiClient.getNote.mockResolvedValueOnce(createMockNoteJSONAPIResponse({ summary: 'Test note content' }));

        mockChannel.send.mockResolvedValue({ id: 'reply-789' });
        mockApiClient.recordNotePublisher.mockResolvedValue(undefined);

        await notePublisherService.handleScoreUpdate(event);

        const sentMessage = (mockChannel.send as jest.Mock).mock.calls[0][0] as { components?: any[] };
        const messageJson = JSON.stringify(sentMessage.components);

        expect(messageJson).toContain(`${(TEST_SCORE_ABOVE_THRESHOLD * 100).toFixed(1)}%`);
      });
    });

    describe('AC #3: Use SectionBuilder for note metadata', () => {
      it('should include author, timestamp, and score in metadata section', async () => {
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

        mockApiClient.checkNoteDuplicate.mockResolvedValueOnce(createMockDuplicateCheckResponse(false));
        mockApiClient.getLastNotePost.mockResolvedValueOnce(createEmptyListResponse());

        mockClient.channels.cache.set('channel-456', mockChannel as any);
        mockChannel.permissionsFor.mockReturnValue(
          new PermissionsBitField(['SendMessages', 'CreatePublicThreads'])
        );
        (mockClient.channels.fetch as any).mockResolvedValue(mockChannel);

        mockApiClient.getNote.mockResolvedValueOnce(createMockNoteJSONAPIResponse({ summary: 'Test note content' }));

        mockChannel.send.mockResolvedValue({ id: 'reply-789' });
        mockApiClient.recordNotePublisher.mockResolvedValue(undefined);

        await notePublisherService.handleScoreUpdate(event);

        const sentMessage = (mockChannel.send as jest.Mock).mock.calls[0][0] as { components?: any[] };
        const messageJson = JSON.stringify(sentMessage.components);

        expect(messageJson).toContain('standard');
        expect(messageJson).toContain('10 ratings');
      });
    });

    describe('AC #4: Apply accent color based on score', () => {
      it('should use HELPFUL color for high confidence published notes', async () => {
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

        mockApiClient.checkNoteDuplicate.mockResolvedValueOnce(createMockDuplicateCheckResponse(false));
        mockApiClient.getLastNotePost.mockResolvedValueOnce(createEmptyListResponse());

        mockClient.channels.cache.set('channel-456', mockChannel as any);
        mockChannel.permissionsFor.mockReturnValue(
          new PermissionsBitField(['SendMessages', 'CreatePublicThreads'])
        );
        (mockClient.channels.fetch as any).mockResolvedValue(mockChannel);

        mockApiClient.getNote.mockResolvedValueOnce(createMockNoteJSONAPIResponse({ summary: 'Test note content' }));

        mockChannel.send.mockResolvedValue({ id: 'reply-789' });
        mockApiClient.recordNotePublisher.mockResolvedValue(undefined);

        await notePublisherService.handleScoreUpdate(event);

        const sentMessage = (mockChannel.send as jest.Mock).mock.calls[0][0] as { components?: any[] };
        const messageJson = JSON.stringify(sentMessage.components);

        expect(messageJson).toContain(V2_COLORS.HELPFUL.toString());
      });
    });

    describe('AC #5: Add MediaGalleryBuilder support for image references', () => {
      it('should include media gallery when note has image URLs', async () => {
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

        mockApiClient.checkNoteDuplicate.mockResolvedValueOnce(createMockDuplicateCheckResponse(false));
        mockApiClient.getLastNotePost.mockResolvedValueOnce(createEmptyListResponse());

        mockClient.channels.cache.set('channel-456', mockChannel as any);
        mockChannel.permissionsFor.mockReturnValue(
          new PermissionsBitField(['SendMessages', 'CreatePublicThreads'])
        );
        (mockClient.channels.fetch as any).mockResolvedValue(mockChannel);

        mockApiClient.getNote.mockResolvedValueOnce(createMockNoteJSONAPIResponse({
          summary: 'Test note with image',
          imageUrls: ['https://example.com/image1.png', 'https://example.com/image2.jpg'],
        }));

        mockChannel.send.mockResolvedValue({ id: 'reply-789' });
        mockApiClient.recordNotePublisher.mockResolvedValue(undefined);

        await notePublisherService.handleScoreUpdate(event);

        const sentMessage = (mockChannel.send as jest.Mock).mock.calls[0][0] as { components?: any[] };
        const messageJson = JSON.stringify(sentMessage.components);

        expect(messageJson).toContain('"type":12');
        expect(messageJson).toContain('https://example.com/image1.png');
      });

      it('should not include media gallery when note has no images', async () => {
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

        mockApiClient.checkNoteDuplicate.mockResolvedValueOnce(createMockDuplicateCheckResponse(false));
        mockApiClient.getLastNotePost.mockResolvedValueOnce(createEmptyListResponse());

        mockClient.channels.cache.set('channel-456', mockChannel as any);
        mockChannel.permissionsFor.mockReturnValue(
          new PermissionsBitField(['SendMessages', 'CreatePublicThreads'])
        );
        (mockClient.channels.fetch as any).mockResolvedValue(mockChannel);

        mockApiClient.getNote.mockResolvedValueOnce(createMockNoteJSONAPIResponse({ summary: 'Test note without images' }));

        mockChannel.send.mockResolvedValue({ id: 'reply-789' });
        mockApiClient.recordNotePublisher.mockResolvedValue(undefined);

        await notePublisherService.handleScoreUpdate(event);

        const sentMessage = (mockChannel.send as jest.Mock).mock.calls[0][0] as { components?: any[] };
        const messageJson = JSON.stringify(sentMessage.components);

        expect(messageJson).not.toContain('"type":12');
      });
    });

    describe('AC #6: Apply MessageFlags.IsComponentsV2', () => {
      it('should include IsComponentsV2 flag in message options', async () => {
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

        mockApiClient.checkNoteDuplicate.mockResolvedValueOnce(createMockDuplicateCheckResponse(false));
        mockApiClient.getLastNotePost.mockResolvedValueOnce(createEmptyListResponse());

        mockClient.channels.cache.set('channel-456', mockChannel as any);
        mockChannel.permissionsFor.mockReturnValue(
          new PermissionsBitField(['SendMessages', 'CreatePublicThreads'])
        );
        (mockClient.channels.fetch as any).mockResolvedValue(mockChannel);

        mockApiClient.getNote.mockResolvedValueOnce(createMockNoteJSONAPIResponse({ summary: 'Test note content' }));

        mockChannel.send.mockResolvedValue({ id: 'reply-789' });
        mockApiClient.recordNotePublisher.mockResolvedValue(undefined);

        await notePublisherService.handleScoreUpdate(event);

        const sentMessage = (mockChannel.send as jest.Mock).mock.calls[0][0] as {
          flags?: number;
        };

        expect(sentMessage.flags).toBeDefined();
        expect((sentMessage.flags! & MessageFlags.IsComponentsV2) !== 0).toBe(true);
      });
    });

    describe('force-published notes', () => {
      it('should use different header for force-published notes', async () => {
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
          metadata: {
            force_published: true,
            admin_username: 'TestAdmin',
            force_published_at: new Date().toISOString(),
          },
        };

        mockApiClient.checkNoteDuplicate.mockResolvedValueOnce(createMockDuplicateCheckResponse(false));
        mockApiClient.getLastNotePost.mockResolvedValueOnce(createEmptyListResponse());

        mockClient.channels.cache.set('channel-456', mockChannel as any);
        mockChannel.permissionsFor.mockReturnValue(
          new PermissionsBitField(['SendMessages', 'CreatePublicThreads'])
        );
        (mockClient.channels.fetch as any).mockResolvedValue(mockChannel);

        mockApiClient.getNote.mockResolvedValueOnce(createMockNoteJSONAPIResponse({ summary: 'Force published note' }));

        mockChannel.send.mockResolvedValue({ id: 'reply-789' });
        mockApiClient.recordNotePublisher.mockResolvedValue(undefined);

        await notePublisherService.handleScoreUpdate(event);

        const sentMessage = (mockChannel.send as jest.Mock).mock.calls[0][0] as { components?: any[] };
        const messageJson = JSON.stringify(sentMessage.components);

        expect(messageJson).toContain('Admin Published');
        expect(messageJson).toContain('TestAdmin');
      });
    });
  });

  describe('recordNotePublisher UUID resolution (task-851 AC #4)', () => {
    beforeEach(() => {
      mockConfigService.getDefaultThreshold.mockReturnValue(TEST_SCORE_THRESHOLD);
      mockConfigService.getConfig.mockResolvedValue({
        guildId: 'guild-123',
        enabled: true,
        threshold: TEST_SCORE_THRESHOLD,
      });
      mockResolveCommunityServerId.mockClear();
    });

    it('should resolve Discord snowflake to UUID before calling recordNotePublisher', async () => {
      const discordSnowflake = '1234567890123456789';
      const resolvedUUID = '550e8400-e29b-41d4-a716-446655440000';

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
        community_server_id: discordSnowflake,
      };

      mockApiClient.checkNoteDuplicate.mockResolvedValueOnce(createMockDuplicateCheckResponse(false));
      mockApiClient.getLastNotePost.mockResolvedValueOnce(createEmptyListResponse());
      mockResolveCommunityServerId.mockResolvedValueOnce(resolvedUUID);

      mockClient.channels.cache.set('channel-456', mockChannel as any);
      mockChannel.permissionsFor.mockReturnValue(
        new PermissionsBitField(['SendMessages', 'CreatePublicThreads'])
      );
      (mockClient.channels.fetch as any).mockResolvedValue(mockChannel);

      mockApiClient.getNote.mockResolvedValueOnce(createMockNoteJSONAPIResponse({ summary: 'Test note content' }));

      mockChannel.send.mockResolvedValue({ id: 'reply-789' });
      mockApiClient.recordNotePublisher.mockResolvedValue(undefined);

      await notePublisherService.handleScoreUpdate(event);

      expect(mockResolveCommunityServerId).toHaveBeenCalledWith(discordSnowflake);
      expect(mockApiClient.recordNotePublisher).toHaveBeenCalledWith(
        expect.objectContaining({
          guildId: resolvedUUID,
        })
      );
    });

    it('should use guildId directly when it is already a UUID', async () => {
      const existingUUID = '550e8400-e29b-41d4-a716-446655440000';

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
        community_server_id: existingUUID,
      };

      mockApiClient.checkNoteDuplicate.mockResolvedValueOnce(createMockDuplicateCheckResponse(false));
      mockApiClient.getLastNotePost.mockResolvedValueOnce(createEmptyListResponse());

      mockClient.channels.cache.set('channel-456', mockChannel as any);
      mockChannel.permissionsFor.mockReturnValue(
        new PermissionsBitField(['SendMessages', 'CreatePublicThreads'])
      );
      (mockClient.channels.fetch as any).mockResolvedValue(mockChannel);

      mockApiClient.getNote.mockResolvedValueOnce(createMockNoteJSONAPIResponse({ summary: 'Test note content' }));

      mockChannel.send.mockResolvedValue({ id: 'reply-789' });
      mockApiClient.recordNotePublisher.mockResolvedValue(undefined);

      await notePublisherService.handleScoreUpdate(event);

      expect(mockResolveCommunityServerId).not.toHaveBeenCalled();
      expect(mockApiClient.recordNotePublisher).toHaveBeenCalledWith(
        expect.objectContaining({
          guildId: existingUUID,
        })
      );
    });
  });
});
