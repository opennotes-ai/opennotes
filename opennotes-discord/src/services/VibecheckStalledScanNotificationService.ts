import type { Client } from 'discord.js';
import { apiClient } from '../api-client.js';
import { logger } from '../logger.js';
import {
  getStalledScan,
  clearStalledScan,
} from '../lib/vibecheck-stalled-scan.js';
import type {
  BulkScanFailedEvent,
  BulkScanProcessingFinishedEvent,
} from '../types/bulk-scan.js';
import { EventType } from '../types/bulk-scan.js';

type BulkScanTerminalEvent = BulkScanProcessingFinishedEvent | BulkScanFailedEvent;

export class VibecheckStalledScanNotificationService {
  constructor(private readonly client: Client) {}

  async handleTerminalEvent(event: BulkScanTerminalEvent): Promise<void> {
    const stalledScan = await getStalledScan(event.scan_id);
    if (!stalledScan) {
      return;
    }

    try {
      const user = await this.client.users.fetch(stalledScan.initiatorId);

      if (event.event_type === EventType.BULK_SCAN_FAILED) {
        await user.send(
          `Your stalled vibecheck scan \`${event.scan_id}\` failed.\n` +
          `Run \`/vibecheck status scan_id:${event.scan_id}\` in the server to review status or retry later.`
        );
        return;
      }

      let messagesScanned = event.messages_scanned;
      let flaggedCount = event.messages_flagged;

      try {
        const results = await apiClient.getBulkScanResults(event.scan_id);
        messagesScanned = results.data.attributes.messages_scanned;
        flaggedCount = results.data.attributes.messages_flagged;
      } catch (error) {
        logger.warn('Failed to fetch final stalled scan results before DM', {
          scanId: event.scan_id,
          error: error instanceof Error ? error.message : String(error),
        });
      }

      await user.send(
        `Your stalled vibecheck scan \`${event.scan_id}\` finished.\n` +
        `Messages scanned: ${messagesScanned}\n` +
        `Flagged: ${flaggedCount}\n` +
        `Run \`/vibecheck status scan_id:${event.scan_id}\` in the server for full details.`
      );
    } catch (error) {
      logger.warn('Failed to deliver stalled scan DM', {
        scanId: event.scan_id,
        initiatorId: stalledScan.initiatorId,
        error: error instanceof Error ? error.message : String(error),
      });
    } finally {
      await clearStalledScan(event.scan_id);
    }
  }
}
