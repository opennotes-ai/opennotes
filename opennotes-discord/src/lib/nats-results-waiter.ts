import type { NatsConnection, JetStreamSubscription } from 'nats';
import { StringCodec, consumerOpts } from 'nats';
import { logger } from '../logger.js';
import { apiClient, type BulkScanResultsResponse } from '../api-client.js';
import {
  NATS_SUBJECTS,
  EventType,
  type BulkScanProgressEvent,
} from '../types/bulk-scan.js';
import {
  NATS_STALL_WARNING_MS,
  NATS_SILENCE_TIMEOUT_MS,
  NATS_MAX_WAIT_MS,
} from './bulk-scan-executor.js';

interface NatsResultsEventPayload {
  event_type: string;
  scan_id: string;
  messages_scanned?: number;
  messages_flagged?: number;
  error_message?: string;
  flagged_messages?: Array<{
    message_id: string;
    channel_id: string;
    content: string;
    author_id: string;
    timestamp: string;
    match_score: number;
    matched_claim: string;
    matched_source: string;
  }>;
}

export type StallWarningCallback = () => void;
export type ProgressCallback = (event: BulkScanProgressEvent) => void;

export class NatsResultsWaiter {
  private readonly scanId: string;
  private readonly nc: NatsConnection;
  private readonly codec = StringCodec();
  private stallWarningCallback?: StallWarningCallback;
  private progressCallback?: ProgressCallback;
  private stallWarningTimer?: ReturnType<typeof setTimeout>;
  private silenceTimeoutTimer?: ReturnType<typeof setTimeout>;
  private maxWaitTimer?: ReturnType<typeof setTimeout>;
  private subscriptions: JetStreamSubscription[] = [];
  private resolved = false;

  constructor(scanId: string, nc: NatsConnection) {
    this.scanId = scanId;
    this.nc = nc;
  }

  onStallWarning(callback: StallWarningCallback): void {
    this.stallWarningCallback = callback;
  }

  onProgress(callback: ProgressCallback): void {
    this.progressCallback = callback;
  }

  private resetTimers(reject?: (reason: Error) => void): void {
    if (this.stallWarningTimer) {
      clearTimeout(this.stallWarningTimer);
    }
    if (this.silenceTimeoutTimer) {
      clearTimeout(this.silenceTimeoutTimer);
    }

    this.stallWarningTimer = setTimeout(() => {
      if (!this.resolved && this.stallWarningCallback) {
        this.stallWarningCallback();
      }
    }, NATS_STALL_WARNING_MS);

    this.silenceTimeoutTimer = setTimeout(() => {
      if (!this.resolved) {
        this.cleanup();
        if (reject) {
          reject(new Error('Scan timed out: no activity for 60 seconds'));
        }
      }
    }, NATS_SILENCE_TIMEOUT_MS);
  }

  private cleanup(): void {
    this.resolved = true;
    if (this.stallWarningTimer) {
      clearTimeout(this.stallWarningTimer);
    }
    if (this.silenceTimeoutTimer) {
      clearTimeout(this.silenceTimeoutTimer);
    }
    if (this.maxWaitTimer) {
      clearTimeout(this.maxWaitTimer);
    }

    for (const sub of this.subscriptions) {
      sub.unsubscribe();
    }
  }

  async start(): Promise<BulkScanResultsResponse> {
    return new Promise<BulkScanResultsResponse>((resolve, reject) => {
      this.startInternal(resolve, reject).catch(reject);
    });
  }

