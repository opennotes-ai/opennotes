import { jest, describe, it, expect, beforeEach, afterEach } from '@jest/globals';
import { ChannelType, Collection } from 'discord.js';

const mockLogger = {
  info: jest.fn<(...args: unknown[]) => void>(),
  error: jest.fn<(...args: unknown[]) => void>(),
  warn: jest.fn<(...args: unknown[]) => void>(),
  debug: jest.fn<(...args: unknown[]) => void>(),
};

const mockInitiateBulkScan = jest.fn<(communityServerId: string, days: number) => Promise<{ scan_id: string }>>();

const mockGetBulkScanResults = jest.fn<(scanId: string) => Promise<{
  scan_id: string;
  status: 'completed' | 'failed' | 'pending';
  messages_scanned: number;
  flagged_messages: any[];
}>>();

const mockGetCommunityServerByPlatformId = jest.fn<(platformId: string, platform?: string) => Promise<{
  id: string;
  platform: string;
  platform_id: string;
  name: string;
  is_active: boolean;
}>>();

const mockPublishBulkScanBatch = jest.fn<(subject: string, batch: any) => Promise<void>>();

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
}));

jest.unstable_mockModule('../../src/api-client.js', () => ({
  apiClient: {
    initiateBulkScan: mockInitiateBulkScan,
    getBulkScanResults: mockGetBulkScanResults,
    getCommunityServerByPlatformId: mockGetCommunityServerByPlatformId,
  },
}));

jest.unstable_mockModule('../../src/events/NatsPublisher.js', () => ({
  natsPublisher: {
    publishBulkScanBatch: mockPublishBulkScanBatch,
  },
}));

const {
  executeBulkScan,
  pollForResults,
  truncateContent,
  POLL_TIMEOUT_MS,
  BACKOFF_INITIAL_MS,
  BACKOFF_MULTIPLIER,
  BACKOFF_MAX_MS,
} = await import('../../src/lib/bulk-scan-executor.js');
const { BULK_SCAN_BATCH_SIZE } = await import('../../src/types/bulk-scan.js');

function generateRecentSnowflake(offsetMs: number = 0): string {
  const timestamp = BigInt(Date.now() - offsetMs);
  const DISCORD_EPOCH = BigInt(1420070400000);
  const snowflake = ((timestamp - DISCORD_EPOCH) << BigInt(22)) | BigInt(Math.floor(Math.random() * 4194304));
  return snowflake.toString();
}

function createMockMessage(id: string, content: string, authorId: string = 'user-123') {
  return {
    id,
    content,
    author: {
      id: authorId,
      username: 'testuser',
      bot: false,
    },
    createdAt: new Date(),
    attachments: new Collection(),
    embeds: [],
  };
}

function createMockChannel(channelId: string, messages: Map<string, any>) {
  const messageArray = Array.from(messages.entries());
  let fetchCallCount = 0;

  return {
    id: channelId,
    name: `channel-${channelId}`,
    type: ChannelType.GuildText,
    viewable: true,
    messages: {
      fetch: jest.fn<(opts: any) => Promise<Collection<string, any>>>()
        .mockImplementation(async () => {
          fetchCallCount++;
          if (fetchCallCount === 1) {
            const subset = messageArray.slice(0, Math.min(100, messageArray.length));
            return new Collection(subset);
          }
          return new Collection();
        }),
    },
  };
}

function createMockGuild(channels: Map<string, any>) {
  const channelsWithFilter = new Map(channels);
  (channelsWithFilter as any).filter = (fn: (ch: any) => boolean) => {
    const result = new Map();
    for (const [k, v] of channelsWithFilter) {
      if (fn(v)) result.set(k, v);
    }
    return result;
  };

  return {
    id: 'guild-123',
    name: 'Test Guild',
    channels: {
      cache: channelsWithFilter,
    },
  };
}

