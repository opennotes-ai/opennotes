import { describe, test, expect } from '@jest/globals';
import {
  EventType,
  NATS_SUBJECTS,
  BulkScanFailedEvent,
  BulkScanProgressEvent,
} from '../../src/types/bulk-scan';

describe('BulkScanFailedEvent', () => {
  test('BULK_SCAN_FAILED event type and NATS subject should be defined', () => {
    expect(EventType.BULK_SCAN_FAILED).toBeTruthy();
    expect(NATS_SUBJECTS.BULK_SCAN_FAILED).toBeTruthy();
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

    expect(event.event_type).toBe(EventType.BULK_SCAN_FAILED);
    expect(event.scan_id).toBeTruthy();
    expect(event.community_server_id).toBeTruthy();
    expect(event.error_message).toBeTruthy();
  });
});

describe('BulkScanProgressEvent updates', () => {
  test('BulkScanProgressEvent interface should support channel_ids and messages_processed fields', () => {
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

    expect(Array.isArray(event.channel_ids)).toBe(true);
    expect(typeof event.messages_processed).toBe('number');
  });
});
