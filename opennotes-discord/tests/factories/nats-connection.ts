import { Factory } from 'fishery';
import { jest } from '@jest/globals';
import type {
  NatsConnection,
  JetStreamClient,
  JetStreamManager,
  JetStreamSubscription,
  PubAck,
  ConsumerInfo,
  Subscription,
  JsMsg,
} from 'nats';

/**
 * Status event type for NATS connection status updates
 */
export interface MockStatusEvent {
  type: string;
  data: string | number;
}

/**
 * Helper to create an async iterator from an array of values.
 * Useful for mocking status(), subscription iteration, etc.
 */
export function createAsyncIterator<T>(values: T[]): AsyncIterableIterator<T> {
  let index = 0;
  return {
    async next() {
      if (index < values.length) {
        return { value: values[index++], done: false as const };
      }
      return { value: undefined as unknown as T, done: true as const };
    },
    [Symbol.asyncIterator]() {
      return this;
    },
  };
}

/**
 * Creates a mock JsMsg for testing message handling.
 */
export function createMockJsMessage(options: {
  data?: Uint8Array;
  subject?: string;
  redeliveryCount?: number;
}): JsMsg {
  const {
    data = new Uint8Array([1, 2, 3]),
    subject = 'test.subject',
    redeliveryCount = 0,
  } = options;

  return {
    data,
    subject,
    redelivered: redeliveryCount > 0,
    seq: 1,
    sid: 1,
    headers: undefined,
    info: {
      redeliveryCount,
      stream: 'test-stream',
      consumer: 'test-consumer',
      domain: undefined,
      delivered: { stream_seq: 1, consumer_seq: 1 },
      pending: 0,
      timestampNanos: Date.now() * 1_000_000,
    },
    ack: jest.fn(),
    nak: jest.fn(),
    working: jest.fn(),
    term: jest.fn(),
    ackAck: jest.fn<() => Promise<boolean>>().mockResolvedValue(true),
    next: jest.fn(),
    json: jest.fn(),
    string: jest.fn(),
  } as unknown as JsMsg;
}

/**
 * Creates a mock JetStream subscription for testing.
 */
export function createMockSubscription(options?: {
  messages?: JsMsg[];
}): JetStreamSubscription {
  const messages = options?.messages ?? [];

  return {
    drain: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
    unsubscribe: jest.fn(),
    closed: Promise.resolve(),
    isClosed: jest.fn().mockReturnValue(false),
    [Symbol.asyncIterator]: jest.fn(function* () {
      yield* messages;
    }),
    getSubject: jest.fn().mockReturnValue('test.subject'),
    getReceived: jest.fn().mockReturnValue(messages.length),
    getPending: jest.fn().mockReturnValue(0),
    getProcessed: jest.fn().mockReturnValue(messages.length),
    getMax: jest.fn().mockReturnValue(undefined),
    getID: jest.fn().mockReturnValue(1),
    consumerInfo: jest.fn<() => Promise<ConsumerInfo>>().mockResolvedValue({
      name: 'test-consumer',
      stream_name: 'test-stream',
      config: {},
      created: new Date().toISOString(),
      delivered: { consumer_seq: 0, stream_seq: 0 },
      ack_floor: { consumer_seq: 0, stream_seq: 0 },
      num_ack_pending: 0,
      num_redelivered: 0,
      num_waiting: 0,
      num_pending: 0,
    } as ConsumerInfo),
    destroy: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
    callback: undefined,
  } as unknown as JetStreamSubscription;
}

/**
 * Mock ConsumerAPI with commonly used methods
 */
export interface MockConsumerAPI {
  add: jest.Mock<() => Promise<ConsumerInfo>>;
  delete: jest.Mock<() => Promise<boolean>>;
  info: jest.Mock<() => Promise<ConsumerInfo>>;
  list: jest.Mock<() => { next: jest.Mock<() => Promise<ConsumerInfo[]>> }>;
  update: jest.Mock;
  pause: jest.Mock;
  resume: jest.Mock;
}

/**
 * Mock JetStreamClient with commonly used methods
 */
export interface MockJetStreamClient {
  publish: jest.Mock<() => Promise<PubAck>>;
  subscribe: jest.Mock<() => Promise<JetStreamSubscription>>;
  pull: jest.Mock;
  fetch: jest.Mock;
  pullSubscribe: jest.Mock;
  views: JetStreamClient['views'];
  apiPrefix: string;
  consumers: JetStreamClient['consumers'];
  streams: JetStreamClient['streams'];
  jetstreamManager: jest.Mock;
  getOptions: jest.Mock;
}

