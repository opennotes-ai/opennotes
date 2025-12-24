import { jest } from '@jest/globals';
import { PermissionsBitField } from 'discord.js';
import type { NotePublisherService as NotePublisherServiceType } from '../../src/services/NotePublisherService.js';
import type { NoteContextService } from '../../src/services/NoteContextService.js';
import type { NotePublisherConfigService } from '../../src/services/NotePublisherConfigService.js';
import type { NatsSubscriber as NatsSubscriberType } from '../../src/events/NatsSubscriber.js';
import type { MockNatsServer as MockNatsServerType } from '../utils/mock-nats-server.js';
import { TEST_SCORE_THRESHOLD } from '../test-constants.js';
import { loggerFactory } from '../factories/index.js';

const mockLogger = loggerFactory.build();

const mockNoteContextServiceClass = jest.fn();
const mockNotePublisherConfigServiceClass = jest.fn();

const mockFetch = jest.fn<typeof fetch>();
global.fetch = mockFetch;

jest.unstable_mockModule('../../src/services/NoteContextService.js', () => ({
  NoteContextService: mockNoteContextServiceClass,
}));

jest.unstable_mockModule('../../src/services/NotePublisherConfigService.js', () => ({
  NotePublisherConfigService: mockNotePublisherConfigServiceClass,
}));

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
}));

const { NotePublisherService } = await import('../../src/services/NotePublisherService.js');
const NoteContextServiceImport = await import('../../src/services/NoteContextService.js');
const NotePublisherConfigServiceImport = await import('../../src/services/NotePublisherConfigService.js');
const { NatsSubscriber } = await import('../../src/events/NatsSubscriber.js');
const { MockNatsServer, checkNatsAvailability } = await import('../utils/mock-nats-server.js');
const { createMockDiscordClient } = await import('../utils/mock-discord.js');
const { createBaseScoreEvent } = await import('../utils/note-publisher-fixtures.js');

const natsAvailable = await checkNatsAvailability();
const SKIP_NATS_TESTS = process.env.SKIP_NATS_TESTS === 'true' || !natsAvailable;

if (!natsAvailable) {
  console.log('NATS not available at localhost:4222, skipping error handling tests');
}

const describeWithNats = SKIP_NATS_TESTS ? describe.skip : describe;

