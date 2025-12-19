import { jest, describe, it, expect, beforeEach } from '@jest/globals';
import type { JetStreamClient, NatsConnection, PubAck } from 'nats';
import { NATS_SUBJECTS } from '../../src/types/bulk-scan.js';

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

    it('should encode event data as JSON string', async () => {
      const { publisher } = await setupPublisher();
      await publisher.connect('nats://localhost:4222');

      const completedEvent = {
        scan_id: '550e8400-e29b-41d4-a716-446655440000',
        community_server_id: '660e8400-e29b-41d4-a716-446655440000',
        messages_scanned: 100,
      };

      await publisher.publishBulkScanCompleted(completedEvent);

      expect(mockCodecEncode).toHaveBeenCalledWith(JSON.stringify(completedEvent));
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

      expect(mockCodecEncode).toHaveBeenCalledWith(JSON.stringify(completedEvent));
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
});
