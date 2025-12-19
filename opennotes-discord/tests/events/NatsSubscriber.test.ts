import { jest } from '@jest/globals';
import type { ScoreUpdateEvent } from '../../src/events/types.js';
import { TEST_SCORE_ABOVE_THRESHOLD } from '../test-constants.js';

const mockConnect = jest.fn<(...args: any[]) => Promise<any>>();
const mockSubscribe = jest.fn<(...args: any[]) => any>();
const mockJsSubscribe = jest.fn<(...args: any[]) => Promise<any>>();
const mockClose = jest.fn<(...args: any[]) => Promise<any>>();
const mockIsClosed = jest.fn<() => boolean>();
const mockDrain = jest.fn<(...args: any[]) => Promise<any>>();
const mockStatus = jest.fn<() => AsyncIterableIterator<any>>();
const mockStringCodec = jest.fn(() => ({
  decode: jest.fn<(data: Uint8Array) => string>(),
  encode: jest.fn<(str: string) => Uint8Array>(),
}));

const createMockConsumerOpts = () => {
  const builder: any = {};
  builder.durable = jest.fn().mockReturnValue(builder);
  builder.deliverGroup = jest.fn().mockReturnValue(builder);
  builder.deliverAll = jest.fn().mockReturnValue(builder);
  builder.deliverNew = jest.fn().mockReturnValue(builder);
  builder.ackExplicit = jest.fn().mockReturnValue(builder);
  builder.ackWait = jest.fn().mockReturnValue(builder);
  builder.maxDeliver = jest.fn().mockReturnValue(builder);
  builder.deliverTo = jest.fn().mockReturnValue(builder);
  return builder;
};

const mockConsumerOpts = jest.fn(() => createMockConsumerOpts());

let mockNatsConnection: any;
let mockJetStream: any;
let mockJetStreamManager: any;
let mockSubscription: any;
let mockCodec: any;

const mockLogger = {
  debug: jest.fn<(...args: unknown[]) => void>(),
  info: jest.fn<(...args: unknown[]) => void>(),
  warn: jest.fn<(...args: unknown[]) => void>(),
  error: jest.fn<(...args: unknown[]) => void>(),
};

jest.unstable_mockModule('nats', () => ({
  connect: mockConnect,
  StringCodec: mockStringCodec,
  consumerOpts: mockConsumerOpts,
}));

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
}));

jest.unstable_mockModule('../../src/utils/url-sanitizer.js', () => ({
  sanitizeConnectionUrl: (url: string) => url.replace(/:[^:@]*@/, ':***@'),
}));

const { NatsSubscriber } = await import('../../src/events/NatsSubscriber.js');

const createAsyncIterator = (values: any[]) => {
  let index = 0;
  return {
    async next() {
      if (index < values.length) {
        return { value: values[index++], done: false };
      }
      return { value: undefined, done: true };
    },
    [Symbol.asyncIterator]() {
      return this;
    },
  } as AsyncIterableIterator<any>;
};

