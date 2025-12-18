import { jest, describe, it, expect, beforeEach, afterEach } from '@jest/globals';
import { ChannelType, Collection } from 'discord.js';

const mockLogger = {
  info: jest.fn<(...args: unknown[]) => void>(),
  error: jest.fn<(...args: unknown[]) => void>(),
  warn: jest.fn<(...args: unknown[]) => void>(),
  debug: jest.fn<(...args: unknown[]) => void>(),
};

const mockInitiateBulkScan = jest.fn<(guildId: string, days: number) => Promise<{ scan_id: string }>>();

const mockGetBulkScanResults = jest.fn<(scanId: string) => Promise<{
  scan_id: string;
  status: 'completed' | 'failed' | 'pending';
  messages_scanned: number;
  flagged_messages: any[];
}>>();

const mockPublishBulkScanBatch = jest.fn<(subject: string, batch: any) => Promise<void>>();

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
}));

jest.unstable_mockModule('../../src/api-client.js', () => ({
  apiClient: {
    initiateBulkScan: mockInitiateBulkScan,
    getBulkScanResults: mockGetBulkScanResults,
  },
}));

jest.unstable_mockModule('../../src/events/NatsPublisher.js', () => ({
  natsPublisher: {
    publishBulkScanBatch: mockPublishBulkScanBatch,
  },
}));

const { executeBulkScan, POLL_INTERVAL_MS, POLL_TIMEOUT_MS } = await import('../../src/lib/bulk-scan-executor.js');
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
          batchIndex: expect.any(Number),
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
});
