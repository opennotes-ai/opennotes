import { jest } from '@jest/globals';
import { PermissionsBitField } from 'discord.js';
import type { NotePublisherService as NotePublisherServiceType } from '../../src/services/NotePublisherService.js';
import type { NoteContextService } from '../../src/services/NoteContextService.js';
import type { NotePublisherConfigService } from '../../src/services/NotePublisherConfigService.js';
import type { NatsSubscriber as NatsSubscriberType } from '../../src/events/NatsSubscriber.js';
import type { MockNatsServer as MockNatsServerType } from '../utils/mock-nats-server.js';
import { TEST_SCORE_THRESHOLD, TEST_SCORE_ABOVE_THRESHOLD } from '../test-constants.js';
import { loggerFactory } from '../factories/index.js';

const mockLogger = loggerFactory.build({}, {
  transient: {
    debugImpl: (...args: unknown[]) => console.log('[DEBUG]', ...args),
    infoImpl: (...args: unknown[]) => console.log('[INFO]', ...args),
    warnImpl: (...args: unknown[]) => console.warn('[WARN]', ...args),
    errorImpl: (...args: unknown[]) => console.error('[ERROR]', ...args),
  },
});

const mockNoteContextService = {
  getNoteContext: jest.fn<() => Promise<any>>(),
  storeNoteContext: jest.fn<() => Promise<void>>(),
};

const mockConfigService = {
  getDefaultThreshold: jest.fn<() => number>(),
  getConfig: jest.fn<() => Promise<any>>(),
  setConfig: jest.fn<() => Promise<void>>(),
};

const mockApiClient = {
  checkNoteDuplicate: jest.fn<() => Promise<any>>(),
  getLastNotePost: jest.fn<() => Promise<any>>(),
  getNote: jest.fn<() => Promise<any>>(),
  recordNotePublisher: jest.fn<() => Promise<void>>(),
};

const mockFetch = jest.fn<typeof fetch>();
global.fetch = mockFetch;

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
const { NatsSubscriber } = await import('../../src/events/NatsSubscriber.js');
const { MockNatsServer, checkNatsAvailability } = await import('../utils/mock-nats-server.js');
const { createMockDiscordClient } = await import('../utils/mock-discord.js');
const { createBaseScoreEvent } = await import('../utils/note-publisher-fixtures.js');

// Helper to create mock JSONAPI note response
function createMockNoteJSONAPIResponse(overrides: {
  id?: string;
  summary?: string;
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
      },
    },
    jsonapi: { version: '1.1' },
  };
}

const natsAvailable = await checkNatsAvailability();
const SKIP_NATS_TESTS = process.env.SKIP_NATS_TESTS === 'true' || !natsAvailable;

if (!natsAvailable) {
  console.log('NATS not available at localhost:4222, skipping integration tests');
}

const describeWithNats = SKIP_NATS_TESTS ? describe.skip : describe;