  private async startInternal(
    resolve: (value: BulkScanResultsResponse) => void,
    reject: (reason: Error) => void
  ): Promise<void> {
    const js = this.nc.jetstream();

    this.maxWaitTimer = setTimeout(() => {
      if (!this.resolved) {
        this.cleanup();
        reject(new Error(`Scan timed out after ${NATS_MAX_WAIT_MS / 1000} seconds`));
      }
    }, NATS_MAX_WAIT_MS);

    this.resetTimers(reject);

    const subjects = [
      NATS_SUBJECTS.BULK_SCAN_PROCESSING_FINISHED,
      NATS_SUBJECTS.BULK_SCAN_RESULT,
      NATS_SUBJECTS.BULK_SCAN_FAILED,
      NATS_SUBJECTS.BULK_SCAN_PROGRESS,
    ];

    for (const subject of subjects) {
      try {
        const opts = consumerOpts();
        opts.deliverTo(`discord-bot-${this.scanId}-${subject.replace(/\./g, '-')}`);
        opts.manualAck();
        opts.ackExplicit();

        const sub = await js.subscribe(subject, opts);
        this.subscriptions.push(sub);

        this.processMessages(sub, resolve, reject).catch((err: unknown) => {
          logger.error('Error processing NATS messages', {
            error: err instanceof Error ? err.message : String(err),
            subject,
            scanId: this.scanId,
          });
        });
      } catch (subErr) {
        logger.warn('Failed to subscribe to NATS subject', {
          error: subErr instanceof Error ? subErr.message : String(subErr),
          subject,
          scanId: this.scanId,
        });
      }
    }
  }

  private async processMessages(
    sub: JetStreamSubscription,
    resolve: (value: BulkScanResultsResponse) => void,
    reject: (reason: Error) => void
  ): Promise<void> {
    for await (const msg of sub) {
      if (this.resolved) {
        break;
      }

      try {
        const data = this.codec.decode(msg.data);
        const event = JSON.parse(data) as NatsResultsEventPayload;

        if (event.scan_id !== this.scanId) {
          msg.ack();
          continue;
        }

        this.resetTimers(reject);

        switch (event.event_type) {
          case EventType.BULK_SCAN_PROCESSING_FINISHED:
            msg.ack();
            try {
              const results = await apiClient.getBulkScanResults(this.scanId);
              this.cleanup();
              resolve(results);
            } catch (fetchErr) {
              this.cleanup();
              reject(
                new Error(
                  `Failed to fetch results: ${fetchErr instanceof Error ? fetchErr.message : String(fetchErr)}`
                )
              );
            }
            break;

          case EventType.BULK_SCAN_RESULTS:
            msg.ack();
            this.cleanup();
            resolve({
              data: {
                id: event.scan_id,
                type: 'bulk_scan',
                attributes: {
                  status: 'completed',
                  messages_scanned: event.messages_scanned ?? 0,
                  messages_flagged: event.messages_flagged ?? 0,
                },
              },
              included: (event.flagged_messages ?? []).map((fm) => ({
                type: 'flagged_message',
                id: fm.message_id,
                attributes: fm,
              })),
              jsonapi: { version: '1.0' },
            } as unknown as BulkScanResultsResponse);
            break;

          case EventType.BULK_SCAN_FAILED:
            msg.ack();
            this.cleanup();
            reject(new Error(`Scan failed: ${event.error_message ?? 'Unknown error'}`));
            break;

          case EventType.BULK_SCAN_PROGRESS:
            msg.ack();
            if (this.progressCallback) {
              this.progressCallback(event as unknown as BulkScanProgressEvent);
            }
            break;

          default:
            msg.ack();
        }
      } catch (parseErr) {
        logger.warn('Failed to parse NATS message', {
          error: parseErr instanceof Error ? parseErr.message : String(parseErr),
          scanId: this.scanId,
        });
        msg.ack();
      }
    }
  }
}

export async function waitForNatsResults(
  scanId: string,
  nc: NatsConnection,
  options?: {
    onStallWarning?: StallWarningCallback;
    onProgress?: ProgressCallback;
  }
): Promise<BulkScanResultsResponse> {
  const waiter = new NatsResultsWaiter(scanId, nc);

  if (options?.onStallWarning) {
    waiter.onStallWarning(options.onStallWarning);
  }
  if (options?.onProgress) {
    waiter.onProgress(options.onProgress);
  }

  return waiter.start();
}