describe('NatsSubscriber', () => {
  let subscriber: InstanceType<typeof NatsSubscriber>;
  const expectedNatsUrl = process.env.NATS_URL || 'nats://localhost:4222';

  beforeEach(() => {
    mockCodec = {
      decode: jest.fn<(data: Uint8Array) => string>(),
      encode: jest.fn<(str: string) => Uint8Array>(),
    };

    mockSubscription = {
      drain: mockDrain,
      [Symbol.asyncIterator]: jest.fn(function* (this: any) {
        yield* this.messages || [];
      }),
      messages: [],
    };

    mockJetStream = {
      subscribe: mockJsSubscribe.mockResolvedValue(mockSubscription),
    };

    mockJetStreamManager = {
      consumers: {
        delete: jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined),
        list: jest.fn<(...args: any[]) => any>().mockReturnValue({
          next: jest.fn<() => Promise<any[]>>().mockResolvedValue([]),
        }),
        add: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({
          name: 'test-consumer',
          config: {},
        }),
      },
    };

    mockNatsConnection = {
      subscribe: mockSubscribe.mockReturnValue(mockSubscription),
      jetstream: jest.fn<() => any>().mockReturnValue(mockJetStream),
      jetstreamManager: jest.fn<() => Promise<any>>().mockResolvedValue(mockJetStreamManager),
      close: mockClose,
      isClosed: mockIsClosed,
      status: mockStatus,
    };

    mockConnect.mockResolvedValue(mockNatsConnection);
    mockStringCodec.mockReturnValue(mockCodec);
    mockConsumerOpts.mockImplementation(() => createMockConsumerOpts());
    mockIsClosed.mockReturnValue(false);

    mockStatus.mockReturnValue(
      createAsyncIterator([{ type: 'connect', data: expectedNatsUrl }])
    );

    subscriber = new NatsSubscriber();

    jest.clearAllMocks();
  });

  describe('constructor', () => {
    it('should initialize with default values from environment', () => {
      const originalEnv = process.env;
      process.env = {
        ...originalEnv,
        NATS_MAX_RECONNECT_ATTEMPTS: '15',
        NATS_RECONNECT_WAIT: '5',
      };

      const newSubscriber = new NatsSubscriber();
      expect(newSubscriber).toBeDefined();

      process.env = originalEnv;
    });

    it('should use fallback values when environment variables are not set', () => {
      const originalEnv = process.env;
      process.env = { ...originalEnv };
      delete process.env.NATS_MAX_RECONNECT_ATTEMPTS;
      delete process.env.NATS_RECONNECT_WAIT;

      const newSubscriber = new NatsSubscriber();
      expect(newSubscriber).toBeDefined();

      process.env = originalEnv;
    });
  });

  describe('connect', () => {
    it('should connect to NATS server with default URL', async () => {
      await subscriber.connect();

      expect(mockConnect).toHaveBeenCalledWith(
        expect.objectContaining({
          servers: expectedNatsUrl,
          maxReconnectAttempts: 10,
          reconnectTimeWait: 2000,
          name: 'opennotes-discord-bot',
        })
      );

      expect(mockLogger.info).toHaveBeenCalledWith(
        'Connected to NATS server',
        expect.objectContaining({
          url: expect.any(String),
        })
      );
    });

    it('should connect to NATS server with custom URL', async () => {
      const customUrl = 'nats://custom-server:4222';

      await subscriber.connect(customUrl);

      expect(mockConnect).toHaveBeenCalledWith(
        expect.objectContaining({
          servers: customUrl,
        })
      );

      expect(mockLogger.info).toHaveBeenCalledWith(
        'Connected to NATS server',
        expect.any(Object)
      );
    });

    it('should use NATS_URL from environment if no URL provided', async () => {
      const originalEnv = process.env;
      process.env = {
        ...originalEnv,
        NATS_URL: 'nats://env-server:4222',
      };

      await subscriber.connect();

      expect(mockConnect).toHaveBeenCalledWith(
        expect.objectContaining({
          servers: 'nats://env-server:4222',
        })
      );

      process.env = originalEnv;
    });

    it('should handle connection errors gracefully', async () => {
      const connectionError = new Error('Connection failed');
      mockConnect.mockRejectedValueOnce(connectionError);

      await expect(subscriber.connect()).rejects.toThrow('Connection failed');

      expect(mockLogger.error).toHaveBeenCalledWith(
        'Failed to connect to NATS',
        expect.objectContaining({
          error: 'Connection failed',
          url: expect.any(String),
        })
      );
    });

    it('should setup connection handlers after successful connection', async () => {
      await subscriber.connect();

      expect(mockStatus).toHaveBeenCalled();
    });
  });

  describe('subscribeToScoreUpdates', () => {
    beforeEach(async () => {
      await subscriber.connect();
      jest.clearAllMocks();
    });

    it('should throw error if not connected', async () => {
      const newSubscriber = new NatsSubscriber();
      const handler = jest.fn<(event: ScoreUpdateEvent) => Promise<void>>().mockResolvedValue(undefined);

      await expect(newSubscriber.subscribeToScoreUpdates(handler)).rejects.toThrow(
        'NATS connection not established. Call connect() first.'
      );
    });

    it('should subscribe to score update events', async () => {
      const handler = jest.fn<(event: ScoreUpdateEvent) => Promise<void>>();

      await subscriber.subscribeToScoreUpdates(handler);

      expect(mockNatsConnection.jetstream).toHaveBeenCalled();
      expect(mockJsSubscribe).toHaveBeenCalledWith(
        'OPENNOTES.note_score_updated',
        expect.any(Object)
      );

      expect(mockLogger.info).toHaveBeenCalledWith(
        'Subscribed to score update events with JetStream consumer group',
        expect.objectContaining({
          subject: 'OPENNOTES.note_score_updated',
          consumerName: expect.any(String),
        })
      );
    });

    it('should handle subscription errors', async () => {
      const subscriptionError = new Error('Subscription failed');
      mockJsSubscribe.mockRejectedValueOnce(subscriptionError);

      const handler = jest.fn<(event: ScoreUpdateEvent) => Promise<void>>();

      await expect(subscriber.subscribeToScoreUpdates(handler)).rejects.toThrow(
        'Subscription failed'
      );

      expect(mockLogger.error).toHaveBeenCalledWith(
        'Failed to subscribe to score updates',
        expect.objectContaining({
          error: 'Subscription failed',
          subject: 'OPENNOTES.note_score_updated',
        })
      );
    });

    it('should process incoming messages and call handler', async () => {
      const handler = jest.fn<(event: ScoreUpdateEvent) => Promise<void>>();

      const testEvent: ScoreUpdateEvent = {
        note_id: 123,
        score: TEST_SCORE_ABOVE_THRESHOLD,
        confidence: 'standard',
        algorithm: 'MFCoreScorer',
        rating_count: 10,
        tier: 2,
        tier_name: 'Tier 2',
        timestamp: new Date().toISOString(),
        original_message_id: 'msg-123',
        channel_id: 'channel-456',
        community_server_id: 'guild-789',
      };

      const eventJson = JSON.stringify(testEvent);
      mockCodec.decode.mockReturnValue(eventJson);

      const messageData = new Uint8Array([1, 2, 3]);
      const mockMessage = {
        data: messageData,
        subject: 'OPENNOTES.note_score_updated',
        ack: jest.fn(),
        nak: jest.fn(),
        info: { redeliveryCount: 0 },
      };

      mockSubscription.messages = [mockMessage];

      await subscriber.subscribeToScoreUpdates(handler);

      await new Promise((resolve) => setTimeout(resolve, 100));

      expect(mockCodec.decode).toHaveBeenCalledWith(messageData);
      expect(handler).toHaveBeenCalledWith(testEvent);
      expect(mockMessage.ack).toHaveBeenCalled();

      expect(mockLogger.debug).toHaveBeenCalledWith(
        'Received score update event',
        expect.objectContaining({
          noteId: 123,
          score: TEST_SCORE_ABOVE_THRESHOLD,
          confidence: 'standard',
          hasDiscordContext: true,
          redeliveryCount: 0,
        })
      );
    });

    it('should handle malformed JSON in messages', async () => {
      const handler = jest.fn<(event: ScoreUpdateEvent) => Promise<void>>();

      mockCodec.decode.mockReturnValue('invalid json {');

      const mockMessage = {
        data: new Uint8Array([1, 2, 3]),
        subject: 'OPENNOTES.note_score_updated',
        ack: jest.fn(),
        nak: jest.fn(),
        info: { redeliveryCount: 0 },
      };

      mockSubscription.messages = [mockMessage];

      await subscriber.subscribeToScoreUpdates(handler);

      await new Promise((resolve) => setTimeout(resolve, 100));

      expect(handler).not.toHaveBeenCalled();
      expect(mockMessage.nak).toHaveBeenCalled();
      expect(mockLogger.error).toHaveBeenCalledWith(
        'Error processing score update event',
        expect.objectContaining({
          error: expect.stringContaining('JSON'),
        })
      );
    });

    it('should handle errors thrown by handler', async () => {
      const handlerError = new Error('Handler processing failed');
      const handler = jest.fn<(event: ScoreUpdateEvent) => Promise<void>>().mockRejectedValue(
        handlerError
      );

      const testEvent: ScoreUpdateEvent = {
        note_id: 456,
        score: 0.75,
        confidence: 'standard',
        algorithm: 'BayesianAverage',
        rating_count: 5,
        tier: 1,
        tier_name: 'Tier 1',
        timestamp: new Date().toISOString(),
      };

      mockCodec.decode.mockReturnValue(JSON.stringify(testEvent));

      const mockMessage = {
        data: new Uint8Array([1, 2, 3]),
        subject: 'OPENNOTES.note_score_updated',
        ack: jest.fn(),
        nak: jest.fn(),
        info: { redeliveryCount: 0 },
      };

      mockSubscription.messages = [mockMessage];

      await subscriber.subscribeToScoreUpdates(handler);

      await new Promise((resolve) => setTimeout(resolve, 100));

      expect(handler).toHaveBeenCalled();
      expect(mockMessage.nak).toHaveBeenCalled();
      expect(mockLogger.error).toHaveBeenCalledWith(
        'Error processing score update event',
        expect.objectContaining({
          error: 'Handler processing failed',
          stack: expect.any(String),
        })
      );
    });

    it('should log events without Discord context correctly', async () => {
      const handler = jest.fn<(event: ScoreUpdateEvent) => Promise<void>>();

      const testEvent: ScoreUpdateEvent = {
        note_id: 789,
        score: 0.9,
        confidence: 'standard',
        algorithm: 'MFCoreScorer',
        rating_count: 20,
        tier: 3,
        tier_name: 'Tier 3',
        timestamp: new Date().toISOString(),
      };

      mockCodec.decode.mockReturnValue(JSON.stringify(testEvent));

      const mockMessage = {
        data: new Uint8Array([1, 2, 3]),
        subject: 'OPENNOTES.note_score_updated',
        ack: jest.fn(),
        nak: jest.fn(),
        info: { redeliveryCount: 0 },
      };

      mockSubscription.messages = [mockMessage];

      await subscriber.subscribeToScoreUpdates(handler);

      await new Promise((resolve) => setTimeout(resolve, 100));

      expect(mockLogger.debug).toHaveBeenCalledWith(
        'Received score update event',
        expect.objectContaining({
          hasDiscordContext: false,
        })
      );
    });
  });

  describe('close', () => {
    it('should close subscription and connection', async () => {
      await subscriber.connect();
      const handler = jest.fn<(event: ScoreUpdateEvent) => Promise<void>>().mockResolvedValue(undefined);
      await subscriber.subscribeToScoreUpdates(handler);

      await subscriber.close();

      expect(mockClose).toHaveBeenCalled();

      expect(mockLogger.info).toHaveBeenCalledWith('Unsubscribed from score update events');
      expect(mockLogger.info).toHaveBeenCalledWith('Closed NATS connection');
    });

    it('should handle closing when not subscribed', async () => {
      await subscriber.connect();

      await subscriber.close();

      expect(mockClose).toHaveBeenCalled();

      expect(mockLogger.info).toHaveBeenCalledWith('Closed NATS connection');
    });

    it('should handle closing when not connected', async () => {
      await subscriber.close();

      expect(mockDrain).not.toHaveBeenCalled();
      expect(mockClose).not.toHaveBeenCalled();
    });
  });

  describe('isConnected', () => {
    it('should return true when connected', async () => {
      await subscriber.connect();

      expect(subscriber.isConnected()).toBe(true);
    });

    it('should return false when not connected', () => {
      expect(subscriber.isConnected()).toBe(false);
    });

    it('should return false when connection is closed', async () => {
      await subscriber.connect();

      mockIsClosed.mockReturnValue(true);

      expect(subscriber.isConnected()).toBe(false);
    });
  });

  describe('connection status handlers', () => {
    it('should log disconnect events', async () => {
      mockStatus.mockReturnValue(
        createAsyncIterator([{ type: 'disconnect', data: null }])
      );

      await subscriber.connect();

      await new Promise((resolve) => setTimeout(resolve, 100));

      expect(mockLogger.warn).toHaveBeenCalledWith('Disconnected from NATS server');
    });

    it('should log reconnect events', async () => {
      mockStatus.mockReturnValue(
        createAsyncIterator([{ type: 'reconnect', data: 'nats://localhost:4222' }])
      );

      await subscriber.connect();

      await new Promise((resolve) => setTimeout(resolve, 100));

      expect(mockLogger.info).toHaveBeenCalledWith('Reconnected to NATS server', {
        server: 'nats://localhost:4222',
      });
    });

    it('should log reconnecting events', async () => {
      mockStatus.mockReturnValue(
        createAsyncIterator([{ type: 'reconnecting', data: 3 }])
      );

      await subscriber.connect();

      await new Promise((resolve) => setTimeout(resolve, 100));

      expect(mockLogger.warn).toHaveBeenCalledWith('Attempting to reconnect to NATS...', {
        attempt: 3,
      });
    });

    it('should log error events', async () => {
      mockStatus.mockReturnValue(
        createAsyncIterator([{ type: 'error', data: 'Connection timeout' }])
      );

      await subscriber.connect();

      await new Promise((resolve) => setTimeout(resolve, 100));

      expect(mockLogger.error).toHaveBeenCalledWith('NATS connection error', {
        error: 'Connection timeout',
      });
    });

    it('should handle multiple status events', async () => {
      mockStatus.mockReturnValue(
        createAsyncIterator([
          { type: 'disconnect', data: null },
          { type: 'reconnecting', data: 1 },
          { type: 'reconnect', data: 'nats://localhost:4222' },
        ])
      );

      await subscriber.connect();

      await new Promise((resolve) => setTimeout(resolve, 100));

      expect(mockLogger.warn).toHaveBeenCalledWith('Disconnected from NATS server');
      expect(mockLogger.warn).toHaveBeenCalledWith('Attempting to reconnect to NATS...', {
        attempt: 1,
      });
      expect(mockLogger.info).toHaveBeenCalledWith('Reconnected to NATS server', {
        server: 'nats://localhost:4222',
      });
    });
  });
});
