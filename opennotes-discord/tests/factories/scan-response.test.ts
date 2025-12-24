import { describe, it, expect } from '@jest/globals';
import {
  flaggedMessageFactory,
  latestScanResponseFactory,
  noteRequestsResultFactory,
  explanationResultFactory,
} from './index.js';

describe('flaggedMessageFactory', () => {
  it('should create a flagged message with default values', () => {
    const msg = flaggedMessageFactory.build();

    expect(msg.type).toBe('flagged-messages');
    expect(msg.id).toBeDefined();
    expect(msg.attributes.channel_id).toBeDefined();
    expect(msg.attributes.content).toBeDefined();
    expect(msg.attributes.author_id).toBeDefined();
    expect(msg.attributes.timestamp).toBeDefined();
    expect(msg.attributes.matches).toHaveLength(1);
    const match = msg.attributes.matches![0];
    expect(match.scan_type).toBe('similarity');
    if (match.scan_type === 'similarity') {
      expect(match.score).toBe(0.9);
    }
  });

  it('should create a flagged message with custom values', () => {
    const msg = flaggedMessageFactory.build({
      id: 'custom-msg-id',
      attributes: {
        channel_id: 'custom-channel',
        content: 'Custom flagged content',
        author_id: 'custom-author',
        timestamp: '2025-01-01T00:00:00Z',
        matches: [{
          scan_type: 'similarity' as const,
          score: 0.75,
          matched_claim: 'Custom claim',
          matched_source: 'custom-source',
          fact_check_item_id: 'custom-fact-id',
        }],
      },
    });

    expect(msg.id).toBe('custom-msg-id');
    expect(msg.attributes.channel_id).toBe('custom-channel');
    expect(msg.attributes.content).toBe('Custom flagged content');
    const match = msg.attributes.matches![0];
    if (match.scan_type === 'similarity') {
      expect(match.score).toBe(0.75);
    }
  });

  it('should create multiple unique flagged messages with buildList', () => {
    const messages = flaggedMessageFactory.buildList(3);

    expect(messages.length).toBe(3);
    expect(messages[0].id).not.toBe(messages[1].id);
    expect(messages[1].id).not.toBe(messages[2].id);
  });
});

describe('latestScanResponseFactory', () => {
  it('should create a scan response with default values', () => {
    const scan = latestScanResponseFactory.build();

    expect(scan.data.type).toBe('bulk-scans');
    expect(scan.data.id).toBeDefined();
    expect(scan.data.attributes.status).toBe('completed');
    expect(scan.data.attributes.messages_scanned).toBe(100);
    expect(scan.data.attributes.messages_flagged).toBe(0);
    expect(scan.included).toEqual([]);
    expect(scan.jsonapi.version).toBe('1.1');
  });

  it('should create a scan response with custom values', () => {
    const flaggedMessages = flaggedMessageFactory.buildList(2);
    const scan = latestScanResponseFactory.build(
      {
        data: {
          type: 'bulk-scans',
          id: 'custom-scan-id',
          attributes: {
            status: 'in_progress',
            initiated_at: '2025-01-01T00:00:00Z',
            messages_scanned: 50,
            messages_flagged: 2,
          },
        },
        included: flaggedMessages,
      },
      { transient: { status: 'in_progress', messagesScanned: 50, flaggedMessages } }
    );

    expect(scan.data.id).toBe('custom-scan-id');
    expect(scan.data.attributes.status).toBe('in_progress');
    expect(scan.data.attributes.messages_scanned).toBe(50);
    expect(scan.included).toHaveLength(2);
  });
});

describe('noteRequestsResultFactory', () => {
  it('should create a note requests result with default values', () => {
    const result = noteRequestsResultFactory.build();

    expect(result.data.type).toBe('note-request-batches');
    expect(result.data.id).toBeDefined();
    expect(result.data.attributes.created_count).toBe(0);
    expect(result.data.attributes.request_ids).toEqual([]);
    expect(result.jsonapi.version).toBe('1.1');
  });

  it('should create a note requests result with custom values', () => {
    const result = noteRequestsResultFactory.build(
      {},
      { transient: { createdCount: 5, requestIds: ['req-1', 'req-2'] } }
    );

    expect(result.data.attributes.created_count).toBe(5);
    expect(result.data.attributes.request_ids).toEqual(['req-1', 'req-2']);
  });
});

describe('explanationResultFactory', () => {
  it('should create an explanation result with default values', () => {
    const result = explanationResultFactory.build();

    expect(result.data.type).toBe('scan-explanations');
    expect(result.data.id).toBeDefined();
    expect(result.data.attributes.explanation).toBeDefined();
    expect(result.jsonapi.version).toBe('1.1');
  });

  it('should create an explanation result with custom values', () => {
    const result = explanationResultFactory.build({
      data: {
        type: 'scan-explanations',
        id: 'custom-explanation-id',
        attributes: {
          explanation: 'Custom explanation text',
        },
      },
    });

    expect(result.data.id).toBe('custom-explanation-id');
    expect(result.data.attributes.explanation).toBe('Custom explanation text');
  });
});
