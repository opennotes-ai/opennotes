import { jest } from '@jest/globals';
import { PermissionsBitField } from 'discord.js';
import type { NotePublisherService as NotePublisherServiceType } from '../../src/services/NotePublisherService.js';
import type { NoteContextService } from '../../src/services/NoteContextService.js';
import type { NotePublisherConfigService } from '../../src/services/NotePublisherConfigService.js';
import type { NatsSubscriber as NatsSubscriberType } from '../../src/events/NatsSubscriber.js';
import type { MockNatsServer as MockNatsServerType } from '../utils/mock-nats-server.js';
import { TEST_SCORE_THRESHOLD, TEST_SCORE_ABOVE_THRESHOLD } from '../test-constants.js';
import { loggerFactory } from '../factories/index.js';

const mockLogger = loggerFactory.build();

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
  getCommunityServerByPlatformId: jest.fn<() => Promise<any>>(),
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
        author_participant_id: 'user-123',
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

// Helper to create mock JSONAPI list response for checkNoteDuplicate (empty = no duplicate)
function createMockNotePublisherPostsListResponse(posts: any[] = []): any {
  return {
    data: posts,
    jsonapi: { version: '1.1' },
  };
}

const natsAvailable = await checkNatsAvailability();
const SKIP_NATS_TESTS = process.env.SKIP_NATS_TESTS === 'true' || !natsAvailable;

if (!natsAvailable) {
  console.log('NATS not available at localhost:4222, skipping e2e tests');
}

const describeWithNats = SKIP_NATS_TESTS ? describe.skip : describe;

