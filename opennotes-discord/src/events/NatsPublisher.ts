import { connect, NatsConnection, StringCodec, JetStreamClient } from 'nats';
import { logger } from '../logger.js';
import { sanitizeConnectionUrl } from '../utils/url-sanitizer.js';
import type { BulkScanBatch, NATS_SUBJECTS } from '../types/bulk-scan.js';

export class NatsPublisher {
  private nc?: NatsConnection;
  private js?: JetStreamClient;
  private readonly codec = StringCodec();
  private readonly maxReconnectAttempts: number;
  private readonly reconnectWait: number;

  constructor() {
    this.maxReconnectAttempts = parseInt(process.env.NATS_MAX_RECONNECT_ATTEMPTS || '10', 10);
    this.reconnectWait = parseInt(process.env.NATS_RECONNECT_WAIT || '2', 10) * 1000;
  }

  async connect(url?: string): Promise<void> {
    const natsUrl = url || process.env.NATS_URL || 'nats://localhost:4222';
    const natsUsername = process.env.NATS_USERNAME;
    const natsPassword = process.env.NATS_PASSWORD;
    const hasAuth = Boolean(natsUsername && natsPassword);

    try {
      const connectOptions: Parameters<typeof connect>[0] = {
        servers: natsUrl,
        maxReconnectAttempts: this.maxReconnectAttempts,
        reconnectTimeWait: this.reconnectWait,
        name: 'opennotes-discord-bot-publisher',
      };

      if (hasAuth) {
        connectOptions.user = natsUsername;
        connectOptions.pass = natsPassword;
      }

      this.nc = await connect(connectOptions);
      this.js = this.nc.jetstream();

      logger.info('NatsPublisher connected to NATS server', {
        url: sanitizeConnectionUrl(natsUrl),
        hasAuth,
      });
    } catch (error) {
      logger.error('NatsPublisher failed to connect to NATS', {
        error: error instanceof Error ? error.message : String(error),
        url: sanitizeConnectionUrl(natsUrl),
      });
      throw error;
    }
  }

  async publishBulkScanBatch(
    subject: typeof NATS_SUBJECTS[keyof typeof NATS_SUBJECTS],
    batch: BulkScanBatch
  ): Promise<void> {
    if (!this.nc || !this.js) {
      throw new Error('NATS connection not established. Call connect() first.');
    }

    try {
      const data = this.codec.encode(JSON.stringify(batch));
      await this.js.publish(subject, data);

      logger.debug('Published bulk scan batch to NATS', {
        subject,
        scan_id: batch.scan_id,
        batch_index: batch.batch_index,
        total_batches: batch.total_batches,
        message_count: batch.messages.length,
      });
    } catch (error) {
      logger.error('Failed to publish bulk scan batch', {
        error: error instanceof Error ? error.message : String(error),
        subject,
        scan_id: batch.scan_id,
        batch_index: batch.batch_index,
      });
      throw error;
    }
  }

  async close(): Promise<void> {
    if (this.nc) {
      await this.nc.close();
      this.nc = undefined;
      this.js = undefined;
      logger.info('NatsPublisher closed NATS connection');
    }
  }

  isConnected(): boolean {
    return this.nc !== undefined && !this.nc.isClosed();
  }
}

let natsPublisherInstance: NatsPublisher | null = null;

export function getNatsPublisher(): NatsPublisher {
  if (!natsPublisherInstance) {
    natsPublisherInstance = new NatsPublisher();
  }
  return natsPublisherInstance;
}

export async function initializeNatsPublisher(): Promise<NatsPublisher> {
  const publisher = getNatsPublisher();
  if (!publisher.isConnected()) {
    await publisher.connect();
  }
  return publisher;
}

export async function closeNatsPublisher(): Promise<void> {
  if (natsPublisherInstance) {
    await natsPublisherInstance.close();
    natsPublisherInstance = null;
  }
}

export const natsPublisher = {
  publishBulkScanBatch: async (
    subject: typeof NATS_SUBJECTS[keyof typeof NATS_SUBJECTS],
    batch: BulkScanBatch
  ): Promise<void> => {
    const publisher = getNatsPublisher();
    if (!publisher.isConnected()) {
      await publisher.connect();
    }
    return publisher.publishBulkScanBatch(subject, batch);
  },
  isConnected: (): boolean => {
    return natsPublisherInstance?.isConnected() ?? false;
  },
};