/**
 * Mock JetStreamManager with commonly used methods
 */
export interface MockJetStreamManager {
  consumers: MockConsumerAPI;
  streams: JetStreamManager['streams'];
  getAccountInfo: jest.Mock;
  advisories: jest.Mock;
  getOptions: jest.Mock;
  jetstream: jest.Mock;
}

/**
 * Mock NatsConnection with commonly used methods
 */
export interface MockNatsConnection {
  jetstream: jest.Mock<() => MockJetStreamClient>;
  jetstreamManager: jest.Mock<() => Promise<MockJetStreamManager>>;
  subscribe: jest.Mock<() => Subscription>;
  close: jest.Mock<() => Promise<void>>;
  drain: jest.Mock<() => Promise<void>>;
  isClosed: jest.Mock<() => boolean>;
  status: jest.Mock<() => AsyncIterable<MockStatusEvent>>;
  closed: jest.Mock<() => Promise<void | Error>>;
  publish: jest.Mock;
  publishMessage: jest.Mock;
  respondMessage: jest.Mock;
  request: jest.Mock;
  requestMany: jest.Mock;
  flush: jest.Mock<() => Promise<void>>;
  isDraining: jest.Mock<() => boolean>;
  getServer: jest.Mock<() => string>;
  stats: jest.Mock;
  rtt: jest.Mock<() => Promise<number>>;
  services: NatsConnection['services'];
  reconnect: jest.Mock<() => Promise<void>>;
  info: undefined;
}

export interface NatsConnectionTransientParams {
  isClosed?: boolean;
  statusEvents?: MockStatusEvent[];
  jetStreamClient?: Partial<MockJetStreamClient>;
  jetStreamManager?: Partial<MockJetStreamManager>;
  subscription?: JetStreamSubscription;
  shouldFailConnect?: boolean;
  shouldFailJetStream?: boolean;
}

function createDefaultConsumerInfo(): ConsumerInfo {
  return {
    name: 'test-consumer',
    stream_name: 'test-stream',
    config: {},
    created: new Date().toISOString(),
    delivered: { consumer_seq: 0, stream_seq: 0 },
    ack_floor: { consumer_seq: 0, stream_seq: 0 },
    num_ack_pending: 0,
    num_redelivered: 0,
    num_waiting: 0,
    num_pending: 0,
  } as ConsumerInfo;
}

function createDefaultJetStreamClient(
  overrides?: Partial<MockJetStreamClient>,
  subscription?: JetStreamSubscription
): MockJetStreamClient {
  const sub = subscription ?? createMockSubscription();

  return {
    publish: jest.fn<() => Promise<PubAck>>().mockResolvedValue({
      stream: 'test-stream',
      seq: 1,
      duplicate: false,
    }),
    subscribe: jest.fn<() => Promise<JetStreamSubscription>>().mockResolvedValue(sub),
    pull: jest.fn(),
    fetch: jest.fn(),
    pullSubscribe: jest.fn(),
    views: {} as JetStreamClient['views'],
    apiPrefix: '$JS.API',
    consumers: {} as JetStreamClient['consumers'],
    streams: {} as JetStreamClient['streams'],
    jetstreamManager: jest.fn(),
    getOptions: jest.fn().mockReturnValue({}),
    ...overrides,
  };
}

function createDefaultJetStreamManager(
  overrides?: Partial<MockJetStreamManager>
): MockJetStreamManager {
  const mockConsumerAPI: MockConsumerAPI = {
    add: jest.fn<() => Promise<ConsumerInfo>>().mockResolvedValue(createDefaultConsumerInfo()),
    delete: jest.fn<() => Promise<boolean>>().mockResolvedValue(true),
    info: jest.fn<() => Promise<ConsumerInfo>>().mockResolvedValue(createDefaultConsumerInfo()),
    list: jest.fn<() => { next: jest.Mock<() => Promise<ConsumerInfo[]>> }>().mockReturnValue({
      next: jest.fn<() => Promise<ConsumerInfo[]>>().mockResolvedValue([]),
    }),
    update: jest.fn(),
    pause: jest.fn(),
    resume: jest.fn(),
  };

  return {
    consumers: mockConsumerAPI,
    streams: {} as JetStreamManager['streams'],
    getAccountInfo: jest.fn(),
    advisories: jest.fn(),
    getOptions: jest.fn().mockReturnValue({}),
    jetstream: jest.fn(),
    ...overrides,
  };
}