describeWithNats('NotePublisher End-to-End Workflow Test (AC #17)', () => {
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

    mockApiClient.checkNoteDuplicate.mockResolvedValue(createMockNotePublisherPostsListResponse());
    mockApiClient.getLastNotePost.mockResolvedValue(createMockNotePublisherPostsListResponse());
    mockApiClient.getNote.mockResolvedValue(createMockNoteJSONAPIResponse({ summary: 'Default note content' }));
    mockApiClient.recordNotePublisher.mockResolvedValue(undefined);
    mockApiClient.getCommunityServerByPlatformId.mockResolvedValue({
      data: {
        type: 'community-servers',
        id: 'guild-123',
        attributes: {
          platform: 'discord',
          platform_community_server_id: 'guild-123',
          name: 'Test Guild',
          is_active: true,
          is_public: true,
        },
      },
      jsonapi: { version: '1.1' },
    });

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
    if (mockNatsServer) {
      await mockNatsServer.purgeStream();
    }
  });

  describe('Complete Auto-Post Workflow', () => {
    it('should execute full workflow: NATS event → threshold check → duplicate check → permission check → Discord post → database record → audit log', async () => {
      const event = createBaseScoreEvent({
        note_id: 42,
        score: TEST_SCORE_ABOVE_THRESHOLD,
        confidence: 'standard',
        rating_count: 10,
        original_message_id: 'msg-e2e-test',
        channel_id: 'channel-456',
        community_server_id: 'guild-123',
      });

      mockApiClient.checkNoteDuplicate.mockResolvedValueOnce(createMockNotePublisherPostsListResponse());
      mockApiClient.getLastNotePost.mockResolvedValueOnce(createMockNotePublisherPostsListResponse());
      mockApiClient.getNote.mockResolvedValueOnce(createMockNoteJSONAPIResponse({
        id: '42',
        summary: 'This is an excellent community note providing valuable context',
      }));
      mockApiClient.recordNotePublisher.mockResolvedValueOnce(undefined);

      const channel = mockDiscordClient.getChannel('channel-456')!;
      channel.permissionsFor = jest.fn().mockReturnValue(
        new PermissionsBitField(['SendMessages', 'CreatePublicThreads'])
      ) as any;

      await natsSubscriber.subscribeToScoreUpdates(
        notePublisherService.handleScoreUpdate.bind(notePublisherService)
      );

      await new Promise((resolve) => setTimeout(resolve, 100));

      await mockNatsServer.publishScoreUpdate(event);

      await new Promise((resolve) => setTimeout(resolve, 1000));

      expect(mockApiClient.checkNoteDuplicate).toHaveBeenCalledWith('msg-e2e-test', 'guild-123');
      expect(mockApiClient.getLastNotePost).toHaveBeenCalledWith('channel-456', 'guild-123');
      expect(mockApiClient.getNote).toHaveBeenCalledWith('42');

      expect(mockDiscordClient.getSentMessageCount()).toBe(1);
      const sentMessages = mockDiscordClient.getSentMessages();
      const messageJson = JSON.stringify(sentMessages[0].components);
      expect(sentMessages[0].components).toBeDefined();
      expect(messageJson).toContain(`${(TEST_SCORE_ABOVE_THRESHOLD * 100).toFixed(1)}%`);
      expect(messageJson).toContain('standard');
      expect(messageJson).toContain(
        'This is an excellent community note providing valuable context'
      );

      expect(mockApiClient.recordNotePublisher).toHaveBeenCalledWith(
        expect.objectContaining({
          noteId: '42',
          originalMessageId: 'msg-e2e-test',
          scoreAtPost: TEST_SCORE_ABOVE_THRESHOLD,
          channelId: 'channel-456',
          guildId: 'guild-123',
        })
      );
    }, 15000);

    it('should validate each step in sequence and halt on failure', async () => {
      const event = createBaseScoreEvent({
        score: 0.65,
      });

      await natsSubscriber.subscribeToScoreUpdates(
        notePublisherService.handleScoreUpdate.bind(notePublisherService)
      );

      await new Promise((resolve) => setTimeout(resolve, 100));

      await mockNatsServer.publishScoreUpdate(event);

      await new Promise((resolve) => setTimeout(resolve, 500));

      expect(mockApiClient.checkNoteDuplicate).not.toHaveBeenCalled();

      expect(mockDiscordClient.getSentMessageCount()).toBe(0);
    }, 10000);

    it('should handle multi-step workflow with realistic timing', async () => {
      const events = [
        createBaseScoreEvent({
          note_id: 1,
          score: 0.75,
          original_message_id: 'msg-1',
        }),
        createBaseScoreEvent({
          note_id: 2,
          score: 0.80,
          original_message_id: 'msg-2',
        }),
        createBaseScoreEvent({
          note_id: 3,
          score: 0.90,
          original_message_id: 'msg-3',
        }),
      ];

      mockFetch.mockImplementation((url: string | URL | Request, init?: RequestInit) => {
        const urlStr = url.toString();
        const method = init?.method || 'GET';

        if (method === 'GET') {
          if (urlStr.includes('/note-publisher/check-duplicate')) {
            return Promise.resolve({
              ok: true,
              status: 200,
              json: async () => ({ exists: false }),
            } as Response);
          }

          if (urlStr.includes('/note-publisher/last-post')) {
            return Promise.resolve({
              ok: false,
              status: 404,
              json: async () => ({}),
            } as Response);
          }

          if (urlStr.includes('/notes/')) {
            return Promise.resolve({
              ok: true,
              status: 200,
              json: async () => ({
                summary: 'Test note content',
              }),
            } as Response);
          }

          return Promise.resolve({
            ok: false,
            status: 404,
            json: async () => ({}),
          } as Response);
        }

        if (method === 'POST') {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: async () => ({ id: 1 }),
          } as Response);
        }

        return Promise.resolve({
          ok: false,
          status: 404,
          json: async () => ({}),
        } as Response);
      });

      const channel = mockDiscordClient.getChannel('channel-456')!;
      channel.permissionsFor = jest.fn().mockReturnValue(
        new PermissionsBitField(['SendMessages', 'CreatePublicThreads'])
      ) as any;

      await natsSubscriber.subscribeToScoreUpdates(
        notePublisherService.handleScoreUpdate.bind(notePublisherService)
      );

      await new Promise((resolve) => setTimeout(resolve, 100));

      for (const event of events) {
        await mockNatsServer.publishScoreUpdate(event);
        await new Promise((resolve) => setTimeout(resolve, 100));
      }

      await new Promise((resolve) => setTimeout(resolve, 1000));

      expect(mockDiscordClient.getSentMessageCount()).toBeGreaterThan(0);
    }, 15000);
  });

  describe('Workflow Validation Steps', () => {
    it('should verify threshold validation happens before other checks', async () => {
      const event = createBaseScoreEvent({
        score: 0.65,
      });

      await natsSubscriber.subscribeToScoreUpdates(
        notePublisherService.handleScoreUpdate.bind(notePublisherService)
      );

      await new Promise((resolve) => setTimeout(resolve, 100));

      await mockNatsServer.publishScoreUpdate(event);

      await new Promise((resolve) => setTimeout(resolve, 500));

      expect(mockApiClient.checkNoteDuplicate).not.toHaveBeenCalled();
    }, 10000);

    it('should verify duplicate check happens after threshold validation', async () => {
      const event = createBaseScoreEvent({
        score: TEST_SCORE_ABOVE_THRESHOLD,
        confidence: 'standard',
      });

      mockApiClient.checkNoteDuplicate.mockResolvedValueOnce(createMockNotePublisherPostsListResponse([{
        type: 'note-publisher-posts',
        id: '5',
        attributes: { original_message_id: 'msg-123', channel_id: 'channel-456' },
      }]));

      await natsSubscriber.subscribeToScoreUpdates(
        notePublisherService.handleScoreUpdate.bind(notePublisherService)
      );

      await new Promise((resolve) => setTimeout(resolve, 100));

      await mockNatsServer.publishScoreUpdate(event);

      await new Promise((resolve) => setTimeout(resolve, 500));

      expect(mockApiClient.checkNoteDuplicate).toHaveBeenCalled();

      expect(mockDiscordClient.getSentMessageCount()).toBe(0);
    }, 10000);
  });
});
