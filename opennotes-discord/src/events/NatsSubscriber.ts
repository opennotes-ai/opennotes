import { connect, NatsConnection, JsMsg, StringCodec, consumerOpts } from 'nats';
import { logger } from '../logger.js';
import { sanitizeConnectionUrl } from '../utils/url-sanitizer.js';
import { safeJSONParse } from '../utils/safe-json.js';
import type { ScoreUpdateEvent } from './types.js';

export class NatsSubscriber {
  private nc?: NatsConnection;
  private readonly codec = StringCodec();
  private readonly maxReconnectAttempts: number;
  private readonly reconnectWait: number;
  private readonly consumerName: string;
  private consumerIterator?: AsyncIterable<JsMsg>;
  private customSubject?: string;

  constructor() {
    this.maxReconnectAttempts = parseInt(process.env.NATS_MAX_RECONNECT_ATTEMPTS || '10', 10);
    this.reconnectWait = parseInt(process.env.NATS_RECONNECT_WAIT || '2', 10) * 1000;

    const baseConsumerName = process.env.NATS_CONSUMER_GROUP || 'discord-bot-score-updates-v3';
    const isTest = process.env.NODE_ENV === 'test' || process.env.JEST_WORKER_ID !== undefined;
    this.consumerName = isTest
      ? `${baseConsumerName}-${Date.now()}-${Math.random().toString(36).substring(7)}`
      : baseConsumerName;
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
        name: 'opennotes-discord-bot',
      };

      if (hasAuth) {
        connectOptions.user = natsUsername;
        connectOptions.pass = natsPassword;
      }

      this.nc = await connect(connectOptions);

      logger.info('Connected to NATS server', {
        url: sanitizeConnectionUrl(natsUrl),
        hasAuth,
      });

      this.setupConnectionHandlers();
    } catch (error) {
      logger.error('Failed to connect to NATS', {
        error: error instanceof Error ? error.message : String(error),
        url: sanitizeConnectionUrl(natsUrl),
      });
      throw error;
    }
  }

  setCustomSubject(subject: string): void {
    this.customSubject = subject;
  }

  async subscribeToScoreUpdates(
    handler: (event: ScoreUpdateEvent) => Promise<void>
  ): Promise<void> {
    if (!this.nc) {
      throw new Error('NATS connection not established. Call connect() first.');
    }

    const subject = this.customSubject || 'OPENNOTES.note_score_updated';

    try {
      const js = this.nc.jetstream();

      // Use ephemeral consumer for async iterator pattern
      // deliverTo() is required by nats.js for async iterator consumers
      // Use a unique subject that won't conflict with the main stream
      const deliverSubject = `_OPENNOTES_DELIVER.${Date.now()}.${Math.random().toString(36).substring(7)}`;

      const opts = consumerOpts()
        .deliverNew()
        .ackExplicit()
        .ackWait(30_000)
        .maxDeliver(3)
        .deliverTo(deliverSubject);

      // Create the JetStream consumer which will deliver to the delivery subject
      this.consumerIterator = await js.subscribe(subject, opts);

      logger.info('Subscribed to score update events with JetStream consumer group', {
        subject,
        consumerName: this.consumerName,
        deliverPolicy: 'new',
        ackPolicy: 'explicit',
        ackWaitMs: 30000,
        maxDeliver: 3,
      });

      // Start the consumer loop and wait for it to actually start
      // Use a microtask queue to ensure the iterator loop starts before resolving
      const loopStartPromise = new Promise<void>((resolve) => {
        void (async (): Promise<void> => {
          logger.info('Starting message consumer loop for score updates');

          // Yield control to allow the iterator to start consuming
          await new Promise(r => setImmediate(r));
          resolve();

          let messageCount = 0;
          for await (const msg of this.consumerIterator!) {
            messageCount++;
            logger.info('Received NATS message', { messageCount, subject: msg.subject });
            try {
              const data = this.codec.decode(msg.data);
              const event = safeJSONParse<ScoreUpdateEvent>(data, {
                validate: (parsed) => {
                  const isValid =
                    typeof parsed === 'object' &&
                    parsed !== null &&
                    'note_id' in parsed &&
                    'score' in parsed;

                  if (!isValid) {
                    logger.warn('Invalid score update event structure', { parsed });
                  }

                  return isValid;
                },
              });

              logger.debug('Received score update event', {
                noteId: event.note_id,
                score: event.score,
                confidence: event.confidence,
                hasDiscordContext: !!event.original_message_id,
                redeliveryCount: msg.info?.redeliveryCount || 0,
              });

              await handler(event);

              msg.ack();

              logger.debug('Acknowledged score update event', {
                noteId: event.note_id,
              });
            } catch (error) {
              logger.error('Error processing score update event', {
                error: error instanceof Error ? error.message : String(error),
                stack: error instanceof Error ? error.stack : undefined,
              });

              msg.nak();
              logger.warn('Negative acknowledged score update event for redelivery', {
                redeliveryCount: msg.info?.redeliveryCount || 0,
              });
            }
          }
        })();
      });

      // Wait for the consumer loop to actually start
      await loopStartPromise;
    } catch (error) {
      logger.error('Failed to subscribe to score updates', {
        error: error instanceof Error ? error.message : String(error),
        subject,
      });
      throw error;
    }
  }

  async close(): Promise<void> {
    if (this.consumerIterator) {
      this.consumerIterator = undefined;
      logger.info('Unsubscribed from score update events');
    }

    if (this.nc) {
      await this.nc.close();
      this.nc = undefined;
      logger.info('Closed NATS connection');
    }
  }

  isConnected(): boolean {
    return this.nc !== undefined && !this.nc.isClosed();
  }

  private setupConnectionHandlers(): void {
    if (!this.nc) {return;}

    void (async (): Promise<void> => {
      for await (const status of this.nc!.status()) {
        switch (status.type as string) {
          case 'disconnect':
            logger.warn('Disconnected from NATS server');
            break;
          case 'reconnect':
            logger.info('Reconnected to NATS server', {
              server: status.data,
            });
            break;
          case 'reconnecting':
            logger.warn('Attempting to reconnect to NATS...', {
              attempt: status.data,
            });
            break;
          case 'error':
            logger.error('NATS connection error', {
              error: status.data,
            });
            break;
        }
      }
    })();
  }
}