describe('bulk-scan-executor', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers({ advanceTimers: true });

    mockGetCommunityServerByPlatformId.mockResolvedValue({
      id: 'community-uuid-123',
      platform: 'discord',
      platform_id: 'guild-123',
      name: 'Test Guild',
      is_active: true,
    });
    mockInitiateBulkScan.mockResolvedValue({ scan_id: 'test-scan-123' });
    mockGetBulkScanResults.mockResolvedValue({
      scan_id: 'test-scan-123',
      status: 'completed',
      messages_scanned: 100,
      flagged_messages: [],
    });
    mockPublishBulkScanBatch.mockResolvedValue(undefined);
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  describe('executeBulkScan - NATS failure handling', () => {
    it('should track failed batches when NATS publish fails for some batches', async () => {
      const messages = new Map();
      for (let i = 0; i < 50; i++) {
        const id = generateRecentSnowflake(i * 1000);
        messages.set(id, createMockMessage(id, `Message ${i}`));
      }

      const channel = createMockChannel('ch-1', messages);
      const guild = createMockGuild(new Map([['ch-1', channel]]));

      mockPublishBulkScanBatch.mockRejectedValueOnce(new Error('NATS connection timeout'));

      const result = await executeBulkScan({
        guild: guild as any,
        days: 7,
        initiatorId: 'user-123',
        errorId: 'err-test-123',
      });

      expect(result.status).toBe('failed');
      expect(result.failedBatches).toBe(1);
      expect(result.batchesPublished).toBe(0);
    });

    it('should return partial status when some batches fail and some succeed', async () => {
      const ch1Messages = new Map();
      for (let i = 0; i < 100; i++) {
        const id = generateRecentSnowflake(i * 1000);
        ch1Messages.set(id, createMockMessage(id, `Message ${i}`));
      }

      const ch2Messages = new Map();
      for (let i = 0; i < 100; i++) {
        const id = generateRecentSnowflake((i + 200) * 1000);
        ch2Messages.set(id, createMockMessage(id, `Message ${i + 200}`));
      }

      const channel1 = createMockChannel('ch-1', ch1Messages);
      const channel2 = createMockChannel('ch-2', ch2Messages);
      const guild = createMockGuild(new Map([['ch-1', channel1], ['ch-2', channel2]]));

      mockPublishBulkScanBatch
        .mockResolvedValueOnce(undefined)
        .mockRejectedValueOnce(new Error('NATS error'));

      const result = await executeBulkScan({
        guild: guild as any,
        days: 7,
        initiatorId: 'user-123',
        errorId: 'err-test-123',
      });

      expect(result.status).toBe('partial');
      expect(result.failedBatches).toBe(1);
      expect(result.batchesPublished).toBe(1);
    });

    it('should include warning message when scan completes with partial results', async () => {
      const ch1Messages = new Map();
      for (let i = 0; i < 100; i++) {
        const id = generateRecentSnowflake(i * 1000);
        ch1Messages.set(id, createMockMessage(id, `Message ${i}`));
      }

      const ch2Messages = new Map();
      for (let i = 0; i < 100; i++) {
        const id = generateRecentSnowflake((i + 200) * 1000);
        ch2Messages.set(id, createMockMessage(id, `Message ${i + 200}`));
      }

      const channel1 = createMockChannel('ch-1', ch1Messages);
      const channel2 = createMockChannel('ch-2', ch2Messages);
      const guild = createMockGuild(new Map([['ch-1', channel1], ['ch-2', channel2]]));

      mockPublishBulkScanBatch
        .mockResolvedValueOnce(undefined)
        .mockRejectedValueOnce(new Error('NATS error'));

      const result = await executeBulkScan({
        guild: guild as any,
        days: 7,
        initiatorId: 'user-123',
        errorId: 'err-test-123',
      });

      expect(result.warningMessage).toBeDefined();
      expect(result.warningMessage).toContain('incomplete');
    });

    it('should log failed batch details for debugging', async () => {
      const messages = new Map();
      for (let i = 0; i < 50; i++) {
        const id = generateRecentSnowflake(i * 1000);
        messages.set(id, createMockMessage(id, `Message ${i}`));
      }

      const channel = createMockChannel('ch-1', messages);
      const guild = createMockGuild(new Map([['ch-1', channel]]));

      const natsError = new Error('NATS connection timeout');
      mockPublishBulkScanBatch.mockRejectedValueOnce(natsError);

      await executeBulkScan({
        guild: guild as any,
        days: 7,
        initiatorId: 'user-123',
        errorId: 'err-test-123',
      });

      expect(mockLogger.warn).toHaveBeenCalledWith(
        expect.stringContaining('Failed to publish batch'),
        expect.objectContaining({
          batchNumber: expect.any(Number),
          scanId: 'test-scan-123',
        })
      );
    });

    it('should return completed status when all batches succeed', async () => {
      const messages = new Map();
      for (let i = 0; i < 50; i++) {
        const id = generateRecentSnowflake(i * 1000);
        messages.set(id, createMockMessage(id, `Message ${i}`));
      }

      const channel = createMockChannel('ch-1', messages);
      const guild = createMockGuild(new Map([['ch-1', channel]]));

      mockPublishBulkScanBatch.mockResolvedValue(undefined);

      const result = await executeBulkScan({
        guild: guild as any,
        days: 7,
        initiatorId: 'user-123',
        errorId: 'err-test-123',
      });

      expect(result.status).toBe('completed');
      expect(result.failedBatches).toBe(0);
      expect(result.warningMessage).toBeUndefined();
    });

    it('should return failed status when all NATS publish attempts fail', async () => {
      const messages = new Map();
      for (let i = 0; i < 50; i++) {
        const id = generateRecentSnowflake(i * 1000);
        messages.set(id, createMockMessage(id, `Message ${i}`));
      }

      const channel = createMockChannel('ch-1', messages);
      const guild = createMockGuild(new Map([['ch-1', channel]]));

      mockPublishBulkScanBatch.mockRejectedValue(new Error('NATS permanently down'));

      const result = await executeBulkScan({
        guild: guild as any,
        days: 7,
        initiatorId: 'user-123',
        errorId: 'err-test-123',
      });

      expect(result.status).toBe('failed');
      expect(result.failedBatches).toBeGreaterThan(0);
      expect(result.batchesPublished).toBe(0);
    });

    it('should correctly count published vs failed batches across multiple channels', async () => {
      const channels = new Map();
      for (let c = 0; c < 4; c++) {
        const chMessages = new Map();
        for (let i = 0; i < 100; i++) {
          const id = generateRecentSnowflake((c * 200 + i) * 1000);
          chMessages.set(id, createMockMessage(id, `Ch${c} Message ${i}`));
        }
        channels.set(`ch-${c}`, createMockChannel(`ch-${c}`, chMessages));
      }

      const guild = createMockGuild(channels);

      mockPublishBulkScanBatch
        .mockResolvedValueOnce(undefined)
        .mockRejectedValueOnce(new Error('Fail'))
        .mockResolvedValueOnce(undefined)
        .mockRejectedValueOnce(new Error('Fail'));

      const result = await executeBulkScan({
        guild: guild as any,
        days: 7,
        initiatorId: 'user-123',
        errorId: 'err-test-123',
      });

      expect(result.batchesPublished).toBe(2);
      expect(result.failedBatches).toBe(2);
      expect(result.status).toBe('partial');
    });
  });

  describe('executeBulkScan - progress callback behavior', () => {
    it('should not block scan execution when progress callback is slow', async () => {
      const messages = new Map();
      for (let i = 0; i < 10; i++) {
        const id = generateRecentSnowflake(i * 1000);
        messages.set(id, createMockMessage(id, `Message ${i}`));
      }

      const channels = new Map();
      for (let c = 0; c < 3; c++) {
        channels.set(`ch-${c}`, createMockChannel(`ch-${c}`, messages));
      }

      const guild = createMockGuild(channels);

      const slowCallback = jest.fn<(progress: any) => Promise<void>>()
        .mockImplementation(async () => {
          await new Promise(resolve => setTimeout(resolve, 500));
        });

      const startTime = Date.now();

      const resultPromise = executeBulkScan({
        guild: guild as any,
        days: 7,
        initiatorId: 'user-123',
        errorId: 'err-test-123',
        progressCallback: slowCallback,
      });

      await jest.advanceTimersByTimeAsync(100);
      const result = await resultPromise;

      const duration = Date.now() - startTime;

      expect(result.status).toBe('completed');
      expect(slowCallback).toHaveBeenCalled();
      expect(duration).toBeLessThan(500);
    });

    it('should continue scan when progress callback throws an error', async () => {
      const messages = new Map();
      for (let i = 0; i < 10; i++) {
        const id = generateRecentSnowflake(i * 1000);
        messages.set(id, createMockMessage(id, `Message ${i}`));
      }

      const channel = createMockChannel('ch-1', messages);
      const guild = createMockGuild(new Map([['ch-1', channel]]));

      const errorCallback = jest.fn<(progress: any) => Promise<void>>()
        .mockRejectedValue(new Error('Progress callback failed'));

      const result = await executeBulkScan({
        guild: guild as any,
        days: 7,
        initiatorId: 'user-123',
        errorId: 'err-test-123',
        progressCallback: errorCallback,
      });

      expect(result.status).toBe('completed');
      expect(errorCallback).toHaveBeenCalled();
    });

    it('should log warning when progress callback fails', async () => {
      const messages = new Map();
      for (let i = 0; i < 10; i++) {
        const id = generateRecentSnowflake(i * 1000);
        messages.set(id, createMockMessage(id, `Message ${i}`));
      }

      const channel = createMockChannel('ch-1', messages);
      const guild = createMockGuild(new Map([['ch-1', channel]]));

      const errorCallback = jest.fn<(progress: any) => Promise<void>>()
        .mockRejectedValue(new Error('Discord API error'));

      await executeBulkScan({
        guild: guild as any,
        days: 7,
        initiatorId: 'user-123',
        errorId: 'err-test-123',
        progressCallback: errorCallback,
      });

      await jest.advanceTimersByTimeAsync(10);

      expect(mockLogger.warn).toHaveBeenCalledWith(
        expect.stringContaining('Progress callback failed'),
        expect.objectContaining({
          error: 'Discord API error',
        })
      );
    });

    it('should call progress callback for each channel with correct data', async () => {
      const messages = new Map();
      for (let i = 0; i < 10; i++) {
        const id = generateRecentSnowflake(i * 1000);
        messages.set(id, createMockMessage(id, `Message ${i}`));
      }

      const channels = new Map();
      channels.set('ch-1', createMockChannel('ch-1', messages));
      channels.set('ch-2', createMockChannel('ch-2', messages));

      const guild = createMockGuild(channels);

      const progressCallback = jest.fn<(progress: any) => Promise<void>>()
        .mockResolvedValue(undefined);

      await executeBulkScan({
        guild: guild as any,
        days: 7,
        initiatorId: 'user-123',
        errorId: 'err-test-123',
        progressCallback,
      });

      expect(progressCallback).toHaveBeenCalledTimes(2);

      expect(progressCallback).toHaveBeenCalledWith(
        expect.objectContaining({
          channelsProcessed: 0,
          totalChannels: 2,
          currentChannel: expect.any(String),
        })
      );
    });
  });

  describe('executeBulkScan - basic functionality', () => {
    it('should return empty result for guild with no accessible channels', async () => {
      const guild = createMockGuild(new Map());

      const result = await executeBulkScan({
        guild: guild as any,
        days: 7,
        initiatorId: 'user-123',
        errorId: 'err-test-123',
      });

      expect(result.channelsScanned).toBe(0);
      expect(result.messagesScanned).toBe(0);
      expect(result.status).toBe('completed');
    });

    it('should skip bot messages', async () => {
      const messages = new Map();
      const botMsgId = generateRecentSnowflake(1000);
      const userMsgId = generateRecentSnowflake(2000);
      messages.set(botMsgId, {
        id: botMsgId,
        content: 'Bot message',
        author: { id: 'bot-123', username: 'testbot', bot: true },
        createdAt: new Date(),
        attachments: new Collection(),
        embeds: [],
      });
      messages.set(userMsgId, createMockMessage(userMsgId, 'User message'));

      const channel = createMockChannel('ch-1', messages);
      const guild = createMockGuild(new Map([['ch-1', channel]]));

      await executeBulkScan({
        guild: guild as any,
        days: 7,
        initiatorId: 'user-123',
        errorId: 'err-test-123',
      });

      const publishCalls = mockPublishBulkScanBatch.mock.calls;
      if (publishCalls.length > 0) {
        const batch = publishCalls[0][1];
        expect(batch.messages.every((m: any) => m.author_id !== 'bot-123')).toBe(true);
      }
    });
  });

  describe('executeBulkScan - community server UUID lookup', () => {
    it('should lookup community server by Discord guild ID and use UUID for API calls', async () => {
      const messages = new Map();
      for (let i = 0; i < 10; i++) {
        const id = generateRecentSnowflake(i * 1000);
        messages.set(id, createMockMessage(id, `Message ${i}`));
      }

      const channel = createMockChannel('ch-1', messages);
      const guild = createMockGuild(new Map([['ch-1', channel]]));

      await executeBulkScan({
        guild: guild as any,
        days: 7,
        initiatorId: 'user-123',
        errorId: 'err-test-123',
      });

      expect(mockGetCommunityServerByPlatformId).toHaveBeenCalledWith('guild-123');

      expect(mockInitiateBulkScan).toHaveBeenCalledWith('community-uuid-123', 7);
    });

    it('should use community server UUID in BulkScanBatch', async () => {
      const messages = new Map();
      for (let i = 0; i < 50; i++) {
        const id = generateRecentSnowflake(i * 1000);
        messages.set(id, createMockMessage(id, `Message ${i}`));
      }

      const channel = createMockChannel('ch-1', messages);
      const guild = createMockGuild(new Map([['ch-1', channel]]));

      await executeBulkScan({
        guild: guild as any,
        days: 7,
        initiatorId: 'user-123',
        errorId: 'err-test-123',
      });

      expect(mockPublishBulkScanBatch).toHaveBeenCalled();
      const batch = mockPublishBulkScanBatch.mock.calls[0][1];
      expect(batch.community_server_id).toBe('community-uuid-123');
    });

    it('should use community server UUID in BulkScanMessage objects', async () => {
      const messages = new Map();
      for (let i = 0; i < 10; i++) {
        const id = generateRecentSnowflake(i * 1000);
        messages.set(id, createMockMessage(id, `Message ${i}`));
      }

      const channel = createMockChannel('ch-1', messages);
      const guild = createMockGuild(new Map([['ch-1', channel]]));

      await executeBulkScan({
        guild: guild as any,
        days: 7,
        initiatorId: 'user-123',
        errorId: 'err-test-123',
      });

      expect(mockPublishBulkScanBatch).toHaveBeenCalled();
      const batch = mockPublishBulkScanBatch.mock.calls[0][1];

      for (const message of batch.messages) {
        expect(message.community_server_id).toBe('community-uuid-123');
      }
    });

    it('should fail fast if community server lookup fails', async () => {
      mockGetCommunityServerByPlatformId.mockRejectedValue(new Error('Community server not found'));

      const messages = new Map();
      for (let i = 0; i < 10; i++) {
        const id = generateRecentSnowflake(i * 1000);
        messages.set(id, createMockMessage(id, `Message ${i}`));
      }

      const channel = createMockChannel('ch-1', messages);
      const guild = createMockGuild(new Map([['ch-1', channel]]));

      await expect(executeBulkScan({
        guild: guild as any,
        days: 7,
        initiatorId: 'user-123',
        errorId: 'err-test-123',
      })).rejects.toThrow('Community server not found');

      expect(mockInitiateBulkScan).not.toHaveBeenCalled();
    });
  });

  describe('executeBulkScan - batch structure', () => {
    it('should use batch_number instead of batch_index (1-indexed)', async () => {
      const messages = new Map();
      for (let i = 0; i < 50; i++) {
        const id = generateRecentSnowflake(i * 1000);
        messages.set(id, createMockMessage(id, `Message ${i}`));
      }

      const channel = createMockChannel('ch-1', messages);
      const guild = createMockGuild(new Map([['ch-1', channel]]));

      await executeBulkScan({
        guild: guild as any,
        days: 7,
        initiatorId: 'user-123',
        errorId: 'err-test-123',
      });

      expect(mockPublishBulkScanBatch).toHaveBeenCalled();
      const batch = mockPublishBulkScanBatch.mock.calls[0][1];

      expect(batch.batch_number).toBeDefined();
      expect(batch.batch_number).toBe(1);
      expect(batch.batch_index).toBeUndefined();
    });

    it('should use is_final_batch instead of total_batches', async () => {
      const messages = new Map();
      for (let i = 0; i < 50; i++) {
        const id = generateRecentSnowflake(i * 1000);
        messages.set(id, createMockMessage(id, `Message ${i}`));
      }

      const channel = createMockChannel('ch-1', messages);
      const guild = createMockGuild(new Map([['ch-1', channel]]));

      await executeBulkScan({
        guild: guild as any,
        days: 7,
        initiatorId: 'user-123',
        errorId: 'err-test-123',
      });

      expect(mockPublishBulkScanBatch).toHaveBeenCalled();
      const batch = mockPublishBulkScanBatch.mock.calls[0][1];

      expect(batch.is_final_batch).toBeDefined();
      expect(typeof batch.is_final_batch).toBe('boolean');
      expect(batch.total_batches).toBeUndefined();
    });

    it('should mark final batch correctly when all messages fit in one batch', async () => {
      const messages = new Map();
      for (let i = 0; i < 50; i++) {
        const id = generateRecentSnowflake(i * 1000);
        messages.set(id, createMockMessage(id, `Message ${i}`));
      }

      const channel = createMockChannel('ch-1', messages);
      const guild = createMockGuild(new Map([['ch-1', channel]]));

      await executeBulkScan({
        guild: guild as any,
        days: 7,
        initiatorId: 'user-123',
        errorId: 'err-test-123',
      });

      expect(mockPublishBulkScanBatch).toHaveBeenCalledTimes(1);
      const batch = mockPublishBulkScanBatch.mock.calls[0][1];
      expect(batch.is_final_batch).toBe(true);
    });

    it('should have batch_number increment for multiple batches', async () => {
      const ch1Messages = new Map();
      for (let i = 0; i < 100; i++) {
        const id = generateRecentSnowflake(i * 1000);
        ch1Messages.set(id, createMockMessage(id, `Message ${i}`));
      }

      const ch2Messages = new Map();
      for (let i = 0; i < 100; i++) {
        const id = generateRecentSnowflake((i + 200) * 1000);
        ch2Messages.set(id, createMockMessage(id, `Message ${i + 200}`));
      }

      const channel1 = createMockChannel('ch-1', ch1Messages);
      const channel2 = createMockChannel('ch-2', ch2Messages);
      const guild = createMockGuild(new Map([['ch-1', channel1], ['ch-2', channel2]]));

      await executeBulkScan({
        guild: guild as any,
        days: 7,
        initiatorId: 'user-123',
        errorId: 'err-test-123',
      });

      expect(mockPublishBulkScanBatch).toHaveBeenCalledTimes(2);

      const batch1 = mockPublishBulkScanBatch.mock.calls[0][1];
      const batch2 = mockPublishBulkScanBatch.mock.calls[1][1];

      expect(batch1.batch_number).toBe(1);
      expect(batch1.is_final_batch).toBe(false);

      expect(batch2.batch_number).toBe(2);
      expect(batch2.is_final_batch).toBe(true);
    });
  });

  describe('exponential backoff configuration', () => {
    it('should export backoff configuration constants', () => {
      expect(BACKOFF_INITIAL_MS).toBe(1000);
      expect(BACKOFF_MULTIPLIER).toBe(2);
      expect(BACKOFF_MAX_MS).toBe(30000);
    });

    it('should use exponential backoff timing on consecutive polls', async () => {
      const pollDelays: number[] = [];
      let pollCount = 0;

      mockGetBulkScanResults
        .mockImplementation(async () => {
          pollCount++;
          if (pollCount < 5) {
            return {
              scan_id: 'test-scan-backoff',
              status: 'pending' as const,
              messages_scanned: 0,
              flagged_messages: [],
            };
          }
          return {
            scan_id: 'test-scan-backoff',
            status: 'completed' as const,
            messages_scanned: 100,
            flagged_messages: [],
          };
        });

      const originalSetTimeout = global.setTimeout;
      const setTimeoutSpy = jest.spyOn(global, 'setTimeout')
        .mockImplementation((fn, delay) => {
          if (typeof delay === 'number' && delay >= BACKOFF_INITIAL_MS) {
            pollDelays.push(delay);
          }
          return originalSetTimeout(fn, 0);
        });

      await pollForResults('test-scan-backoff', 'err-test');

      setTimeoutSpy.mockRestore();

      expect(pollDelays.length).toBeGreaterThanOrEqual(3);
      expect(pollDelays[0]).toBe(BACKOFF_INITIAL_MS);
      expect(pollDelays[1]).toBe(BACKOFF_INITIAL_MS * BACKOFF_MULTIPLIER);
      expect(pollDelays[2]).toBe(BACKOFF_INITIAL_MS * BACKOFF_MULTIPLIER * BACKOFF_MULTIPLIER);
    });

    it('should cap backoff delay at maximum value', async () => {
      let pollCount = 0;

      mockGetBulkScanResults
        .mockImplementation(async () => {
          pollCount++;
          if (pollCount < 10) {
            return {
              scan_id: 'test-scan-max',
              status: 'pending' as const,
              messages_scanned: 0,
              flagged_messages: [],
            };
          }
          return {
            scan_id: 'test-scan-max',
            status: 'completed' as const,
            messages_scanned: 100,
            flagged_messages: [],
          };
        });

      const pollDelays: number[] = [];
      const originalSetTimeout = global.setTimeout;
      const setTimeoutSpy = jest.spyOn(global, 'setTimeout')
        .mockImplementation((fn, delay) => {
          if (typeof delay === 'number' && delay >= BACKOFF_INITIAL_MS) {
            pollDelays.push(delay);
          }
          return originalSetTimeout(fn, 0);
        });

      await pollForResults('test-scan-max', 'err-test');

      setTimeoutSpy.mockRestore();

      const maxObserved = Math.max(...pollDelays);
      expect(maxObserved).toBeLessThanOrEqual(BACKOFF_MAX_MS);
    });
  });

  describe('truncateContent - grapheme-aware truncation', () => {
    it('should truncate basic ASCII text correctly', () => {
      const text = 'Hello, World!';
      expect(truncateContent(text, 5)).toBe('He...');
      expect(truncateContent(text, 13)).toBe('Hello, World!');
      expect(truncateContent(text, 20)).toBe('Hello, World!');
    });

    it('should handle text shorter than or equal to maxLength', () => {
      expect(truncateContent('Hi', 100)).toBe('Hi');
      expect(truncateContent('Hi', 2)).toBe('Hi');
    });

    it('should not break emoji characters when truncating', () => {
      const emoji = '😀';
      expect(emoji.length).toBe(2);

      expect(truncateContent(emoji + 'abc', 3)).toBe('...');
      expect(truncateContent(emoji + 'abc', 4)).toBe('...');
      expect(truncateContent(emoji + 'abc', 5)).toBe(emoji + 'abc');
      expect(truncateContent(emoji + 'ab', 4)).toBe(emoji + 'ab');
      expect(truncateContent(emoji + 'abcd', 5)).toBe(emoji + '...');
    });

    it('should handle family emoji (multi-codepoint grapheme) as single unit', () => {
      const familyEmoji = '👨‍👩‍👧‍👦';
      expect(familyEmoji.length).toBe(11);

      const result = truncateContent(familyEmoji + 'test', 14);
      expect(result).toBe(familyEmoji + '...');

      const shortResult = truncateContent(familyEmoji + 'test', 10);
      expect(shortResult).toBe('...');
    });

    it('should handle flag emoji correctly', () => {
      const flag = '🇺🇸';
      expect(flag.length).toBe(4);

      expect(truncateContent(flag + 'hello', 7)).toBe(flag + '...');
      expect(truncateContent(flag + 'hello', 6)).toBe('...');
    });

    it('should handle mixed content with emojis', () => {
      const text = 'Hello 👋 World 🌍';
      const result = truncateContent(text, 10);
      expect(result.endsWith('...')).toBe(true);
      expect(result.length).toBeLessThanOrEqual(13);
    });

    it('should handle empty string', () => {
      expect(truncateContent('', 10)).toBe('');
    });

    it('should handle string with only emojis', () => {
      const emojis = '🔥🎉💯';
      expect(emojis.length).toBe(6);

      expect(truncateContent(emojis, 5)).toBe('🔥...');
      expect(truncateContent(emojis, 6)).toBe('🔥🎉💯');
      expect(truncateContent(emojis, 9)).toBe('🔥🎉💯');
    });

    it('should preserve entire grapheme or exclude it - never break mid-grapheme', () => {
      const text = 'abcdef';
      const result = truncateContent(text, 5);
      expect(result).toBe('ab...');

      const simpleEmoji = '😀test';
      const emoji = '😀';
      expect(truncateContent(simpleEmoji, 5)).toBe(emoji + '...');
      expect(truncateContent(simpleEmoji, 6)).toBe(emoji + 'test');
      expect(truncateContent(simpleEmoji, 4)).toBe('...');
    });
  });
});
