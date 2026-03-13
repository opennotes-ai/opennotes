import {
  DiscordAPIError,
  RESTJSONErrorCodes,
  type Client,
} from 'discord.js';
import { apiClient } from '../api-client.js';
import { logger } from '../logger.js';
import {
  claimStalledScanDelivery,
  getStalledScan,
  markStalledScanDeliveryFailed,
  markStalledScanNotified,
  resetStalledScanDelivery,
  STALLED_SCAN_DELIVERY_CLAIM_TTL_MS,
  type StalledScanRecord,
} from '../lib/vibecheck-stalled-scan.js';
import type {
  BulkScanFailedEvent,
  BulkScanProcessingFinishedEvent,
} from '../types/bulk-scan.js';
import { EventType } from '../types/bulk-scan.js';
import type { DistributedLock } from '../utils/distributed-lock.js';

type BulkScanTerminalEvent = BulkScanProcessingFinishedEvent | BulkScanFailedEvent;

class RetryableTerminalEventError extends Error {
  constructor(
    message: string,
    readonly reason: 'lock-contention' | 'recent-cache-miss'
  ) {
    super(message);
    this.name = 'RetryableTerminalEventError';
  }
}

export class VibecheckStalledScanNotificationService {
  private readonly activeDeliveries = new Set<string>();
  private readonly lockTtlMs = STALLED_SCAN_DELIVERY_CLAIM_TTL_MS;
  private readonly lookupRetryDelayMs = 50;
  private readonly lookupRetryAttempts = 12;
  private readonly historicalReplayThresholdMs = STALLED_SCAN_DELIVERY_CLAIM_TTL_MS * 2;

  constructor(
    private readonly client: Client,
    private readonly distributedLock: DistributedLock | null = null
  ) {
    if (!this.distributedLock) {
      logger.warn('VibecheckStalledScanNotificationService initialized without distributed locking - duplicate DMs are possible in multi-instance deployment');
    }
  }

  async handleTerminalEvent(event: BulkScanTerminalEvent): Promise<void> {
    if (this.activeDeliveries.has(event.scan_id)) {
      logger.info('Skipping stalled scan DM - delivery already in progress locally', {
        scanId: event.scan_id,
      });
      return;
    }
    this.activeDeliveries.add(event.scan_id);

    const lockKey = `vibecheck:stalled-scan:${event.scan_id}`;
    let lockAcquired = false;
    let stalledScan: StalledScanRecord | null = null;
    let stopLockKeepalive = () => {};
    const historicalReplay = this.isHistoricalReplay(event);

    try {
      lockAcquired = this.distributedLock
        ? await this.distributedLock.acquire(lockKey, {
          ttlMs: this.lockTtlMs,
          retryDelayMs: 50,
          maxRetries: 3,
        })
        : true;

      if (!lockAcquired) {
        logger.info('Retrying stalled scan DM after lock acquisition failed', {
          scanId: event.scan_id,
          lockKey,
        });
        throw new RetryableTerminalEventError(
          `Stalled scan terminal event is waiting on lock contention for ${event.scan_id}`,
          'lock-contention'
        );
      }

      stopLockKeepalive = this.startLockKeepalive(lockKey);
      stalledScan = await this.findStalledScan(event.scan_id, {
        retryOnMiss: !historicalReplay,
      });
      if (!stalledScan) {
        if (historicalReplay) {
          logger.info('Skipping historical terminal replay without stalled scan metadata', {
            scanId: event.scan_id,
            eventTimestamp: event.timestamp,
          });
          return;
        }

        throw new RetryableTerminalEventError(
          `Stalled scan metadata is not visible yet for ${event.scan_id}`,
          'recent-cache-miss'
        );
      }

      const deliveryClaim = await claimStalledScanDelivery(event.scan_id);
      if (deliveryClaim.status !== 'claimed' || !deliveryClaim.record) {
        return;
      }
      stalledScan = deliveryClaim.record;

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
      if (error instanceof RetryableTerminalEventError) {
        await resetStalledScanDelivery(event.scan_id);
        throw error;
      }

      if (this.isPermanentDiscordDeliveryError(error)) {
        await markStalledScanDeliveryFailed(event.scan_id, error.message);
        logger.warn('Skipping stalled scan DM after permanent Discord failure', {
          scanId: event.scan_id,
          initiatorId: stalledScan?.initiatorId,
          error: error.message,
          code: error.code,
          status: error.status,
        });
        return;
      }

      await resetStalledScanDelivery(event.scan_id);
      throw error;
    } finally {
      this.activeDeliveries.delete(event.scan_id);
      stopLockKeepalive();
      if (this.distributedLock && lockAcquired) {
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

  private async findStalledScan(
    scanId: string,
    options: { retryOnMiss: boolean } = { retryOnMiss: true }
  ): Promise<StalledScanRecord | null> {
    const attempts = options.retryOnMiss ? this.lookupRetryAttempts : 1;

    for (let attempt = 0; attempt < attempts; attempt += 1) {
      const stalledScan = await getStalledScan(scanId);
      if (stalledScan) {
        return stalledScan;
      }

      if (attempt < attempts - 1) {
        await this.sleep(this.lookupRetryDelayMs);
      }
    }

    return null;
  }

  private async sleep(ms: number): Promise<void> {
    await new Promise((resolve) => setTimeout(resolve, ms));
  }

  private isHistoricalReplay(event: BulkScanTerminalEvent): boolean {
    const eventTimestampMs = Date.parse(event.timestamp);
    if (Number.isNaN(eventTimestampMs)) {
      return false;
    }

    return Date.now() - eventTimestampMs > this.historicalReplayThresholdMs;
  }

  private startLockKeepalive(lockKey: string): () => void {
    if (!this.distributedLock) {
      return () => {};
    }

    const intervalMs = Math.max(1000, Math.floor(this.lockTtlMs / 2));
    const interval = setInterval(() => {
      void this.distributedLock!.extend(lockKey, this.lockTtlMs).catch((error) => {
        logger.warn('Failed to extend stalled scan DM lock', {
          lockKey,
          error: error instanceof Error ? error.message : String(error),
        });
      });
    }, intervalMs);

    return () => {
      clearInterval(interval);
    };
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
