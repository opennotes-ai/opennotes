import { jest } from '@jest/globals';
import { PermissionsBitField } from 'discord.js';
import type { NotePublisherService as NotePublisherServiceType } from '../../src/services/NotePublisherService.js';
import type { NoteContextService } from '../../src/services/NoteContextService.js';
import type { NotePublisherConfigService } from '../../src/services/NotePublisherConfigService.js';
import type { NatsSubscriber as NatsSubscriberType } from '../../src/events/NatsSubscriber.js';
import type { MockNatsServer as MockNatsServerType } from '../utils/mock-nats-server.js';
import { TEST_SCORE_THRESHOLD, TEST_SCORE_ABOVE_THRESHOLD } from '../test-constants.js';

const mockLogger = {
  debug: jest.fn<(...args: unknown[]) => void>((...args) => console.log('[DEBUG]', ...args)),
  info: jest.fn<(...args: unknown[]) => void>((...args) => console.log('[INFO]', ...args)),
  warn: jest.fn<(...args: unknown[]) => void>((...args) => console.warn('[WARN]', ...args)),
  error: jest.fn<(...args: unknown[]) => void>((...args) => console.error('[ERROR]', ...args)),
};

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

const natsAvailable = await checkNatsAvailability();
const SKIP_NATS_TESTS =
  process.env.CI === 'true' || process.env.SKIP_NATS_TESTS === 'true' || !natsAvailable;

if (!natsAvailable && process.env.CI !== 'true') {
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
      authorId: 'user-123',
    });
    mockNoteContextService.storeNoteContext.mockResolvedValue(undefined);

    mockConfigService.getDefaultThreshold.mockReturnValue(TEST_SCORE_THRESHOLD);
    mockConfigService.getConfig.mockResolvedValue({
      guildId: 'guild-123',
      enabled: true,
      threshold: TEST_SCORE_THRESHOLD,
    });

    mockApiClient.checkNoteDuplicate.mockResolvedValue({ exists: false });
    mockApiClient.getLastNotePost.mockRejectedValue(new Error('404'));
    mockApiClient.getNote.mockResolvedValue({ summary: 'Default note content' });
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

      mockApiClient.checkNoteDuplicate.mockResolvedValueOnce({ exists: false });
      mockApiClient.getLastNotePost.mockRejectedValueOnce(new Error('404'));
      mockApiClient.getNote.mockResolvedValueOnce({ summary: 'This is a helpful community note' });
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
      expect(sentMessages[0].content).toContain('🤖');
      expect(sentMessages[0].content).toContain(`${(TEST_SCORE_ABOVE_THRESHOLD * 100).toFixed(1)}%`);
      expect(sentMessages[0].content).toContain('standard');
      expect(sentMessages[0].content).toContain('This is a helpful community note');
    }, 10000);

    it('should properly use message references for threaded replies', async () => {
      const event = createBaseScoreEvent({
        original_message_id: 'msg-original-123',
      });

      mockApiClient.checkNoteDuplicate.mockResolvedValueOnce({ exists: false });
      mockApiClient.getLastNotePost.mockRejectedValueOnce(new Error('404'));
      mockApiClient.getNote.mockResolvedValueOnce({ summary: 'Note content' });
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
          content: expect.any(String),
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

      mockApiClient.checkNoteDuplicate.mockResolvedValueOnce({ exists: true, auto_post_id: 5 });

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
      mockApiClient.checkNoteDuplicate.mockResolvedValueOnce({ exists: false });
      mockApiClient.getLastNotePost.mockResolvedValueOnce({ posted_at: twoMinutesAgo.toISOString() });

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

      mockApiClient.checkNoteDuplicate.mockResolvedValueOnce({ exists: false });
      mockApiClient.getLastNotePost.mockRejectedValueOnce(new Error('404'));

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

      mockApiClient.checkNoteDuplicate.mockResolvedValueOnce({ exists: false });
      mockApiClient.getLastNotePost.mockRejectedValueOnce(new Error('404'));

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

      mockApiClient.checkNoteDuplicate.mockResolvedValueOnce({ exists: false });
      mockApiClient.getLastNotePost.mockRejectedValueOnce(new Error('404'));

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

      mockApiClient.checkNoteDuplicate.mockResolvedValueOnce({ exists: false });
      mockApiClient.getLastNotePost.mockRejectedValueOnce(new Error('404'));

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
