import { describe, test, expect } from '@jest/globals';

describe('waitForNatsResults', () => {
  test('waitForNatsResults function should exist and be exported', async () => {
    const module = await import('../../src/lib/bulk-scan-executor.js');
    expect(typeof module.waitForNatsResults).toBe('function');
  });

  test('NatsResultsWaiter class should be exported', async () => {
    const module = await import('../../src/lib/bulk-scan-executor.js');
    expect(module.NatsResultsWaiter).toBeDefined();
  });

  test('should have correct timeout constants', async () => {
    const {
      NATS_STALL_WARNING_MS,
      NATS_SILENCE_TIMEOUT_MS,
      NATS_MAX_WAIT_MS,
    } = await import('../../src/lib/bulk-scan-executor.js');

    expect(NATS_STALL_WARNING_MS).toBe(30000);
    expect(NATS_SILENCE_TIMEOUT_MS).toBe(60000);
    expect(NATS_MAX_WAIT_MS).toBe(300000);
  });
});

describe('NatsResultsWaiter', () => {
  test('NatsResultsWaiter should have onStallWarning method', async () => {
    const { NatsResultsWaiter } = await import('../../src/lib/nats-results-waiter.js');

    const mockNc = {} as never;
    const waiter = new NatsResultsWaiter('scan-123', mockNc);

    expect(typeof waiter.onStallWarning).toBe('function');
  });

  test('NatsResultsWaiter should have onProgress method', async () => {
    const { NatsResultsWaiter } = await import('../../src/lib/nats-results-waiter.js');

    const mockNc = {} as never;
    const waiter = new NatsResultsWaiter('scan-123', mockNc);

    expect(typeof waiter.onProgress).toBe('function');
  });

  test('NatsResultsWaiter should have start method', async () => {
    const { NatsResultsWaiter } = await import('../../src/lib/nats-results-waiter.js');

    const mockNc = {} as never;
    const waiter = new NatsResultsWaiter('scan-123', mockNc);

    expect(typeof waiter.start).toBe('function');
  });
});
