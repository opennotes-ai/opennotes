import { jest, describe, it, expect, beforeEach } from '@jest/globals';
import type { LatestScanResponse, FlaggedMessageResource } from '../../src/lib/api-client.js';

function createFlaggedMessageResource(
  id: string,
  channelId: string,
  content: string,
  matchScore: number,
  matchedClaim: string,
  factCheckItemId: string = '12345678-1234-1234-1234-123456789abc'
): FlaggedMessageResource {
  return {
    type: 'flagged-messages',
    id,
    attributes: {
      channel_id: channelId,
      content,
      author_id: 'author-1',
      timestamp: new Date().toISOString(),
      matches: [
        {
          scan_type: 'similarity' as const,
          score: matchScore,
          matched_claim: matchedClaim,
          matched_source: 'snopes',
          fact_check_item_id: factCheckItemId,
        },
      ],
    },
  };
}

function createLatestScanResponse(
  scanId: string,
  status: string,
  messagesScanned: number,
  flaggedMessages: FlaggedMessageResource[] = []
): LatestScanResponse {
  return {
    data: {
      type: 'bulk-scans',
      id: scanId,
      attributes: {
        status,
        initiated_at: new Date().toISOString(),
        messages_scanned: messagesScanned,
        messages_flagged: flaggedMessages.length,
      },
    },
    included: flaggedMessages,
    jsonapi: { version: '1.1' },
  };
}

describe('formatScanStatus', () => {
  let formatScanStatus: typeof import('../../src/lib/scan-status-formatter.js').formatScanStatus;

  beforeEach(async () => {
    const module = await import('../../src/lib/scan-status-formatter.js');
    formatScanStatus = module.formatScanStatus;
  });

  describe('pending status', () => {
    it('should format pending scan status', () => {
      const scan = createLatestScanResponse('scan-123', 'pending', 0);

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
      const scan = createLatestScanResponse('scan-123', 'in_progress', 50);

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
      const scan = createLatestScanResponse('scan-123', 'completed', 100);

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
      const flaggedMessages: FlaggedMessageResource[] = [
        createFlaggedMessageResource('msg-1', 'ch-1', 'This vaccine causes autism', 0.95, 'Vaccines cause autism'),
      ];

      const scan = createLatestScanResponse('scan-123', 'completed', 100, flaggedMessages);

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
      const flaggedMessages: FlaggedMessageResource[] = [
        createFlaggedMessageResource('msg-1', 'ch-1', 'This vaccine causes autism', 0.95, 'Vaccines cause autism'),
      ];

      const scan = createLatestScanResponse('scan-123', 'completed', 100, flaggedMessages);

      const result = formatScanStatus({
        scan,
        guildId: 'guild-456',
        days: 7,
      });

      expect(result.content).not.toContain('Matched:');
    });

    it('should include flagged message details', () => {
      const flaggedMessages: FlaggedMessageResource[] = [
        createFlaggedMessageResource('msg-1', 'ch-1', 'This vaccine causes autism', 0.95, 'Vaccines cause autism'),
        createFlaggedMessageResource('msg-2', 'ch-2', '5G towers spread COVID', 0.85, '5G causes COVID-19'),
      ];

      const scan = createLatestScanResponse('scan-123', 'completed', 100, flaggedMessages);

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
      const flaggedMessages: FlaggedMessageResource[] = Array.from({ length: 15 }, (_, i) =>
        createFlaggedMessageResource(`msg-${i}`, 'ch-1', `Message ${i}`, 0.9, `Claim ${i}`)
      );

      const scan = createLatestScanResponse('scan-123', 'completed', 100, flaggedMessages);

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
      const scan = createLatestScanResponse('scan-123', 'failed', 0);

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
      const scan = createLatestScanResponse('scan-123', 'completed', 100);

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
      const scan = createLatestScanResponse('scan-123', 'completed', 100);

      const result = formatScanStatus({
        scan,
        guildId: 'guild-456',
        days: 1,
      });

      expect(result.content).toMatch(/1 day\b/);
      expect(result.content).not.toContain('1 days');
    });

    it('should show plural days when days is greater than 1', () => {
      const scan = createLatestScanResponse('scan-123', 'completed', 100);

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
      const flaggedMessages: FlaggedMessageResource[] = [
        createFlaggedMessageResource('msg-1', 'ch-1', 'This vaccine causes autism', 0.95, 'Vaccines cause autism'),
      ];

      const scan = createLatestScanResponse('scan-123', 'completed', 100, flaggedMessages);
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
      const flaggedMessages: FlaggedMessageResource[] = [
        createFlaggedMessageResource('msg-1', 'ch-1', 'Some content', 0.85, 'Matched claim'),
      ];

      const scan = createLatestScanResponse('scan-123', 'completed', 100, flaggedMessages);

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
      const flaggedMessages: FlaggedMessageResource[] = [
        createFlaggedMessageResource('msg-1', 'ch-1', 'Flagged content', 0.9, 'Claim'),
      ];

      const scan = createLatestScanResponse('scan-123', 'completed', 100, flaggedMessages);

      const result = formatScanStatus({
        scan,
        guildId: 'guild-456',
        days: 7,
        includeButtons: false,
      });

      expect(result.components).toBeUndefined();
    });

    it('should include buttons when includeButtons is true and there are flagged messages', () => {
      const flaggedMessages: FlaggedMessageResource[] = [
        createFlaggedMessageResource('msg-1', 'ch-1', 'Flagged content', 0.9, 'Claim'),
      ];

      const scan = createLatestScanResponse('scan-123', 'completed', 100, flaggedMessages);

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
