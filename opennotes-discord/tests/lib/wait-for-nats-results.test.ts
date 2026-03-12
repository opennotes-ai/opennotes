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

function createMockMessage(event: Record<string, unknown>) {
  return {
    data: Buffer.from(JSON.stringify(event), 'utf8'),
    ack: jest.fn(),
  };
}

function createDeferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function createControlledSub() {
  const queuedMessages: Array<{ data: Uint8Array; ack: () => void }> = [];
  let pendingResolve: ((result: IteratorResult<{ data: Uint8Array; ack: () => void }>) => void) | undefined;
  let finished = false;

  return {
    sub: {
      unsubscribe: jest.fn(),
      [Symbol.asyncIterator]() {
        return {
          next: () => {
            if (queuedMessages.length > 0) {
              return Promise.resolve({ value: queuedMessages.shift()!, done: false });
            }
            if (finished) {
              return Promise.resolve({ value: undefined, done: true });
            }
            return new Promise<IteratorResult<{ data: Uint8Array; ack: () => void }>>((resolve) => {
              pendingResolve = resolve;
            });
          },
          return: () => {
            finished = true;
            if (pendingResolve) {
              pendingResolve({ value: undefined, done: true });
              pendingResolve = undefined;
            }
            return Promise.resolve({ value: undefined, done: true });
          },
        };
      },
    },
    push(message: { data: Uint8Array; ack: () => void }) {
      if (pendingResolve) {
        pendingResolve({ value: message, done: false });
        pendingResolve = undefined;
        return;
      }
      queuedMessages.push(message);
    },
    finish() {
      finished = true;
      if (pendingResolve) {
        pendingResolve({ value: undefined, done: true });
        pendingResolve = undefined;
      }
    },
  };
}