describeWithNats('NotePublisher Integration Tests (AC #16)', () => {
  let mockNatsServer: MockNatsServerType;
  let natsSubscriber: NatsSubscriberType;
  let notePublisherService: NotePublisherServiceType;
  let mockDiscordClient: ReturnType<typeof createMockDiscordClient>;

  beforeAll(async () => {
    mockNatsServer = new MockNatsServer();
    const natsUrl = await mockNatsServer.start(4222);
    process.env.NATS_URL = natsUrl;
  }, 15000);

  afterAll(async () => {
    await mockNatsServer.close();
  });

  beforeEach(async () => {
    jest.clearAllMocks();

    mockDiscordClient = createMockDiscordClient();
    mockDiscordClient.createMockChannel('channel-456');

    mockNoteContextService.getNoteContext.mockResolvedValue({
      noteId: '1',
      originalMessageId: 'msg-123',
      channelId: 'channel-456',
      guildId: 'guild-123',
      authorId: '00000000-0000-0001-aaaa-000000000123',
    });
    mockNoteContextService.storeNoteContext.mockResolvedValue(undefined);

    mockConfigService.getDefaultThreshold.mockReturnValue(TEST_SCORE_THRESHOLD);
    mockConfigService.getConfig.mockResolvedValue({
      guildId: 'guild-123',
      enabled: true,
      threshold: TEST_SCORE_THRESHOLD,
    });

    mockApiClient.checkNoteDuplicate.mockResolvedValue({ data: [], jsonapi: { version: '1.1' } });
    mockApiClient.getLastNotePost.mockResolvedValue({ data: [], jsonapi: { version: '1.1' } });
    mockApiClient.getNote.mockResolvedValue(createMockNoteJSONAPIResponse({ summary: 'Default note content' }));
    mockApiClient.recordNotePublisher.mockResolvedValue(undefined);

    notePublisherService = new NotePublisherService(
      mockDiscordClient.getClient(),
      mockNoteContextService as any,
      mockConfigService as any
    );

    natsSubscriber = new NatsSubscriber();
    natsSubscriber.setCustomSubject(mockNatsServer.getSubject());
    await natsSubscriber.connect(process.env.NATS_URL);
  });

  afterEach(async () => {
    if (natsSubscriber) {
      await natsSubscriber.close();
    }
    if (mockDiscordClient) {
      mockDiscordClient.clearSentMessages();
    }
  });

  describe('NATS Event Flow → NotePublisherService → Discord API', () => {
    it('should receive NATS event and trigger auto-post with proper message formatting', async () => {
      const event = createBaseScoreEvent({
        score: TEST_SCORE_ABOVE_THRESHOLD,
        confidence: 'standard',
      });

      mockApiClient.checkNoteDuplicate.mockResolvedValueOnce({ data: [], jsonapi: { version: '1.1' } });
      mockApiClient.getLastNotePost.mockResolvedValueOnce({ data: [], jsonapi: { version: '1.1' } });
      mockApiClient.getNote.mockResolvedValueOnce(createMockNoteJSONAPIResponse({ summary: 'This is a helpful community note' }));
      mockApiClient.recordNotePublisher.mockResolvedValueOnce(undefined);

      const channel = mockDiscordClient.getChannel('channel-456')!;
      channel.permissionsFor = jest.fn().mockReturnValue(
        new PermissionsBitField(['SendMessages', 'CreatePublicThreads'])
      ) as any;

      console.log('Test: Setting custom subject:', mockNatsServer.getSubject());

      try {
        console.log('Test: Calling subscribeToScoreUpdates...');
        await natsSubscriber.subscribeToScoreUpdates(
          notePublisherService.handleScoreUpdate.bind(notePublisherService)
        );
        console.log('Test: subscribeToScoreUpdates returned');
      } catch (error) {
        console.error('Subscribe error:', error);
        throw error;
      }

      console.log('Test: Waiting 100ms for consumer loop to start...');
      await new Promise((resolve) => setTimeout(resolve, 100));

      try {
        console.log('Test: Publishing event...');
        await mockNatsServer.publishScoreUpdate(event);
        console.log('Test: Event published');
      } catch (error) {
        console.error('Publish error:', error);
        throw error;
      }

      console.log('Test: Waiting 500ms for handler to process...');
      await new Promise((resolve) => setTimeout(resolve, 500));

      console.log('Test: Checking sent messages. Count:', mockDiscordClient.getSentMessageCount());
      expect(mockDiscordClient.getSentMessageCount()).toBe(1);

      const sentMessages = mockDiscordClient.getSentMessages();
      const messageJson = JSON.stringify(sentMessages[0].components);
      expect(sentMessages[0].components).toBeDefined();
      expect(messageJson).toContain(`${(TEST_SCORE_ABOVE_THRESHOLD * 100).toFixed(1)}%`);
      expect(messageJson).toContain('standard');
      expect(messageJson).toContain('This is a helpful community note');
    }, 10000);

    it('should properly use message references for threaded replies', async () => {
      const event = createBaseScoreEvent({
        original_message_id: 'msg-original-123',
      });

      mockApiClient.checkNoteDuplicate.mockResolvedValueOnce({ data: [], jsonapi: { version: '1.1' } });
      mockApiClient.getLastNotePost.mockResolvedValueOnce({ data: [], jsonapi: { version: '1.1' } });
      mockApiClient.getNote.mockResolvedValueOnce(createMockNoteJSONAPIResponse({ summary: 'Note content' }));
      mockApiClient.recordNotePublisher.mockResolvedValue(undefined);

      const channel = mockDiscordClient.getChannel('channel-456')!;
      channel.permissionsFor = jest.fn().mockReturnValue(
        new PermissionsBitField(['SendMessages', 'CreatePublicThreads'])
      ) as any;

      await natsSubscriber.subscribeToScoreUpdates(
        notePublisherService.handleScoreUpdate.bind(notePublisherService)
      );

      await new Promise((resolve) => setTimeout(resolve, 100));

      await mockNatsServer.publishScoreUpdate(event);

      await new Promise((resolve) => setTimeout(resolve, 500));

      expect(channel.send).toHaveBeenCalledWith(
        expect.objectContaining({
          components: expect.any(Array),
          flags: expect.any(Number),
          reply: {
            messageReference: event.original_message_id,
            failIfNotExists: false,
          },
        })
      );
    }, 10000);

    it('should validate threshold and confidence before posting', async () => {
      const lowScoreEvent = createBaseScoreEvent({
        score: 0.65,
        confidence: 'standard',
      });

      await natsSubscriber.subscribeToScoreUpdates(
        notePublisherService.handleScoreUpdate.bind(notePublisherService)
      );

      await mockNatsServer.publishScoreUpdate(lowScoreEvent);

      await new Promise((resolve) => setTimeout(resolve, 500));

      expect(mockDiscordClient.getSentMessageCount()).toBe(0);
    }, 10000);

    it('should validate confidence level before posting', async () => {
      const provisionalEvent = createBaseScoreEvent({
        score: TEST_SCORE_ABOVE_THRESHOLD,
        confidence: 'provisional',
        rating_count: 3,
      });

      await natsSubscriber.subscribeToScoreUpdates(
        notePublisherService.handleScoreUpdate.bind(notePublisherService)
      );

      await mockNatsServer.publishScoreUpdate(provisionalEvent);

      await new Promise((resolve) => setTimeout(resolve, 500));

      expect(mockDiscordClient.getSentMessageCount()).toBe(0);
    }, 10000);
  });

  describe('Duplicate Prevention', () => {
    it('should prevent duplicate auto-posts for same original message', async () => {
      const event = createBaseScoreEvent({
        original_message_id: 'msg-duplicate',
      });

      mockApiClient.checkNoteDuplicate.mockResolvedValueOnce({
        data: [{ type: 'note-publisher-posts', id: '5', attributes: { original_message_id: 'msg-duplicate' } }],
        jsonapi: { version: '1.1' },
      });

      await natsSubscriber.subscribeToScoreUpdates(
        notePublisherService.handleScoreUpdate.bind(notePublisherService)
      );

      await mockNatsServer.publishScoreUpdate(event);

      await new Promise((resolve) => setTimeout(resolve, 500));

      expect(mockDiscordClient.getSentMessageCount()).toBe(0);
    }, 10000);
  });

  describe('Cooldown System', () => {
    it('should enforce 5-minute cooldown between posts in same channel', async () => {
      const event = createBaseScoreEvent();

      const twoMinutesAgo = new Date(Date.now() - 2 * 60 * 1000);
      mockApiClient.checkNoteDuplicate.mockResolvedValueOnce({ data: [], jsonapi: { version: '1.1' } });
      mockApiClient.getLastNotePost.mockResolvedValueOnce({
        data: [{ type: 'note-publisher-posts', id: '1', attributes: { posted_at: twoMinutesAgo.toISOString() } }],
        jsonapi: { version: '1.1' },
      });

      await natsSubscriber.subscribeToScoreUpdates(
        notePublisherService.handleScoreUpdate.bind(notePublisherService)
      );

      await mockNatsServer.publishScoreUpdate(event);

      await new Promise((resolve) => setTimeout(resolve, 500));

      expect(mockDiscordClient.getSentMessageCount()).toBe(0);
    }, 10000);
  });

  describe('Permission Checks', () => {
    it('should skip posting if missing SEND_MESSAGES permission', async () => {
      const event = createBaseScoreEvent();

      mockApiClient.checkNoteDuplicate.mockResolvedValueOnce({ data: [], jsonapi: { version: '1.1' } });
      mockApiClient.getLastNotePost.mockResolvedValueOnce({ data: [], jsonapi: { version: '1.1' } });

      mockDiscordClient.simulatePermissionChange('channel-456', 'SEND_MESSAGES');

      await natsSubscriber.subscribeToScoreUpdates(
        notePublisherService.handleScoreUpdate.bind(notePublisherService)
      );

      await mockNatsServer.publishScoreUpdate(event);

      await new Promise((resolve) => setTimeout(resolve, 500));

      expect(mockDiscordClient.getSentMessageCount()).toBe(0);
    }, 10000);

    it('should skip posting if missing CREATE_PUBLIC_THREADS permission', async () => {
      const event = createBaseScoreEvent();

      mockApiClient.checkNoteDuplicate.mockResolvedValueOnce({ data: [], jsonapi: { version: '1.1' } });
      mockApiClient.getLastNotePost.mockResolvedValueOnce({ data: [], jsonapi: { version: '1.1' } });

      mockDiscordClient.simulatePermissionChange('channel-456', 'CREATE_PUBLIC_THREADS');

      await natsSubscriber.subscribeToScoreUpdates(
        notePublisherService.handleScoreUpdate.bind(notePublisherService)
      );

      await mockNatsServer.publishScoreUpdate(event);

      await new Promise((resolve) => setTimeout(resolve, 500));

      expect(mockDiscordClient.getSentMessageCount()).toBe(0);
    }, 10000);
  });

  describe('Configuration', () => {
    it('should respect server-level auto-post disable setting', async () => {
      const event = createBaseScoreEvent();

      mockApiClient.checkNoteDuplicate.mockResolvedValueOnce({ data: [], jsonapi: { version: '1.1' } });
      mockApiClient.getLastNotePost.mockResolvedValueOnce({ data: [], jsonapi: { version: '1.1' } });

      mockConfigService.getConfig.mockResolvedValueOnce({
        guildId: 'guild-123',
        enabled: false,
        threshold: TEST_SCORE_THRESHOLD,
      });

      await natsSubscriber.subscribeToScoreUpdates(
        notePublisherService.handleScoreUpdate.bind(notePublisherService)
      );

      await mockNatsServer.publishScoreUpdate(event);

      await new Promise((resolve) => setTimeout(resolve, 500));

      expect(mockDiscordClient.getSentMessageCount()).toBe(0);
    }, 10000);

    it('should respect channel-level auto-post disable setting', async () => {
      const event = createBaseScoreEvent();

      mockApiClient.checkNoteDuplicate.mockResolvedValueOnce({ data: [], jsonapi: { version: '1.1' } });
      mockApiClient.getLastNotePost.mockResolvedValueOnce({ data: [], jsonapi: { version: '1.1' } });

      mockConfigService.getConfig.mockResolvedValueOnce({
        guildId: 'guild-123',
        channelId: 'channel-456',
        enabled: false,
        threshold: TEST_SCORE_THRESHOLD,
      });

      await natsSubscriber.subscribeToScoreUpdates(
        notePublisherService.handleScoreUpdate.bind(notePublisherService)
      );

      await mockNatsServer.publishScoreUpdate(event);

      await new Promise((resolve) => setTimeout(resolve, 500));

      expect(mockDiscordClient.getSentMessageCount()).toBe(0);
    }, 10000);
  });
});
