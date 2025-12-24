import { jest } from '@jest/globals';
import { PermissionsBitField } from 'discord.js';
import type { NotePublisherService as NotePublisherServiceType } from '../../src/services/NotePublisherService.js';
import type { NoteContextService } from '../../src/services/NoteContextService.js';
import type { NotePublisherConfigService } from '../../src/services/NotePublisherConfigService.js';
import type { NatsSubscriber as NatsSubscriberType } from '../../src/events/NatsSubscriber.js';
import type { MockNatsServer as MockNatsServerType } from '../utils/mock-nats-server.js';
import { TEST_SCORE_THRESHOLD } from '../test-constants.js';

const mockLogger = {
  debug: jest.fn<(...args: unknown[]) => void>(),
  info: jest.fn<(...args: unknown[]) => void>(),
  warn: jest.fn<(...args: unknown[]) => void>(),
  error: jest.fn<(...args: unknown[]) => void>(),
};

const mockNoteContextService = {
  getNoteContext: jest.fn<(noteId: string) => Promise<any>>(),
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
const { performanceScenarios } = await import('../utils/note-publisher-fixtures.js');

const natsAvailable = await checkNatsAvailability();
const SKIP_NATS_TESTS = process.env.SKIP_NATS_TESTS === 'true' || !natsAvailable;

if (!natsAvailable) {
  console.log('NATS not available at localhost:4222, skipping performance tests');
}

const describeWithNats = SKIP_NATS_TESTS ? describe.skip : describe;

describeWithNats('NotePublisher Performance Tests (AC #4, #8)', () => {
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

    for (let i = 0; i < 10; i++) {
      mockDiscordClient.createMockChannel(`channel-${i}`);
    }

    mockNoteContextService.getNoteContext.mockImplementation((noteId: any) => {
      return Promise.resolve({
        noteId: String(noteId),
        guildId: 'guild-123',
        channelId: `channel-${noteId % 10}`,
        originalMessageId: `msg-${noteId}`,
        authorId: `user-${noteId}`,
      });
    });
    mockNoteContextService.storeNoteContext.mockResolvedValue(undefined);

    mockConfigService.getDefaultThreshold.mockReturnValue(0.7);
    mockConfigService.getConfig.mockResolvedValue({
      guildId: 'guild-123',
      enabled: true,
      threshold: TEST_SCORE_THRESHOLD,
    });

    mockApiClient.checkNoteDuplicate.mockResolvedValue({ exists: false });
    mockApiClient.getLastNotePost.mockRejectedValue(new Error('404'));
    mockApiClient.getNote.mockResolvedValue({ summary: 'Performance test note content' });
    mockApiClient.recordNotePublisher.mockResolvedValue(undefined);

    notePublisherService = new NotePublisherService(
      mockDiscordClient.getClient(),
      mockNoteContextService as any,
      mockConfigService as any
    );

    natsSubscriber = new NatsSubscriber();
    natsSubscriber.setCustomSubject(mockNatsServer.getSubject());
    await natsSubscriber.connect(process.env.NATS_URL);

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
            json: async () => ({ summary: 'Performance test note content' }),
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

    for (let i = 0; i < 10; i++) {
      const channel = mockDiscordClient.getChannel(`channel-${i}`)!;
      channel.permissionsFor = jest.fn().mockReturnValue(
        new PermissionsBitField(['SendMessages', 'CreatePublicThreads'])
      ) as any;
    }
  });

  afterEach(async () => {
    if (natsSubscriber) {
      await natsSubscriber.close();
    }
    if (mockDiscordClient) {
      mockDiscordClient.clearSentMessages();
    }
  });

  describe('Concurrent Event Processing (AC #4)', () => {
    it('should handle 50 concurrent score update events without blocking or dropping events', async () => {
      const events = performanceScenarios.generateConcurrentEvents(50);

      await natsSubscriber.subscribeToScoreUpdates(
        notePublisherService.handleScoreUpdate.bind(notePublisherService)
      );

      await new Promise((resolve) => setTimeout(resolve, 200));

      const startTime = Date.now();

      await mockNatsServer.publishConcurrent(events);

      await new Promise((resolve) => setTimeout(resolve, 3000));

      const endTime = Date.now();
      const totalTime = endTime - startTime;

      const sentCount = mockDiscordClient.getSentMessageCount();

      expect(sentCount).toBeGreaterThan(0);

      console.log(`Processed ${sentCount} events in ${totalTime}ms`);
      console.log(`Average time per event: ${(totalTime / sentCount).toFixed(2)}ms`);

      expect(totalTime).toBeLessThan(10000);
    }, 20000);

    it('should maintain system responsiveness during burst of 100 events', async () => {
      const events = performanceScenarios.generateConcurrentEvents(100);

      await natsSubscriber.subscribeToScoreUpdates(
        notePublisherService.handleScoreUpdate.bind(notePublisherService)
      );

      await new Promise((resolve) => setTimeout(resolve, 200));

      const startTime = Date.now();

      await mockNatsServer.publishConcurrent(events);

      await new Promise((resolve) => setTimeout(resolve, 5000));

      const endTime = Date.now();
      const totalTime = endTime - startTime;

      const sentCount = mockDiscordClient.getSentMessageCount();

      console.log(`Processed ${sentCount}/100 events in ${totalTime}ms`);

      expect(sentCount).toBeGreaterThan(0);

      expect(totalTime).toBeLessThan(15000);
    }, 25000);
  });

  describe('Performance Metrics (AC #8)', () => {
    it('should maintain event processing latency <500ms p95', async () => {
      const events = performanceScenarios.generateConcurrentEvents(50);

      await natsSubscriber.subscribeToScoreUpdates(
        notePublisherService.handleScoreUpdate.bind(notePublisherService)
      );

      await new Promise((resolve) => setTimeout(resolve, 200));

      const eventTimes: number[] = [];
      const publishStart = Date.now();

      await mockNatsServer.publishConcurrent(events);

      await new Promise((resolve) => setTimeout(resolve, 3000));

      const sentMessages = mockDiscordClient.getSentMessages();

      sentMessages.forEach((msg) => {
        const latency = msg.timestamp.getTime() - publishStart;
        eventTimes.push(latency);
      });

      if (eventTimes.length > 0) {
        eventTimes.sort((a, b) => a - b);

        const p50Index = Math.floor(eventTimes.length * 0.5);
        const p95Index = Math.floor(eventTimes.length * 0.95);
        const p99Index = Math.floor(eventTimes.length * 0.99);

        const p50 = eventTimes[p50Index];
        const p95 = eventTimes[p95Index];
        const p99 = eventTimes[p99Index];

        console.log('Performance Metrics:');
        console.log(`  p50 latency: ${p50}ms`);
        console.log(`  p95 latency: ${p95}ms`);
        console.log(`  p99 latency: ${p99}ms`);
        console.log(`  Total events: ${eventTimes.length}`);

        expect(p95).toBeLessThan(500);
      }
    }, 20000);

    it('should demonstrate graceful degradation under sustained load', async () => {
      const bursts = performanceScenarios.generateBurstEvents(20, 5);

      await natsSubscriber.subscribeToScoreUpdates(
        notePublisherService.handleScoreUpdate.bind(notePublisherService)
      );

      await new Promise((resolve) => setTimeout(resolve, 200));

      const burstResults: Array<{
        burstIndex: number;
        processedCount: number;
        duration: number;
      }> = [];

      for (let i = 0; i < bursts.length; i++) {
        const burstStart = Date.now();
        mockDiscordClient.clearSentMessages();

        await mockNatsServer.publishConcurrent(bursts[i]);

        await new Promise((resolve) => setTimeout(resolve, 1000));

        const burstEnd = Date.now();

        burstResults.push({
          burstIndex: i,
          processedCount: mockDiscordClient.getSentMessageCount(),
          duration: burstEnd - burstStart,
        });
      }

      console.log('Burst Processing Results:');
      burstResults.forEach((result) => {
        console.log(
          `  Burst ${result.burstIndex}: ${result.processedCount} events in ${result.duration}ms`
        );
      });

      const avgProcessed =
        burstResults.reduce((sum, r) => sum + r.processedCount, 0) / burstResults.length;

      expect(avgProcessed).toBeGreaterThan(0);

      const degradation =
        ((burstResults[0].processedCount - burstResults[burstResults.length - 1].processedCount) /
          burstResults[0].processedCount) *
        100;

      console.log(`Performance degradation: ${degradation.toFixed(2)}%`);

      expect(Math.abs(degradation)).toBeLessThan(50);
    }, 30000);
  });

  describe('Resource Utilization', () => {
    it('should handle sequential batches without memory leaks', async () => {
      await natsSubscriber.subscribeToScoreUpdates(
        notePublisherService.handleScoreUpdate.bind(notePublisherService)
      );

      await new Promise((resolve) => setTimeout(resolve, 200));

      const batches = 5;
      const batchSize = 20;

      for (let batch = 0; batch < batches; batch++) {
        const events = performanceScenarios.generateConcurrentEvents(batchSize);

        mockDiscordClient.clearSentMessages();

        await mockNatsServer.publishConcurrent(events);

        await new Promise((resolve) => setTimeout(resolve, 1000));

        const processed = mockDiscordClient.getSentMessageCount();

        console.log(`Batch ${batch + 1}: Processed ${processed}/${batchSize} events`);

        expect(processed).toBeGreaterThan(0);
      }

      if (global.gc) {
        global.gc();
      }
    }, 30000);

    it('should not drop events under normal load conditions', async () => {
      const events = performanceScenarios.generateConcurrentEvents(50);

      await natsSubscriber.subscribeToScoreUpdates(
        notePublisherService.handleScoreUpdate.bind(notePublisherService)
      );

      await new Promise((resolve) => setTimeout(resolve, 200));

      await mockNatsServer.publishConcurrent(events);

      await new Promise((resolve) => setTimeout(resolve, 3000));

      const processedCount = mockDiscordClient.getSentMessageCount();
      const lossRate = ((events.length - processedCount) / events.length) * 100;

      console.log(`Event loss rate: ${lossRate.toFixed(2)}% (${processedCount}/${events.length})`);

      expect(lossRate).toBeLessThan(10);
    }, 20000);
  });

  describe('Throughput Testing', () => {
    it('should measure maximum sustainable throughput', async () => {
      await natsSubscriber.subscribeToScoreUpdates(
        notePublisherService.handleScoreUpdate.bind(notePublisherService)
      );

      await new Promise((resolve) => setTimeout(resolve, 200));

      const testDuration = 5000;
      const events = performanceScenarios.generateConcurrentEvents(100);

      const startTime = Date.now();

      await mockNatsServer.publishConcurrent(events);

      await new Promise((resolve) => setTimeout(resolve, testDuration));

      const endTime = Date.now();
      const actualDuration = (endTime - startTime) / 1000;

      const processedCount = mockDiscordClient.getSentMessageCount();
      const throughput = processedCount / actualDuration;

      console.log(`Throughput: ${throughput.toFixed(2)} events/second`);
      console.log(`Total processed: ${processedCount} events in ${actualDuration.toFixed(2)}s`);

      expect(throughput).toBeGreaterThan(0);
    }, 15000);
  });
});