export const natsConnectionFactory = Factory.define<
  MockNatsConnection,
  NatsConnectionTransientParams
>(({ transientParams }) => {
  const {
    isClosed = false,
    statusEvents = [{ type: 'connect', data: 'nats://localhost:4222' }],
    jetStreamClient,
    jetStreamManager,
    subscription,
    shouldFailJetStream = false,
  } = transientParams;

  const jsClient = createDefaultJetStreamClient(jetStreamClient, subscription);
  const jsManager = createDefaultJetStreamManager(jetStreamManager);

  const mockConnection: MockNatsConnection = {
    jetstream: shouldFailJetStream
      ? jest.fn<() => MockJetStreamClient>().mockImplementation(() => {
          throw new Error('JetStream unavailable');
        })
      : jest.fn<() => MockJetStreamClient>().mockReturnValue(jsClient),
    jetstreamManager: shouldFailJetStream
      ? jest.fn<() => Promise<MockJetStreamManager>>().mockRejectedValue(
          new Error('JetStream manager unavailable')
        )
      : jest.fn<() => Promise<MockJetStreamManager>>().mockResolvedValue(jsManager),
    subscribe: jest.fn<() => Subscription>().mockReturnValue({
      drain: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
      unsubscribe: jest.fn(),
      closed: Promise.resolve(),
      isClosed: jest.fn().mockReturnValue(false),
      getSubject: jest.fn().mockReturnValue('test.subject'),
      getReceived: jest.fn().mockReturnValue(0),
      getPending: jest.fn().mockReturnValue(0),
      getProcessed: jest.fn().mockReturnValue(0),
      getMax: jest.fn().mockReturnValue(undefined),
      getID: jest.fn().mockReturnValue(1),
      callback: undefined,
      [Symbol.asyncIterator]: jest.fn(function* () {
        yield* [];
      }),
    } as unknown as Subscription),
    close: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
    drain: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
    isClosed: jest.fn<() => boolean>().mockReturnValue(isClosed),
    status: jest.fn<() => AsyncIterable<MockStatusEvent>>().mockReturnValue(
      createAsyncIterator(statusEvents)
    ),
    closed: jest.fn<() => Promise<void | Error>>().mockResolvedValue(undefined),
    publish: jest.fn(),
    publishMessage: jest.fn(),
    respondMessage: jest.fn(),
    request: jest.fn(),
    requestMany: jest.fn(),
    flush: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
    isDraining: jest.fn<() => boolean>().mockReturnValue(false),
    getServer: jest.fn<() => string>().mockReturnValue('nats://localhost:4222'),
    stats: jest.fn().mockReturnValue({
      inBytes: 0,
      outBytes: 0,
      inMsgs: 0,
      outMsgs: 0,
    }),
    rtt: jest.fn<() => Promise<number>>().mockResolvedValue(1),
    services: {} as NatsConnection['services'],
    reconnect: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
    info: undefined,
  };

  return mockConnection;
});

/**
 * Pre-configured factory for a closed NATS connection.
 */
export const closedNatsConnectionFactory = natsConnectionFactory.transient({
  isClosed: true,
  statusEvents: [{ type: 'disconnect', data: '' }],
});

/**
 * Pre-configured factory for a connection with JetStream unavailable.
 */
export const failingJetStreamConnectionFactory = natsConnectionFactory.transient({
  shouldFailJetStream: true,
});

/**
 * Helper to create a mock connect function that returns a factory-built connection.
 */
export function createMockConnect(
  connection?: MockNatsConnection
): jest.Mock<() => Promise<MockNatsConnection>> {
  const conn = connection ?? natsConnectionFactory.build();
  return jest.fn<() => Promise<MockNatsConnection>>().mockResolvedValue(conn);
}

/**
 * Helper to create a failing mock connect function.
 */
export function createFailingMockConnect(
  error: Error = new Error('Connection failed')
): jest.Mock<() => Promise<never>> {
  return jest.fn<() => Promise<never>>().mockRejectedValue(error);
}
