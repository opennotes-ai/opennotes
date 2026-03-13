import { jest, describe, it, expect, beforeEach } from '@jest/globals';
import {
  flaggedMessageFactory,
  latestScanResponseFactory,
} from '../factories/index.js';
import type { FlaggedMessageResource } from '../../src/lib/api-client.js';

describe('formatScanStatus', () => {
  let formatScanStatus: typeof import('../../src/lib/scan-status-formatter.js').formatScanStatus;
  let formatScanStatusPaginated: typeof import('../../src/lib/scan-status-formatter.js').formatScanStatusPaginated;

  beforeEach(async () => {
    const module = await import('../../src/lib/scan-status-formatter.js');
    formatScanStatus = module.formatScanStatus;
    formatScanStatusPaginated = module.formatScanStatusPaginated;
  });

  describe('pending status', () => {
    it('should format pending scan status', () => {
      const scan = latestScanResponseFactory.build(
        { data: { type: 'bulk-scans', id: 'scan-123', attributes: { status: 'pending', initiated_at: new Date().toISOString(), messages_scanned: 0, messages_flagged: 0 } } },
        { transient: { status: 'pending', messagesScanned: 0 } }
      );

      const result = formatScanStatus({
        scan,
        guildId: 'guild-456',
        days: 7,
      });

      expect(result.content).toContain('pending');
      expect(result.content).toContain('scan-123');
    });
  });

  describe('in_progress status', () => {
    it('should format in_progress scan status', () => {
      const scan = latestScanResponseFactory.build(
        { data: { type: 'bulk-scans', id: 'scan-123', attributes: { status: 'in_progress', initiated_at: new Date().toISOString(), messages_scanned: 50, messages_flagged: 0 } } },
        { transient: { status: 'in_progress', messagesScanned: 50 } }
      );

      const result = formatScanStatus({
        scan,
        guildId: 'guild-456',
        days: 7,
      });

      expect(result.content).toContain('in progress');
      expect(result.content).toContain('50');
    });
  });

  describe('completed status with no flagged messages', () => {
    it('should show no flagged content message', () => {
      const scan = latestScanResponseFactory.build(
        { data: { type: 'bulk-scans', id: 'scan-123', attributes: { status: 'completed', initiated_at: new Date().toISOString(), messages_scanned: 100, messages_flagged: 0 } } },
        { transient: { status: 'completed', messagesScanned: 100 } }
      );

      const result = formatScanStatus({
        scan,
        guildId: 'guild-456',
        days: 7,
      });

      expect(result.content).toMatch(/complete/i);
      expect(result.content).toMatch(/no.*flagged|no.*misinformation/i);
      expect(result.content).toContain('100');
    });
  });

  describe('completed status with flagged messages', () => {
    it('should display preview at top, then link to message, then confidence', () => {
      const flaggedMessages = [
        flaggedMessageFactory.build(
          {
            id: 'msg-1',
            attributes: {
              channel_id: 'ch-1',
              content: 'This vaccine causes autism',
              author_id: '00000000-0000-0001-aaaa-000000000001',
              timestamp: new Date().toISOString(),
              matches: [{
                scan_type: 'similarity' as const,
                score: 0.95,
                matched_claim: 'Vaccines cause autism',
                matched_source: 'snopes',
                fact_check_item_id: '12345678-1234-1234-1234-123456789abc',
              }],
            },
          },
          { transient: { matchScore: 0.95, matchedClaim: 'Vaccines cause autism' } }
        ),
      ];

      const scan = latestScanResponseFactory.build(
        {
          data: { type: 'bulk-scans', id: 'scan-123', attributes: { status: 'completed', initiated_at: new Date().toISOString(), messages_scanned: 100, messages_flagged: 1 } },
          included: flaggedMessages,
        },
        { transient: { status: 'completed', messagesScanned: 100, flaggedMessages } }
      );

      const result = formatScanStatus({
        scan,
        guildId: 'guild-456',
        days: 7,
      });

      const lines = result.content.split('\n').filter(l => l.trim());
      const resultBlock = lines.slice(lines.findIndex(l => l.includes('**1.**')));

      expect(resultBlock[0]).toContain('Preview:');
      expect(resultBlock[0]).toContain('This vaccine causes autism');
      expect(resultBlock[1]).toMatch(/\(link to message\)/);
      expect(resultBlock[1]).toMatch(/discord\.com\/channels/);
      expect(resultBlock[2]).toContain('Confidence:');
      expect(resultBlock[2]).toContain('95%');
    });

    it('should NOT include Matched field', () => {
      const flaggedMessages = [
        flaggedMessageFactory.build(
          {
            id: 'msg-1',
            attributes: {
              channel_id: 'ch-1',
              content: 'This vaccine causes autism',
              author_id: '00000000-0000-0001-aaaa-000000000001',
              timestamp: new Date().toISOString(),
              matches: [{
                scan_type: 'similarity' as const,
                score: 0.95,
                matched_claim: 'Vaccines cause autism',
                matched_source: 'snopes',
                fact_check_item_id: '12345678-1234-1234-1234-123456789abc',
              }],
            },
          }
        ),
      ];

      const scan = latestScanResponseFactory.build(
        {
          data: { type: 'bulk-scans', id: 'scan-123', attributes: { status: 'completed', initiated_at: new Date().toISOString(), messages_scanned: 100, messages_flagged: 1 } },
          included: flaggedMessages,
        },
        { transient: { status: 'completed', messagesScanned: 100, flaggedMessages } }
      );

      const result = formatScanStatus({
        scan,
        guildId: 'guild-456',
        days: 7,
      });

      expect(result.content).not.toContain('Matched:');
    });

    it('should include flagged message details', () => {
      const flaggedMessages: FlaggedMessageResource[] = [
        flaggedMessageFactory.build({
          id: 'msg-1',
          attributes: {
            channel_id: 'ch-1',
            content: 'This vaccine causes autism',
            author_id: '00000000-0000-0001-aaaa-000000000001',
            timestamp: new Date().toISOString(),
            matches: [{
              scan_type: 'similarity' as const,
              score: 0.95,
              matched_claim: 'Vaccines cause autism',
              matched_source: 'snopes',
              fact_check_item_id: '12345678-1234-1234-1234-123456789abc',
            }],
          },
        }),
        flaggedMessageFactory.build({
          id: 'msg-2',
          attributes: {
            channel_id: 'ch-2',
            content: '5G towers spread COVID',
            author_id: '00000000-0000-0001-aaaa-000000000002',
            timestamp: new Date().toISOString(),
            matches: [{
              scan_type: 'similarity' as const,
              score: 0.85,
              matched_claim: '5G causes COVID-19',
              matched_source: 'snopes',
              fact_check_item_id: '12345678-1234-1234-1234-123456789def',
            }],
          },
        }),
      ];

      const scan = latestScanResponseFactory.build(
        {
          data: { type: 'bulk-scans', id: 'scan-123', attributes: { status: 'completed', initiated_at: new Date().toISOString(), messages_scanned: 100, messages_flagged: 2 } },
          included: flaggedMessages,
        },
        { transient: { status: 'completed', messagesScanned: 100, flaggedMessages } }
      );

      const result = formatScanStatus({
        scan,
        guildId: 'guild-456',
        days: 7,
      });

      expect(result.content).toContain('2');
      expect(result.content).toContain('95%');
      expect(result.content).toMatch(/discord\.com\/channels/);
    });

    it('should limit displayed results to 10', () => {
      const flaggedMessages = Array.from({ length: 15 }, (_, i) =>
        flaggedMessageFactory.build({
          id: `msg-${i}`,
          attributes: {
            channel_id: 'ch-1',
            content: `Message ${i}`,
            author_id: `author-${i}`,
            timestamp: new Date().toISOString(),
            matches: [{
              scan_type: 'similarity' as const,
              score: 0.9,
              matched_claim: `Claim ${i}`,
              matched_source: 'snopes',
              fact_check_item_id: `fact-${i}`,
            }],
          },
        })
      );

      const scan = latestScanResponseFactory.build(
        {
          data: { type: 'bulk-scans', id: 'scan-123', attributes: { status: 'completed', initiated_at: new Date().toISOString(), messages_scanned: 100, messages_flagged: 15 } },
          included: flaggedMessages,
        },
        { transient: { status: 'completed', messagesScanned: 100, flaggedMessages } }
      );

      const result = formatScanStatus({
        scan,
        guildId: 'guild-456',
        days: 7,
      });

      expect(result.content).toContain('5 more');
    });
  });

  describe('failed status', () => {
    it('should format failed scan status', () => {
      const scan = latestScanResponseFactory.build(
        { data: { type: 'bulk-scans', id: 'scan-123', attributes: { status: 'failed', initiated_at: new Date().toISOString(), messages_scanned: 0, messages_flagged: 0 } } },
        { transient: { status: 'failed', messagesScanned: 0 } }
      );

      const result = formatScanStatus({
        scan,
        guildId: 'guild-456',
        days: 7,
      });

      expect(result.content).toMatch(/failed/i);
      expect(result.content).toContain('scan-123');
    });
  });

  describe('warning message', () => {
    it('should include warning message when provided', () => {
      const scan = latestScanResponseFactory.build(
        { data: { type: 'bulk-scans', id: 'scan-123', attributes: { status: 'completed', initiated_at: new Date().toISOString(), messages_scanned: 100, messages_flagged: 0 } } },
        { transient: { status: 'completed', messagesScanned: 100 } }
      );

      const result = formatScanStatus({
        scan,
        guildId: 'guild-456',
        days: 7,
        warningMessage: 'Some batches failed to process',
      });

      expect(result.content).toContain('Warning');
      expect(result.content).toContain('Some batches failed to process');
    });
  });

  describe('days parameter', () => {
    it('should show singular day when days is 1', () => {
      const scan = latestScanResponseFactory.build(
        { data: { type: 'bulk-scans', id: 'scan-123', attributes: { status: 'completed', initiated_at: new Date().toISOString(), messages_scanned: 100, messages_flagged: 0 } } },
        { transient: { status: 'completed', messagesScanned: 100 } }
      );

      const result = formatScanStatus({
        scan,
        guildId: 'guild-456',
        days: 1,
      });

      expect(result.content).toMatch(/1 day\b/);
      expect(result.content).not.toContain('1 days');
    });

    it('should show plural days when days is greater than 1', () => {
      const scan = latestScanResponseFactory.build(
        { data: { type: 'bulk-scans', id: 'scan-123', attributes: { status: 'completed', initiated_at: new Date().toISOString(), messages_scanned: 100, messages_flagged: 0 } } },
        { transient: { status: 'completed', messagesScanned: 100 } }
      );

      const result = formatScanStatus({
        scan,
        guildId: 'guild-456',
        days: 7,
      });

      expect(result.content).toContain('7 days');
    });
  });

  describe('explanations display', () => {
    it('should display explanation when provided for a flagged message', () => {
      const flaggedMessages = [
        flaggedMessageFactory.build({
          id: 'msg-1',
          attributes: {
            channel_id: 'ch-1',
            content: 'This vaccine causes autism',
            author_id: '00000000-0000-0001-aaaa-000000000001',
            timestamp: new Date().toISOString(),
            matches: [{
              scan_type: 'similarity' as const,
              score: 0.95,
              matched_claim: 'Vaccines cause autism',
              matched_source: 'snopes',
              fact_check_item_id: '12345678-1234-1234-1234-123456789abc',
            }],
          },
        }),
      ];

      const scan = latestScanResponseFactory.build(
        {
          data: { type: 'bulk-scans', id: 'scan-123', attributes: { status: 'completed', initiated_at: new Date().toISOString(), messages_scanned: 100, messages_flagged: 1 } },
          included: flaggedMessages,
        },
        { transient: { status: 'completed', messagesScanned: 100, flaggedMessages } }
      );
      const explanations = new Map([
        ['msg-1', 'This message contains a claim that has been debunked by fact-checkers.'],
      ]);

      const result = formatScanStatus({
        scan,
        guildId: 'guild-456',
        days: 7,
        explanations,
      });

      expect(result.content).toContain('Explanation:');
      expect(result.content).toContain('debunked by fact-checkers');
    });

    it('should not display explanation when not provided', () => {
      const flaggedMessages = [
        flaggedMessageFactory.build({
          id: 'msg-1',
          attributes: {
            channel_id: 'ch-1',
            content: 'Some content',
            author_id: '00000000-0000-0001-aaaa-000000000001',
            timestamp: new Date().toISOString(),
            matches: [{
              scan_type: 'similarity' as const,
              score: 0.85,
              matched_claim: 'Matched claim',
              matched_source: 'snopes',
              fact_check_item_id: '12345678-1234-1234-1234-123456789abc',
            }],
          },
        }),
      ];

      const scan = latestScanResponseFactory.build(
        {
          data: { type: 'bulk-scans', id: 'scan-123', attributes: { status: 'completed', initiated_at: new Date().toISOString(), messages_scanned: 100, messages_flagged: 1 } },
          included: flaggedMessages,
        },
        { transient: { status: 'completed', messagesScanned: 100, flaggedMessages } }
      );

      const result = formatScanStatus({
        scan,
        guildId: 'guild-456',
        days: 7,
      });

      expect(result.content).not.toContain('Explanation:');
    });
  });

  describe('includeButtons option', () => {
    it('should not include buttons when includeButtons is false', () => {
      const flaggedMessages = [
        flaggedMessageFactory.build({
          id: 'msg-1',
          attributes: {
            channel_id: 'ch-1',
            content: 'Flagged content',
            author_id: '00000000-0000-0001-aaaa-000000000001',
            timestamp: new Date().toISOString(),
            matches: [{
              scan_type: 'similarity' as const,
              score: 0.9,
              matched_claim: 'Claim',
              matched_source: 'snopes',
              fact_check_item_id: '12345678-1234-1234-1234-123456789abc',
            }],
          },
        }),
      ];

      const scan = latestScanResponseFactory.build(
        {
          data: { type: 'bulk-scans', id: 'scan-123', attributes: { status: 'completed', initiated_at: new Date().toISOString(), messages_scanned: 100, messages_flagged: 1 } },
          included: flaggedMessages,
        },
        { transient: { status: 'completed', messagesScanned: 100, flaggedMessages } }
      );

      const result = formatScanStatus({
        scan,
        guildId: 'guild-456',
        days: 7,
        includeButtons: false,
      });

      expect(result.components).toBeUndefined();
    });

    it('should include buttons when includeButtons is true and there are flagged messages', () => {
      const flaggedMessages = [
        flaggedMessageFactory.build({
          id: 'msg-1',
          attributes: {
            channel_id: 'ch-1',
            content: 'Flagged content',
            author_id: '00000000-0000-0001-aaaa-000000000001',
            timestamp: new Date().toISOString(),
            matches: [{
              scan_type: 'similarity' as const,
              score: 0.9,
              matched_claim: 'Claim',
              matched_source: 'snopes',
              fact_check_item_id: '12345678-1234-1234-1234-123456789abc',
            }],
          },
        }),
      ];

      const scan = latestScanResponseFactory.build(
        {
          data: { type: 'bulk-scans', id: 'scan-123', attributes: { status: 'completed', initiated_at: new Date().toISOString(), messages_scanned: 100, messages_flagged: 1 } },
          included: flaggedMessages,
        },
        { transient: { status: 'completed', messagesScanned: 100, flaggedMessages } }
      );

      const result = formatScanStatus({
        scan,
        guildId: 'guild-456',
        days: 7,
        includeButtons: true,
      });

      expect(result.components).toBeDefined();
      expect(result.components!.length).toBeGreaterThan(0);
    });
  });
});

