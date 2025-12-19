import { jest, describe, it, expect, beforeEach } from '@jest/globals';
import type { FlaggedMessage, BulkScanResultsResponse } from '../../src/types/bulk-scan.js';

describe('formatScanStatus', () => {
  let formatScanStatus: typeof import('../../src/lib/scan-status-formatter.js').formatScanStatus;

  beforeEach(async () => {
    const module = await import('../../src/lib/scan-status-formatter.js');
    formatScanStatus = module.formatScanStatus;
  });

  describe('pending status', () => {
    it('should format pending scan status', () => {
      const scan: BulkScanResultsResponse = {
        scan_id: 'scan-123',
        status: 'pending',
        messages_scanned: 0,
        flagged_messages: [],
      };

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
      const scan: BulkScanResultsResponse = {
        scan_id: 'scan-123',
        status: 'in_progress',
        messages_scanned: 50,
        flagged_messages: [],
      };

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
      const scan: BulkScanResultsResponse = {
        scan_id: 'scan-123',
        status: 'completed',
        messages_scanned: 100,
        flagged_messages: [],
      };

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
    it('should include flagged message details', () => {
      const flaggedMessages: FlaggedMessage[] = [
        {
          message_id: 'msg-1',
          channel_id: 'ch-1',
          content: 'This vaccine causes autism',
          author_id: 'author-1',
          timestamp: new Date().toISOString(),
          match_score: 0.95,
          matched_claim: 'Vaccines cause autism',
          matched_source: 'snopes',
        },
        {
          message_id: 'msg-2',
          channel_id: 'ch-2',
          content: '5G towers spread COVID',
          author_id: 'author-2',
          timestamp: new Date().toISOString(),
          match_score: 0.85,
          matched_claim: '5G causes COVID-19',
          matched_source: 'politifact',
        },
      ];

      const scan: BulkScanResultsResponse = {
        scan_id: 'scan-123',
        status: 'completed',
        messages_scanned: 100,
        flagged_messages: flaggedMessages,
      };

      const result = formatScanStatus({
        scan,
        guildId: 'guild-456',
        days: 7,
      });

      expect(result.content).toContain('2');
      expect(result.content).toContain('95%');
      expect(result.content).toContain('Vaccines cause autism');
      expect(result.content).toMatch(/discord\.com\/channels/);
    });

    it('should limit displayed results to 10', () => {
      const flaggedMessages: FlaggedMessage[] = Array.from({ length: 15 }, (_, i) => ({
        message_id: `msg-${i}`,
        channel_id: 'ch-1',
        content: `Message ${i}`,
        author_id: 'author-1',
        timestamp: new Date().toISOString(),
        match_score: 0.9,
        matched_claim: `Claim ${i}`,
        matched_source: 'snopes',
      }));

      const scan: BulkScanResultsResponse = {
        scan_id: 'scan-123',
        status: 'completed',
        messages_scanned: 100,
        flagged_messages: flaggedMessages,
      };

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
      const scan: BulkScanResultsResponse = {
        scan_id: 'scan-123',
        status: 'failed',
        messages_scanned: 0,
        flagged_messages: [],
      };

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
      const scan: BulkScanResultsResponse = {
        scan_id: 'scan-123',
        status: 'completed',
        messages_scanned: 100,
        flagged_messages: [],
      };

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
      const scan: BulkScanResultsResponse = {
        scan_id: 'scan-123',
        status: 'completed',
        messages_scanned: 100,
        flagged_messages: [],
      };

      const result = formatScanStatus({
        scan,
        guildId: 'guild-456',
        days: 1,
      });

      expect(result.content).toMatch(/1 day\b/);
      expect(result.content).not.toContain('1 days');
    });

    it('should show plural days when days is greater than 1', () => {
      const scan: BulkScanResultsResponse = {
        scan_id: 'scan-123',
        status: 'completed',
        messages_scanned: 100,
        flagged_messages: [],
      };

      const result = formatScanStatus({
        scan,
        guildId: 'guild-456',
        days: 7,
      });

      expect(result.content).toContain('7 days');
    });
  });

  describe('includeButtons option', () => {
    it('should not include buttons when includeButtons is false', () => {
      const flaggedMessages: FlaggedMessage[] = [
        {
          message_id: 'msg-1',
          channel_id: 'ch-1',
          content: 'Flagged content',
          author_id: 'author-1',
          timestamp: new Date().toISOString(),
          match_score: 0.9,
          matched_claim: 'Claim',
          matched_source: 'snopes',
        },
      ];

      const scan: BulkScanResultsResponse = {
        scan_id: 'scan-123',
        status: 'completed',
        messages_scanned: 100,
        flagged_messages: flaggedMessages,
      };

      const result = formatScanStatus({
        scan,
        guildId: 'guild-456',
        days: 7,
        includeButtons: false,
      });

      expect(result.components).toBeUndefined();
    });

    it('should include buttons when includeButtons is true and there are flagged messages', () => {
      const flaggedMessages: FlaggedMessage[] = [
        {
          message_id: 'msg-1',
          channel_id: 'ch-1',
          content: 'Flagged content',
          author_id: 'author-1',
          timestamp: new Date().toISOString(),
          match_score: 0.9,
          matched_claim: 'Claim',
          matched_source: 'snopes',
        },
      ];

      const scan: BulkScanResultsResponse = {
        scan_id: 'scan-123',
        status: 'completed',
        messages_scanned: 100,
        flagged_messages: flaggedMessages,
      };

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