async function flushMicrotasks(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
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

  test('does not resolve or fetch terminal status on bulk_scan.results alone', async () => {
    const resultsSub = createControlledSub();
    const terminalFetch = createDeferred<any>();
    mockGetBulkScanResults.mockReturnValue(terminalFetch.promise);

    mockSubscribe
      .mockResolvedValueOnce(resultsSub.sub)
      .mockResolvedValueOnce(createMockSub([]))
      .mockResolvedValueOnce(createMockSub([]))
      .mockResolvedValueOnce(createMockSub([]));

    const waiterPromise = waitForNatsResults('scan-123', {
      jetstream: () => ({ subscribe: mockSubscribe }),
    } as any);

    let settled = false;
    waiterPromise.finally(() => {
      settled = true;
    });

    await flushMicrotasks();

    const resultsMessage = createMockMessage({
      event_type: 'bulk_scan.results',
      scan_id: 'scan-123',
      messages_scanned: 10,
      messages_flagged: 1,
      flagged_messages: [],
    });

    resultsSub.push(resultsMessage);
    await flushMicrotasks();

    expect(resultsMessage.ack).toHaveBeenCalledTimes(1);
    expect(mockGetBulkScanResults).not.toHaveBeenCalled();
    expect(settled).toBe(false);

    const finishedMessage = createMockMessage({
      event_type: 'bulk_scan.processing_finished',
      scan_id: 'scan-123',
      community_server_id: 'community-1',
    });

    resultsSub.push(finishedMessage);
    await flushMicrotasks();

    expect(mockGetBulkScanResults).toHaveBeenCalledTimes(1);

    const completedPayload = {
      data: {
        id: 'scan-123',
        type: 'bulk-scan',
        attributes: {
          status: 'completed',
          messages_scanned: 10,
          messages_flagged: 1,
        },
      },
      included: [],
      jsonapi: { version: '1.0' },
    };

    terminalFetch.resolve(completedPayload);
    await expect(waiterPromise).resolves.toEqual(completedPayload);
  });

  test('resolves failed scans from API payload after bulk_scan.failed', async () => {
    const failedPayload = {
      data: {
        id: 'scan-123',
        type: 'bulk-scan',
        attributes: {
          status: 'failed',
          messages_scanned: 10,
          messages_flagged: 0,
        },
      },
      included: [],
      jsonapi: { version: '1.0' },
    };
    mockGetBulkScanResults.mockResolvedValue(failedPayload);

    const failedMessage = createMockMessage({
      event_type: 'bulk_scan.failed',
      scan_id: 'scan-123',
      community_server_id: 'community-1',
      error_message: 'batch processing failed',
    });

    mockSubscribe
      .mockResolvedValueOnce(createMockSub([]))
      .mockResolvedValueOnce(createMockSub([]))
      .mockResolvedValueOnce(createMockSub([failedMessage]))
      .mockResolvedValueOnce(createMockSub([]));

    const result = await waitForNatsResults('scan-123', {
      jetstream: () => ({ subscribe: mockSubscribe }),
    } as any);

    expect(failedMessage.ack).toHaveBeenCalledTimes(1);
    expect(mockGetBulkScanResults).toHaveBeenCalledTimes(1);
    expect(result).toEqual(failedPayload);
    expect(result.data.attributes.status).toBe('failed');
  });

  test('rejects when terminal NATS signal is followed by a non-terminal API payload', async () => {
    mockGetBulkScanResults.mockResolvedValue({
      data: {
        id: 'scan-123',
        type: 'bulk-scan',
        attributes: {
          status: 'in_progress',
          messages_scanned: 10,
          messages_flagged: 0,
        },
      },
      included: [],
      jsonapi: { version: '1.0' },
    });

    const failedMessage = createMockMessage({
      event_type: 'bulk_scan.failed',
      scan_id: 'scan-123',
      community_server_id: 'community-1',
      error_message: 'batch processing failed',
    });

    mockSubscribe
      .mockResolvedValueOnce(createMockSub([]))
      .mockResolvedValueOnce(createMockSub([]))
      .mockResolvedValueOnce(createMockSub([failedMessage]))
      .mockResolvedValueOnce(createMockSub([]));

    await expect(
      waitForNatsResults('scan-123', {
        jetstream: () => ({ subscribe: mockSubscribe }),
      } as any)
    ).rejects.toThrow(/not terminal/i);

    expect(failedMessage.ack).toHaveBeenCalledTimes(1);
    expect(mockGetBulkScanResults).toHaveBeenCalledTimes(1);
  });

  test('fetches terminal status only once when failed and processing_finished both arrive', async () => {
    const processingFinishedSub = createControlledSub();
    const failedSub = createControlledSub();
    const terminalFetch = createDeferred<any>();
    mockGetBulkScanResults.mockReturnValue(terminalFetch.promise);

    mockSubscribe
      .mockResolvedValueOnce(processingFinishedSub.sub)
      .mockResolvedValueOnce(createMockSub([]))
      .mockResolvedValueOnce(failedSub.sub)
      .mockResolvedValueOnce(createMockSub([]));

    const waiterPromise = waitForNatsResults('scan-123', {
      jetstream: () => ({ subscribe: mockSubscribe }),
    } as any);

    await flushMicrotasks();

    const failedMessage = createMockMessage({
      event_type: 'bulk_scan.failed',
      scan_id: 'scan-123',
      community_server_id: 'community-1',
      error_message: 'batch processing failed',
    });
    failedSub.push(failedMessage);
    await flushMicrotasks();

    expect(mockGetBulkScanResults).toHaveBeenCalledTimes(1);

    const finishedMessage = createMockMessage({
      event_type: 'bulk_scan.processing_finished',
      scan_id: 'scan-123',
      community_server_id: 'community-1',
    });
    processingFinishedSub.push(finishedMessage);
    await flushMicrotasks();

    expect(mockGetBulkScanResults).toHaveBeenCalledTimes(1);

    const failedPayload = {
      data: {
        id: 'scan-123',
        type: 'bulk-scan',
        attributes: {
          status: 'failed',
          messages_scanned: 10,
          messages_flagged: 0,
        },
      },
      included: [],
      jsonapi: { version: '1.0' },
    };

    terminalFetch.resolve(failedPayload);
    await expect(waiterPromise).resolves.toEqual(failedPayload);
  });
});
