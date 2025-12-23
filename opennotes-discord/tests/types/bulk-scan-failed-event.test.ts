import { describe, test, expect } from '@jest/globals';
import {
  EventType,
  NATS_SUBJECTS,
  BulkScanFailedEvent,
  BulkScanProgressEvent,
} from '../../src/types/bulk-scan';

describe('BulkScanFailedEvent', () => {
  test('BULK_SCAN_FAILED event type should exist', () => {
    expect(EventType.BULK_SCAN_FAILED).toBe('bulk_scan.failed');
  });

  test('NATS subject for BULK_SCAN_FAILED should exist', () => {
    expect(NATS_SUBJECTS.BULK_SCAN_FAILED).toBe('OPENNOTES.bulk_scan_failed');
  });

  test('BulkScanFailedEvent interface should have required fields', () => {
    const event: BulkScanFailedEvent = {
      event_id: 'evt_test123',
      event_type: EventType.BULK_SCAN_FAILED,
      version: '1.0',
      timestamp: '2025-01-01T00:00:00Z',
      metadata: {},
      scan_id: 'scan-123',
      community_server_id: 'server-456',
      error_message: 'Database connection failed',
    };

    expect(event.event_type).toBe('bulk_scan.failed');
    expect(event.scan_id).toBe('scan-123');
    expect(event.community_server_id).toBe('server-456');
    expect(event.error_message).toBe('Database connection failed');
  });
});

describe('BulkScanProgressEvent updates', () => {
  test('BulkScanProgressEvent should have channel_ids field', () => {
    const event: BulkScanProgressEvent = {
      event_id: 'evt_test123',
      event_type: EventType.BULK_SCAN_PROGRESS,
      version: '1.0',
      timestamp: '2025-01-01T00:00:00Z',
      metadata: {},
      scan_id: 'scan-123',
      community_server_id: 'server-456',
      platform_id: '123456789',
      batch_number: 1,
      messages_in_batch: 50,
      message_scores: [],
      threshold_used: 0.6,
      channel_ids: ['ch1', 'ch2', 'ch3'],
      messages_processed: 150,
    };

    expect(event.channel_ids).toEqual(['ch1', 'ch2', 'ch3']);
  });

  test('BulkScanProgressEvent should have messages_processed field', () => {
    const event: BulkScanProgressEvent = {
      event_id: 'evt_test123',
      event_type: EventType.BULK_SCAN_PROGRESS,
      version: '1.0',
      timestamp: '2025-01-01T00:00:00Z',
      metadata: {},
      scan_id: 'scan-123',
      community_server_id: 'server-456',
      platform_id: '123456789',
      batch_number: 1,
      messages_in_batch: 50,
      message_scores: [],
      threshold_used: 0.6,
      channel_ids: [],
      messages_processed: 150,
    };

    expect(event.messages_processed).toBe(150);
  });
});
