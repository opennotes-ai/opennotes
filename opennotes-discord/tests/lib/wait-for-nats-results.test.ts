import { jest, describe, test, expect, beforeEach } from '@jest/globals';

const mockGetBulkScanResults = jest.fn<() => Promise<any>>();
const mockSubscribe = jest.fn<(...args: any[]) => Promise<any>>();

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: {
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
    debug: jest.fn(),
  },
}));

jest.unstable_mockModule('../../src/api-client.js', () => ({
  apiClient: {
    getBulkScanResults: mockGetBulkScanResults,
  },
}));

jest.unstable_mockModule('nats', () => ({
  connect: jest.fn(),
  StringCodec: () => ({
    decode: (data: Uint8Array) => Buffer.from(data).toString('utf8'),
  }),
  consumerOpts: () => ({
    deliverTo: jest.fn(),
    manualAck: jest.fn(),
    ackExplicit: jest.fn(),
  }),
}));

const { NatsResultsWaiter, waitForNatsResults } = await import('../../src/lib/nats-results-waiter.js');

function createMockSub(messages: Array<{ data: Uint8Array; ack: () => void }>) {
  return {
    unsubscribe: jest.fn(),
    [Symbol.asyncIterator]: async function* () {
      for (const message of messages) {
        yield message;
      }
    },
  };
}

describe('NatsResultsWaiter', () => {
  beforeEach(() => {
    jest.clearAllMocks();

    mockGetBulkScanResults.mockResolvedValue({
      data: {
        id: 'scan-123',
        type: 'bulk-scan',
        attributes: {
          status: 'completed',
          messages_scanned: 20,
          messages_flagged: 0,
        },
      },
      included: [],
      jsonapi: { version: '1.0' },
    });
  });

  test('fails when one or more required subjects cannot be subscribed', async () => {
    mockSubscribe
      .mockResolvedValueOnce(createMockSub([]))
      .mockRejectedValueOnce(new Error('subject unavailable'))
      .mockResolvedValueOnce(createMockSub([]))
      .mockResolvedValueOnce(createMockSub([]));

    const waiter = new NatsResultsWaiter('scan-123', {
      jetstream: () => ({ subscribe: mockSubscribe }),
    } as any);

    await expect(waiter.start()).rejects.toThrow(/Failed to subscribe/i);
  });

  test('invokes onProgress callback for bulk_scan.progress events', async () => {
    const onProgress = jest.fn();

    const progressEvent = {
      event_type: 'bulk_scan.progress',
      scan_id: 'scan-123',
      community_server_id: 'community-1',
      platform_community_server_id: 'guild-1',
      batch_number: 1,
      messages_in_batch: 10,
      messages_processed: 10,
      channel_ids: ['channel-1'],
      message_scores: [],
      threshold_used: 0.7,
    };

    const finishedEvent = {
      event_type: 'bulk_scan.processing_finished',
      scan_id: 'scan-123',
      community_server_id: 'community-1',
      messages_scanned: 10,
      messages_flagged: 0,
    };

    const progressMessage = {
      data: Buffer.from(JSON.stringify(progressEvent), 'utf8'),
      ack: jest.fn(),
    };
    const finishedMessage = {
      data: Buffer.from(JSON.stringify(finishedEvent), 'utf8'),
      ack: jest.fn(),
    };

    mockSubscribe
      .mockResolvedValueOnce(createMockSub([progressMessage, finishedMessage]))
      .mockResolvedValueOnce(createMockSub([]))
      .mockResolvedValueOnce(createMockSub([]))
      .mockResolvedValueOnce(createMockSub([]));

    const result = await waitForNatsResults('scan-123', {
      jetstream: () => ({ subscribe: mockSubscribe }),
    } as any, {
      onProgress,
    });

    expect(onProgress).toHaveBeenCalledWith(expect.objectContaining({
      event_type: 'bulk_scan.progress',
      scan_id: 'scan-123',
    }));
    expect(result.data.attributes.status).toBe('completed');
  });
});
