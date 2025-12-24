import { jest, describe, it, expect, beforeEach } from '@jest/globals';
import {
  natsConnectionFactory,
  closedNatsConnectionFactory,
  failingJetStreamConnectionFactory,
  createAsyncIterator,
  createMockJsMessage,
  createMockSubscription,
  createMockConnect,
  createFailingMockConnect,
} from './nats-connection.js';

describe('natsConnectionFactory', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('basic factory', () => {
    it('should create a mock NATS connection with default values', () => {
      const connection = natsConnectionFactory.build();

      expect(connection).toBeDefined();
      expect(connection.jetstream).toBeDefined();
      expect(connection.jetstreamManager).toBeDefined();
      expect(connection.subscribe).toBeDefined();
      expect(connection.close).toBeDefined();
      expect(connection.drain).toBeDefined();
      expect(connection.isClosed).toBeDefined();
      expect(connection.status).toBeDefined();
    });

    it('should return false for isClosed by default', () => {
      const connection = natsConnectionFactory.build();

      expect(connection.isClosed()).toBe(false);
    });

    it('should return a JetStream client', () => {
      const connection = natsConnectionFactory.build();
      const js = connection.jetstream();

      expect(js).toBeDefined();
      expect(js.publish).toBeDefined();
      expect(js.subscribe).toBeDefined();
    });

    it('should return a JetStream manager', async () => {
      const connection = natsConnectionFactory.build();
      const jsm = await connection.jetstreamManager();

      expect(jsm).toBeDefined();
      expect(jsm.consumers).toBeDefined();
      expect(jsm.consumers.add).toBeDefined();
      expect(jsm.consumers.delete).toBeDefined();
      expect(jsm.consumers.info).toBeDefined();
      expect(jsm.consumers.list).toBeDefined();
    });

    it('should resolve publish with PubAck', async () => {
      const connection = natsConnectionFactory.build();
      const js = connection.jetstream();

      const pubAck = await js.publish();

      expect(pubAck).toEqual({
        stream: 'test-stream',
        seq: 1,
        duplicate: false,
      });
    });
  });

  describe('transient params', () => {
    it('should support custom isClosed state', () => {
      const connection = natsConnectionFactory.build({}, { transient: { isClosed: true } });

      expect(connection.isClosed()).toBe(true);
    });

    it('should support custom status events', async () => {
      const statusEvents = [
        { type: 'disconnect', data: '' },
        { type: 'reconnecting', data: 1 },
        { type: 'reconnect', data: 'nats://localhost:4222' },
      ];
      const connection = natsConnectionFactory.build(
        {},
        { transient: { statusEvents: statusEvents as any } }
      );

      const events: unknown[] = [];
      for await (const status of connection.status()) {
        events.push(status);
      }

      expect(events).toHaveLength(3);
      expect(events[0]).toEqual({ type: 'disconnect', data: '' });
      expect(events[1]).toEqual({ type: 'reconnecting', data: 1 });
      expect(events[2]).toEqual({ type: 'reconnect', data: 'nats://localhost:4222' });
    });

    it('should support failing JetStream', () => {
      const connection = natsConnectionFactory.build(
        {},
        { transient: { shouldFailJetStream: true } }
      );

      expect(() => connection.jetstream()).toThrow('JetStream unavailable');
    });

    it('should support failing JetStream manager', async () => {
      const connection = natsConnectionFactory.build(
        {},
        { transient: { shouldFailJetStream: true } }
      );

      await expect(connection.jetstreamManager()).rejects.toThrow(
        'JetStream manager unavailable'
      );
    });
  });

  describe('pre-configured factories', () => {
    it('closedNatsConnectionFactory should return closed connection', () => {
      const connection = closedNatsConnectionFactory.build();

      expect(connection.isClosed()).toBe(true);
    });

    it('failingJetStreamConnectionFactory should fail JetStream access', () => {
      const connection = failingJetStreamConnectionFactory.build();

      expect(() => connection.jetstream()).toThrow('JetStream unavailable');
    });
  });
});

describe('createAsyncIterator', () => {
  it('should create an async iterator from array values', async () => {
    const values = [1, 2, 3];
    const iterator = createAsyncIterator(values);

    const results: number[] = [];
    for await (const value of iterator) {
      results.push(value);
    }

    expect(results).toEqual([1, 2, 3]);
  });

  it('should work with empty arrays', async () => {
    const iterator = createAsyncIterator([]);

    const results: unknown[] = [];
    for await (const value of iterator) {
      results.push(value);
    }

    expect(results).toEqual([]);
  });

  it('should work with objects', async () => {
    const values = [{ type: 'connect', data: 'test' }];
    const iterator = createAsyncIterator(values);

    const result = await iterator.next();

    expect(result.done).toBe(false);
    expect(result.value).toEqual({ type: 'connect', data: 'test' });
  });
});

describe('createMockJsMessage', () => {
  it('should create a JsMsg with default values', () => {
    const msg = createMockJsMessage({});

    expect(msg.data).toBeInstanceOf(Uint8Array);
    expect(msg.subject).toBe('test.subject');
    expect(msg.redelivered).toBe(false);
    expect(msg.info.redeliveryCount).toBe(0);
    expect(msg.ack).toBeDefined();
    expect(msg.nak).toBeDefined();
    expect(msg.term).toBeDefined();
  });

  it('should support custom data', () => {
    const customData = new Uint8Array([4, 5, 6]);
    const msg = createMockJsMessage({ data: customData });

    expect(msg.data).toBe(customData);
  });

  it('should support custom subject', () => {
    const msg = createMockJsMessage({ subject: 'custom.subject' });

    expect(msg.subject).toBe('custom.subject');
  });

  it('should support redelivery count', () => {
    const msg = createMockJsMessage({ redeliveryCount: 3 });

    expect(msg.redelivered).toBe(true);
    expect(msg.info.redeliveryCount).toBe(3);
  });
});

describe('createMockSubscription', () => {
  it('should create a subscription with no messages', () => {
    const sub = createMockSubscription();

    expect(sub).toBeDefined();
    expect(sub.drain).toBeDefined();
    expect(sub.unsubscribe).toBeDefined();
  });

  it('should support custom messages', () => {
    const messages = [createMockJsMessage({ subject: 'msg1' })];
    const sub = createMockSubscription({ messages });

    expect(sub.getReceived()).toBe(1);
  });
});

describe('createMockConnect', () => {
  it('should create a mock connect function', async () => {
    const mockConnect = createMockConnect();

    const connection = await mockConnect();

    expect(connection).toBeDefined();
    expect(connection.jetstream).toBeDefined();
  });

  it('should accept a pre-built connection', async () => {
    const customConnection = natsConnectionFactory.build(
      {},
      { transient: { isClosed: true } }
    );
    const mockConnect = createMockConnect(customConnection);

    const connection = await mockConnect();

    expect(connection.isClosed()).toBe(true);
  });
});

describe('createFailingMockConnect', () => {
  it('should create a mock connect that fails with default error', async () => {
    const mockConnect = createFailingMockConnect();

    await expect(mockConnect()).rejects.toThrow('Connection failed');
  });

  it('should support custom error', async () => {
    const customError = new Error('Custom connection error');
    const mockConnect = createFailingMockConnect(customError);

    await expect(mockConnect()).rejects.toThrow('Custom connection error');
  });
});
