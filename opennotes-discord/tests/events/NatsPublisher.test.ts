import { jest, describe, it, expect, beforeEach } from '@jest/globals';
import type { JetStreamClient, NatsConnection, PubAck } from 'nats';
import { NATS_SUBJECTS, EventType } from '../../src/types/bulk-scan.js';

describe('NatsPublisher NATS_SUBJECTS', () => {
  it('should have correct subject names matching server expectations', () => {
    expect(NATS_SUBJECTS.BULK_SCAN_BATCH).toBe('OPENNOTES.bulk_scan_message_batch');
    expect(NATS_SUBJECTS.BULK_SCAN_COMPLETE).toBe('OPENNOTES.bulk_scan_completed');
    expect(NATS_SUBJECTS.BULK_SCAN_RESULT).toBe('OPENNOTES.bulk_scan_results');
  });
});

describe('EventType constants', () => {
  it('should have correct event type values', () => {
    expect(EventType.BULK_SCAN_MESSAGE_BATCH).toBe('bulk_scan.message_batch');
    expect(EventType.BULK_SCAN_COMPLETED).toBe('bulk_scan.completed');
    expect(EventType.BULK_SCAN_RESULTS).toBe('bulk_scan.results');
  });
});

describe('NatsPublisher', () => {
  const mockJsPublish = jest.fn<() => Promise<PubAck>>();
  const mockNcClose = jest.fn<() => Promise<void>>();
  const mockNcIsClosed = jest.fn<() => boolean>();
  const mockCodecEncode = jest.fn<(data: string) => Uint8Array>();

  beforeEach(() => {
    jest.resetModules();
    jest.clearAllMocks();
    mockCodecEncode.mockImplementation((data: string) => new TextEncoder().encode(data));
    mockNcIsClosed.mockReturnValue(false);
    mockJsPublish.mockResolvedValue({} as PubAck);
  });

  async function setupPublisher() {
    const mockJs: Partial<JetStreamClient> = {
      publish: mockJsPublish,
    };

    const mockNc: Partial<NatsConnection> = {
      jetstream: jest.fn(() => mockJs as JetStreamClient),
      close: mockNcClose,
      isClosed: mockNcIsClosed,
    };

    const mockConnect = jest.fn<() => Promise<Partial<NatsConnection>>>().mockResolvedValue(mockNc);

    jest.unstable_mockModule('nats', () => ({
      connect: mockConnect,
      StringCodec: jest.fn(() => ({
        encode: mockCodecEncode,
        decode: jest.fn(),
      })),
    }));

    jest.unstable_mockModule('../../src/logger.js', () => ({
      logger: {
        info: jest.fn(),
        debug: jest.fn(),
        error: jest.fn(),
        warn: jest.fn(),
      },
    }));

    jest.unstable_mockModule('../../src/utils/url-sanitizer.js', () => ({
      sanitizeConnectionUrl: jest.fn((url: string) => url),
    }));

    const { NatsPublisher } = await import('../../src/events/NatsPublisher.js');
    const publisher = new NatsPublisher();

    return { publisher, mockConnect, mockNc };
  }

  describe('publishBulkScanCompleted', () => {
    it('should throw error if not connected', async () => {
      const { publisher } = await setupPublisher();

      const completedEvent = {
        scan_id: '550e8400-e29b-41d4-a716-446655440000',
        community_server_id: '660e8400-e29b-41d4-a716-446655440000',
        messages_scanned: 42,
      };

      await expect(publisher.publishBulkScanCompleted(completedEvent)).rejects.toThrow(
        'NATS connection not established. Call connect() first.'
      );
    });

    it('should publish to BULK_SCAN_COMPLETE subject with correct payload', async () => {
      const { publisher } = await setupPublisher();
      await publisher.connect('nats://localhost:4222');

      const completedEvent = {
        scan_id: '550e8400-e29b-41d4-a716-446655440000',
        community_server_id: '660e8400-e29b-41d4-a716-446655440000',
        messages_scanned: 42,
      };

      await publisher.publishBulkScanCompleted(completedEvent);

      expect(mockJsPublish).toHaveBeenCalledTimes(1);
      expect(mockJsPublish).toHaveBeenCalledWith(
        NATS_SUBJECTS.BULK_SCAN_COMPLETE,
        expect.any(Uint8Array)
      );
    });

    it('should include BaseEvent fields in published event', async () => {
      const { publisher } = await setupPublisher();
      await publisher.connect('nats://localhost:4222');

      const completedEvent = {
        scan_id: '550e8400-e29b-41d4-a716-446655440000',
        community_server_id: '660e8400-e29b-41d4-a716-446655440000',
        messages_scanned: 100,
      };

      await publisher.publishBulkScanCompleted(completedEvent);

      expect(mockCodecEncode).toHaveBeenCalledTimes(1);
      const encodedJson = mockCodecEncode.mock.calls[0][0];
      const parsedEvent = JSON.parse(encodedJson);

      expect(parsedEvent.event_id).toBeDefined();
      expect(typeof parsedEvent.event_id).toBe('string');
      expect(parsedEvent.event_id.length).toBeGreaterThan(0);
      expect(parsedEvent.event_type).toBe(EventType.BULK_SCAN_COMPLETED);
      expect(parsedEvent.version).toBe('1.0');
      expect(parsedEvent.timestamp).toBeDefined();
      expect(parsedEvent.metadata).toBeDefined();
      expect(typeof parsedEvent.metadata).toBe('object');
      expect(parsedEvent.scan_id).toBe(completedEvent.scan_id);
      expect(parsedEvent.community_server_id).toBe(completedEvent.community_server_id);
      expect(parsedEvent.messages_scanned).toBe(completedEvent.messages_scanned);
    });

    it('should handle zero messages scanned', async () => {
      const { publisher } = await setupPublisher();
      await publisher.connect('nats://localhost:4222');

      const completedEvent = {
        scan_id: '550e8400-e29b-41d4-a716-446655440000',
        community_server_id: '660e8400-e29b-41d4-a716-446655440000',
        messages_scanned: 0,
      };

      await publisher.publishBulkScanCompleted(completedEvent);

      const encodedJson = mockCodecEncode.mock.calls[0][0];
      const parsedEvent = JSON.parse(encodedJson);
      expect(parsedEvent.messages_scanned).toBe(0);
      expect(parsedEvent.event_id).toBeDefined();
      expect(mockJsPublish).toHaveBeenCalled();
    });

    it('should throw error when publish fails', async () => {
      const { publisher } = await setupPublisher();
      await publisher.connect('nats://localhost:4222');

      const publishError = new Error('Publish failed');
      mockJsPublish.mockRejectedValueOnce(publishError);

      const completedEvent = {
        scan_id: '550e8400-e29b-41d4-a716-446655440000',
        community_server_id: '660e8400-e29b-41d4-a716-446655440000',
        messages_scanned: 10,
      };

      await expect(publisher.publishBulkScanCompleted(completedEvent)).rejects.toThrow(
        'Publish failed'
      );
    });
  });

  describe('publishBulkScanBatch', () => {
    it('should throw error if not connected', async () => {
      const { publisher } = await setupPublisher();

      const batchData = {
        scan_id: '550e8400-e29b-41d4-a716-446655440000',
        community_server_id: '660e8400-e29b-41d4-a716-446655440000',
        initiated_by: 'user-123',
        batch_number: 1,
        is_final_batch: false,
        messages: [],
        cutoff_timestamp: new Date().toISOString(),
      };

      await expect(publisher.publishBulkScanBatch(NATS_SUBJECTS.BULK_SCAN_BATCH, batchData)).rejects.toThrow(
        'NATS connection not established. Call connect() first.'
      );
    });

    it('should include BaseEvent fields in published batch event', async () => {
      const { publisher } = await setupPublisher();
      await publisher.connect('nats://localhost:4222');

      const batchData = {
        scan_id: '550e8400-e29b-41d4-a716-446655440000',
        community_server_id: '660e8400-e29b-41d4-a716-446655440000',
        initiated_by: 'user-123',
        batch_number: 1,
        is_final_batch: false,
        messages: [
          {
            message_id: 'msg-1',
            channel_id: 'ch-1',
            community_server_id: '660e8400-e29b-41d4-a716-446655440000',
            content: 'Test message',
            author_id: 'author-1',
            timestamp: new Date().toISOString(),
          }
        ],
        cutoff_timestamp: new Date().toISOString(),
      };

      await publisher.publishBulkScanBatch(NATS_SUBJECTS.BULK_SCAN_BATCH, batchData);

      expect(mockCodecEncode).toHaveBeenCalledTimes(1);
      const encodedJson = mockCodecEncode.mock.calls[0][0];
      const parsedEvent = JSON.parse(encodedJson);

      expect(parsedEvent.event_id).toBeDefined();
      expect(typeof parsedEvent.event_id).toBe('string');
      expect(parsedEvent.event_type).toBe(EventType.BULK_SCAN_MESSAGE_BATCH);
      expect(parsedEvent.version).toBe('1.0');
      expect(parsedEvent.timestamp).toBeDefined();
      expect(parsedEvent.metadata).toBeDefined();
      expect(parsedEvent.scan_id).toBe(batchData.scan_id);
      expect(parsedEvent.batch_number).toBe(batchData.batch_number);
      expect(parsedEvent.is_final_batch).toBe(batchData.is_final_batch);
      expect(parsedEvent.messages).toHaveLength(1);
    });

    it('should publish to correct subject', async () => {
      const { publisher } = await setupPublisher();
      await publisher.connect('nats://localhost:4222');

      const batchData = {
        scan_id: '550e8400-e29b-41d4-a716-446655440000',
        community_server_id: '660e8400-e29b-41d4-a716-446655440000',
        initiated_by: 'user-123',
        batch_number: 1,
        is_final_batch: true,
        messages: [],
        cutoff_timestamp: new Date().toISOString(),
      };

      await publisher.publishBulkScanBatch(NATS_SUBJECTS.BULK_SCAN_BATCH, batchData);

      expect(mockJsPublish).toHaveBeenCalledWith(
        NATS_SUBJECTS.BULK_SCAN_BATCH,
        expect.any(Uint8Array)
      );
    });
  });
});
