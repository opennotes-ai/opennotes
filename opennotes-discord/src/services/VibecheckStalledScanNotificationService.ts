import {
  DiscordAPIError,
  RESTJSONErrorCodes,
  type Client,
} from 'discord.js';
import { apiClient } from '../api-client.js';
import { logger } from '../logger.js';
import {
  getStalledScan,
  markStalledScanNotified,
  type StalledScanRecord,
} from '../lib/vibecheck-stalled-scan.js';
import type {
  BulkScanFailedEvent,
  BulkScanProcessingFinishedEvent,
} from '../types/bulk-scan.js';
import { EventType } from '../types/bulk-scan.js';
import type { DistributedLock } from '../utils/distributed-lock.js';

type BulkScanTerminalEvent = BulkScanProcessingFinishedEvent | BulkScanFailedEvent;

export class VibecheckStalledScanNotificationService {
  private readonly lockTtlMs = 10 * 1000;
  private readonly lookupRetryDelayMs = 50;
  private readonly lookupRetryAttempts = 3;

  constructor(
    private readonly client: Client,
    private readonly distributedLock: DistributedLock | null = null
  ) {
    if (!this.distributedLock) {
      logger.warn('VibecheckStalledScanNotificationService initialized without distributed locking - duplicate DMs are possible in multi-instance deployment');
    }
  }

  async handleTerminalEvent(event: BulkScanTerminalEvent): Promise<void> {
    const lockKey = `vibecheck:stalled-scan:${event.scan_id}`;
    const lockAcquired = this.distributedLock
      ? await this.distributedLock.acquire(lockKey, {
        ttlMs: this.lockTtlMs,
        retryDelayMs: 50,
        maxRetries: 3,
      })
      : true;

    if (!lockAcquired) {
      logger.info('Skipping stalled scan DM - lock acquisition failed', {
        scanId: event.scan_id,
        lockKey,
      });
      return;
    }

    let stalledScan: StalledScanRecord | null = null;

    try {
      stalledScan = await this.findStalledScan(event.scan_id);
      if (!stalledScan || stalledScan.notificationState === 'sent') {
        return;
      }

      const user = await this.client.users.fetch(stalledScan.initiatorId);

      if (event.event_type === EventType.BULK_SCAN_FAILED) {
        await user.send(
          `Your stalled vibecheck scan \`${event.scan_id}\` failed.\n` +
          `Run \`/vibecheck status scan_id:${event.scan_id}\` in the server to review status or retry later.`
        );
      } else {
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
      }

      const markedDelivered = await markStalledScanNotified(event.scan_id);
      if (!markedDelivered) {
        logger.warn('Failed to persist delivered stalled scan state after DM send', {
          scanId: event.scan_id,
          initiatorId: stalledScan.initiatorId,
        });
      }
    } catch (error) {
      if (this.isPermanentDiscordDeliveryError(error)) {
        logger.warn('Skipping stalled scan DM after permanent Discord failure', {
          scanId: event.scan_id,
          initiatorId: stalledScan?.initiatorId,
          error: error.message,
          code: error.code,
          status: error.status,
        });
        return;
      }

      throw error;
    } finally {
      if (this.distributedLock) {
        try {
          await this.distributedLock.release(lockKey);
        } catch (error) {
          logger.warn('Failed to release stalled scan DM lock', {
            scanId: event.scan_id,
            lockKey,
            error: error instanceof Error ? error.message : String(error),
          });
        }
      }
    }
  }

  private async findStalledScan(scanId: string): Promise<StalledScanRecord | null> {
    for (let attempt = 0; attempt < this.lookupRetryAttempts; attempt += 1) {
      const stalledScan = await getStalledScan(scanId);
      if (stalledScan) {
        return stalledScan;
      }

      if (attempt < this.lookupRetryAttempts - 1) {
        await this.sleep(this.lookupRetryDelayMs);
      }
    }

    return null;
  }

  private async sleep(ms: number): Promise<void> {
    await new Promise((resolve) => setTimeout(resolve, ms));
  }

  private isPermanentDiscordDeliveryError(error: unknown): error is DiscordAPIError {
    if (!(error instanceof DiscordAPIError)) {
      return false;
    }

    if (typeof error.code !== 'number') {
      return false;
    }

    return new Set<number>([
      RESTJSONErrorCodes.CannotSendMessagesToThisUser,
      RESTJSONErrorCodes.UnknownUser,
      RESTJSONErrorCodes.MissingAccess,
      RESTJSONErrorCodes.MissingPermissions,
    ]).has(error.code);
  }
}