describeWithNats('NotePublisher Error Handling Integration Tests (AC #7)', () => {
  let mockNatsServer: MockNatsServerType;
  let natsSubscriber: NatsSubscriberType;
  let notePublisherService: NotePublisherServiceType;
  let mockDiscordClient: ReturnType<typeof createMockDiscordClient>;
  let mockNoteContextService: jest.Mocked<NoteContextService>;
  let mockConfigService: jest.Mocked<NotePublisherConfigService>;

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
    mockFetch.mockClear();

    mockDiscordClient = createMockDiscordClient();
    mockDiscordClient.createMockChannel('channel-456');

    mockNoteContextService = new NoteContextServiceImport.NoteContextService() as jest.Mocked<NoteContextService>;
    mockConfigService = new NotePublisherConfigServiceImport.NotePublisherConfigService() as jest.Mocked<NotePublisherConfigService>;

    mockConfigService.getDefaultThreshold = jest.fn().mockReturnValue(0.7) as any;
    mockConfigService.getConfig = jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({
      guildId: 'guild-123',
      enabled: true,
      threshold: TEST_SCORE_THRESHOLD,
    });

    notePublisherService = new NotePublisherService(
      mockDiscordClient.getClient(),
      mockNoteContextService,
      mockConfigService
    );

    natsSubscriber = new NatsSubscriber();
    natsSubscriber.setCustomSubject(mockNatsServer.getSubject());
    await natsSubscriber.connect(process.env.NATS_URL);
  });

  afterEach(async () => {
    if (natsSubscriber && natsSubscriber.isConnected()) {
      await natsSubscriber.close();
    }
    if (mockDiscordClient) {
      mockDiscordClient.clearSentMessages();
    }
  });

  describe('NATS Connection Failures', () => {
    it('should handle NATS connection loss gracefully', async () => {
      const event = createBaseScoreEvent();

      await natsSubscriber.subscribeToScoreUpdates(
        notePublisherService.handleScoreUpdate.bind(notePublisherService)
      );

      await natsSubscriber.close();

      try {
        await mockNatsServer.publishScoreUpdate(event);
      } catch {
      }

      expect(mockDiscordClient.getSentMessageCount()).toBe(0);
    }, 10000);

    it('should attempt reconnection on NATS connection failure', async () => {
      const disconnectedSubscriber = new NatsSubscriber();

      await expect(
        disconnectedSubscriber.connect('nats://localhost:9999')
      ).rejects.toThrow();

      await disconnectedSubscriber.close();
    }, 10000);
  });

  describe('Discord API Rate Limits (429)', () => {
    it('should handle Discord rate limit errors gracefully', async () => {
      const event = createBaseScoreEvent();

      mockFetch
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          json: async () => ({ exists: false }),
        } as Response)
        .mockResolvedValueOnce({
          ok: false,
          status: 404,
          json: async () => ({}),
        } as Response)
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          json: async () => ({ content: 'Note content' }),
        } as Response);

      const channel = mockDiscordClient.getChannel('channel-456')!;
      channel.permissionsFor = jest.fn().mockReturnValue(
        new PermissionsBitField(['SendMessages', 'CreatePublicThreads'])
      ) as any;

      mockDiscordClient.simulateRateLimit('channel-456', 1000);

      await natsSubscriber.subscribeToScoreUpdates(
        notePublisherService.handleScoreUpdate.bind(notePublisherService)
      );

      await mockNatsServer.publishScoreUpdate(event);

      await new Promise((resolve) => setTimeout(resolve, 500));

      expect(mockDiscordClient.getSentMessageCount()).toBe(0);
    }, 10000);
  });

  describe('Database Unavailability', () => {
    it('should handle database connection errors when checking duplicates', async () => {
      const event = createBaseScoreEvent();

      mockFetch.mockRejectedValueOnce(
        Object.assign(new Error('Database connection failed'), {
          code: 'ECONNREFUSED',
        })
      );

      await natsSubscriber.subscribeToScoreUpdates(
        notePublisherService.handleScoreUpdate.bind(notePublisherService)
      );

      await mockNatsServer.publishScoreUpdate(event);

      await new Promise((resolve) => setTimeout(resolve, 500));

      expect(mockDiscordClient.getSentMessageCount()).toBe(0);
    }, 10000);

    it('should handle database errors when checking cooldown', async () => {
      const event = createBaseScoreEvent();

      mockFetch
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          json: async () => ({ exists: false }),
        } as Response)
        .mockRejectedValueOnce(
          Object.assign(new Error('Database connection failed'), {
            code: 'ECONNREFUSED',
          })
        );

      await natsSubscriber.subscribeToScoreUpdates(
        notePublisherService.handleScoreUpdate.bind(notePublisherService)
      );

      await mockNatsServer.publishScoreUpdate(event);

      await new Promise((resolve) => setTimeout(resolve, 500));

      expect(mockDiscordClient.getSentMessageCount()).toBe(0);
    }, 10000);
  });

  describe('Deleted Original Messages', () => {
    it('should handle deleted original message gracefully (Discord error 10008)', async () => {
      const event = createBaseScoreEvent();

      mockFetch
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          json: async () => ({ exists: false }),
        } as Response)
        .mockResolvedValueOnce({
          ok: false,
          status: 404,
          json: async () => ({}),
        } as Response)
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          json: async () => ({ content: 'Note content' }),
        } as Response)
        .mockResolvedValue({
          ok: true,
          status: 200,
          json: async () => ({ id: 1 }),
        } as Response);

      const channel = mockDiscordClient.getChannel('channel-456')!;
      channel.permissionsFor = jest.fn().mockReturnValue(
        new PermissionsBitField(['SendMessages', 'CreatePublicThreads'])
      ) as any;

      mockDiscordClient.simulateDeletedMessage('channel-456');

      await natsSubscriber.subscribeToScoreUpdates(
        notePublisherService.handleScoreUpdate.bind(notePublisherService)
      );

      await mockNatsServer.publishScoreUpdate(event);

      await new Promise((resolve) => setTimeout(resolve, 500));

      expect(mockDiscordClient.getSentMessageCount()).toBe(0);
    }, 10000);
  });

  describe('Missing Note Content', () => {
    it('should handle missing note content from backend API', async () => {
      const event = createBaseScoreEvent({
        note_id: 999,
      });

      mockFetch
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          json: async () => ({ exists: false }),
        } as Response)
        .mockResolvedValueOnce({
          ok: false,
          status: 404,
          json: async () => ({}),
        } as Response)
        .mockResolvedValueOnce({
          ok: false,
          status: 404,
          json: async () => ({}),
        } as Response);

      const channel = mockDiscordClient.getChannel('channel-456')!;
      channel.permissionsFor = jest.fn().mockReturnValue(
        new PermissionsBitField(['SendMessages', 'CreatePublicThreads'])
      ) as any;

      await natsSubscriber.subscribeToScoreUpdates(
        notePublisherService.handleScoreUpdate.bind(notePublisherService)
      );

      await mockNatsServer.publishScoreUpdate(event);

      await new Promise((resolve) => setTimeout(resolve, 500));

      expect(mockDiscordClient.getSentMessageCount()).toBe(0);
    }, 10000);
  });

  describe('Network Errors', () => {
    it('should handle network timeout errors', async () => {
      const event = createBaseScoreEvent();

      mockFetch.mockRejectedValueOnce(
        Object.assign(new Error('Network timeout'), {
          code: 'ETIMEDOUT',
        })
      );

      await natsSubscriber.subscribeToScoreUpdates(
        notePublisherService.handleScoreUpdate.bind(notePublisherService)
      );

      await mockNatsServer.publishScoreUpdate(event);

      await new Promise((resolve) => setTimeout(resolve, 500));

      expect(mockDiscordClient.getSentMessageCount()).toBe(0);
    }, 10000);

    it('should handle DNS resolution errors', async () => {
      const event = createBaseScoreEvent();

      mockFetch.mockRejectedValueOnce(
        Object.assign(new Error('DNS lookup failed'), {
          code: 'ENOTFOUND',
        })
      );

      await natsSubscriber.subscribeToScoreUpdates(
        notePublisherService.handleScoreUpdate.bind(notePublisherService)
      );

      await mockNatsServer.publishScoreUpdate(event);

      await new Promise((resolve) => setTimeout(resolve, 500));

      expect(mockDiscordClient.getSentMessageCount()).toBe(0);
    }, 10000);
  });

  describe('Malformed Event Data', () => {
    it('should handle invalid NATS event payloads', async () => {
      await natsSubscriber.subscribeToScoreUpdates(
        notePublisherService.handleScoreUpdate.bind(notePublisherService)
      );

      const invalidEvent = {
        note_id: 'invalid',
        score: 'not-a-number',
      };

      await mockNatsServer.publishScoreUpdate(invalidEvent);

      await new Promise((resolve) => setTimeout(resolve, 500));

      expect(mockDiscordClient.getSentMessageCount()).toBe(0);
    }, 10000);
  });
});