describe('formatScanStatusPaginated', () => {
  let formatScanStatusPaginated: typeof import('../../src/lib/scan-status-formatter.js').formatScanStatusPaginated;

  beforeEach(async () => {
    const module = await import('../../src/lib/scan-status-formatter.js');
    formatScanStatusPaginated = module.formatScanStatusPaginated;
  });

  it('should paginate pending scan status without using the completed header', () => {
    const scan = latestScanResponseFactory.build(
      {
        data: {
          type: 'bulk-scans',
          id: 'scan-pending-123',
          attributes: {
            status: 'pending',
            initiated_at: new Date().toISOString(),
            messages_scanned: 0,
            messages_flagged: 0,
          },
        },
      },
      { transient: { status: 'pending', messagesScanned: 0 } }
    );

    const result = formatScanStatusPaginated({
      scan,
      guildId: 'guild-456',
      days: 7,
    });

    expect(result.header).toContain('Pending');
    expect(result.header).not.toContain('Scan Complete');
    expect(result.pages.pages[0]).toContain('waiting to be processed');
  });

  it('should paginate in-progress scan status without flagged summary text', () => {
    const scan = latestScanResponseFactory.build(
      {
        data: {
          type: 'bulk-scans',
          id: 'scan-progress-123',
          attributes: {
            status: 'in_progress',
            initiated_at: new Date().toISOString(),
            messages_scanned: 42,
            messages_flagged: 0,
          },
        },
      },
      { transient: { status: 'in_progress', messagesScanned: 42 } }
    );

    const result = formatScanStatusPaginated({
      scan,
      guildId: 'guild-456',
      days: 7,
    });

    expect(result.header).toContain('In Progress');
    expect(result.header).not.toContain('Flagged');
    expect(result.pages.pages[0]).toContain('Messages scanned so far');
  });

  it('should paginate failed scan status without using the completed header', () => {
    const scan = latestScanResponseFactory.build(
      {
        data: {
          type: 'bulk-scans',
          id: 'scan-failed-123',
          attributes: {
            status: 'failed',
            initiated_at: new Date().toISOString(),
            messages_scanned: 17,
            messages_flagged: 0,
          },
        },
      },
      { transient: { status: 'failed', messagesScanned: 17 } }
    );

    const result = formatScanStatusPaginated({
      scan,
      guildId: 'guild-456',
      days: 7,
    });

    expect(result.header).toContain('Failed');
    expect(result.header).not.toContain('Scan Complete');
    expect(result.pages.pages[0]).toContain('failed due to processing errors');
  });

  it('should paginate included flagged messages for failed scans with partial results', () => {
    const flaggedMessages = [
      flaggedMessageFactory.build({
        id: 'msg-1',
        attributes: {
          channel_id: 'ch-1',
          content: 'This vaccine causes autism',
          author_id: '00000000-0000-0001-aaaa-000000000001',
          timestamp: new Date().toISOString(),
          matches: [{
            scan_type: 'similarity' as const,
            score: 0.95,
            matched_claim: 'Vaccines cause autism',
            matched_source: 'snopes',
            fact_check_item_id: '12345678-1234-1234-1234-123456789abc',
          }],
        },
      }),
    ];

    const scan = latestScanResponseFactory.build(
      {
        data: {
          type: 'bulk-scans',
          id: 'scan-failed-partial-123',
          attributes: {
            status: 'failed',
            initiated_at: new Date().toISOString(),
            messages_scanned: 17,
            messages_flagged: 1,
          },
        },
        included: flaggedMessages,
      },
      { transient: { status: 'failed', messagesScanned: 17, flaggedMessages } }
    );

    const result = formatScanStatusPaginated({
      scan,
      guildId: 'guild-456',
      days: 7,
    });

    expect(result.header).toContain('Failed');
    expect(result.header).not.toContain('Scan Complete');
    expect(result.pages.pages[0]).toContain('Preview:');
    expect(result.pages.pages[0]).toContain('This vaccine causes autism');
    expect(result.pages.pages[0]).toContain('Confidence: **95%**');
    expect(result.pages.pages[0]).toContain('failed due to processing errors');
  });

  it('should keep the no-results body for completed scans with zero flagged messages', () => {
    const scan = latestScanResponseFactory.build(
      {
        data: {
          type: 'bulk-scans',
          id: 'scan-complete-empty-123',
          attributes: {
            status: 'completed',
            initiated_at: new Date().toISOString(),
            messages_scanned: 17,
            messages_flagged: 0,
          },
        },
        included: [],
      },
      { transient: { status: 'completed', messagesScanned: 17, flaggedMessages: [] } }
    );

    const result = formatScanStatusPaginated({
      scan,
      guildId: 'guild-456',
      days: 7,
    });

    expect(result.header).toContain('Scan Complete');
    expect(result.header).toContain('**Flagged:** 0');
    expect(result.pages.pages[0]).toContain('No flagged content found');
    expect(result.pages.pages[0]).toContain('No flashpoints or potential misinformation were detected');
  });
});
