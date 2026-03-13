import {
  connect,
  NatsConnection,
  JsMsg,
  StringCodec,
  consumerOpts,
  NatsError,
  JetStreamClient,
  JetStreamSubscription,
} from 'nats';
import { logger } from '../logger.js';
import { sanitizeConnectionUrl } from '../utils/url-sanitizer.js';
import { safeJSONParse } from '../utils/safe-json.js';
import type { ScoreUpdateEvent } from './types.js';
import type {
  BulkScanFailedEvent,
  BulkScanProcessingFinishedEvent,
  BulkScanProgressEvent,
} from '../types/bulk-scan.js';
import { EventType, NATS_SUBJECTS } from '../types/bulk-scan.js';

export class NatsSubscriber {
  private readonly retryableTerminalRedeliveryDelayMs = 30_000;
  private nc?: NatsConnection;
  private readonly codec = StringCodec();
  private readonly maxReconnectAttempts: number;
  private readonly reconnectWait: number;
  private consumerIterator?: AsyncIterable<JsMsg>;
  private customSubject?: string;

  constructor() {
    this.maxReconnectAttempts = parseInt(process.env.NATS_MAX_RECONNECT_ATTEMPTS || '10', 10);
    this.reconnectWait = parseInt(process.env.NATS_RECONNECT_WAIT || '2', 10) * 1000;
  }

  private isConsumerAlreadyExistsError(error: unknown): boolean {
    // Check message content for any Error type
    if (error instanceof Error) {
      const message = error.message?.toLowerCase() || '';
      if (
        message.includes('consumer name already in use') ||
        message.includes('consumer already exists')
      ) {
        return true;
      }
    }
    // Additional checks for NatsError-specific properties
    if (error instanceof NatsError && error.isJetStreamError()) {
      const apiError = error.api_error;
      if (apiError?.err_code === 10059 || apiError?.err_code === 10148) {
        return true;
      }
    }
    return false;
  }

  private async bindOrCreateConsumer(
    js: JetStreamClient,
    streamName: string,
    durableName: string,
    subject: string,
    deliverSubject: string,
    deliverPolicy: 'all' | 'new' = 'all'
  ): Promise<JetStreamSubscription> {
    // Try bind first - if consumer exists, this is the fastest path
    try {
      const bindOpts = consumerOpts().bind(streamName, durableName);
      const subscription = await js.subscribe(subject, bindOpts);

      if (await this.shouldRecreateConsumer(subscription, streamName, durableName, deliverPolicy)) {
        await subscription.destroy();
        logger.warn('Destroyed incompatible consumer so it can be recreated with replay support', {
          consumerName: durableName,
          streamName,
          subject,
          deliverPolicy,
        });
      } else {
        logger.info('Bound to existing consumer', { consumerName: durableName, streamName });
        return subscription;
      }
    } catch (bindError) {
      // Log the bind error but don't throw yet - we'll try to create
      // This handles both "consumer not found" AND "stream not found" errors
      logger.info('Bind failed, attempting to create consumer', {
        consumerName: durableName,
        streamName,
        bindError: bindError instanceof Error ? bindError.message : String(bindError),
      });
    }

    // Bind failed, try to create the consumer
    try {
      const createOpts = consumerOpts()
        .durable(durableName)
        .deliverGroup(durableName)
        .deliverTo(deliverSubject)
        .ackExplicit()
        .ackWait(30_000)
        .maxDeliver(3);
      if (deliverPolicy === 'new') {
        createOpts.deliverNew();
      } else {
        createOpts.deliverAll();
      }
      const subscription = await js.subscribe(subject, createOpts);
      logger.info('Created new consumer', { consumerName: durableName, streamName });
      return subscription;
    } catch (createError) {
      // If consumer already exists (race condition), retry bind
      if (this.isConsumerAlreadyExistsError(createError)) {
        logger.info('Consumer was created by another instance, retrying bind', {
          consumerName: durableName,
          streamName,
        });
        const retryBindOpts = consumerOpts().bind(streamName, durableName);
        return await js.subscribe(subject, retryBindOpts);
      }

      // For any other error, log and throw
      logger.error('Failed to create consumer', {
        consumerName: durableName,
        streamName,
        error: createError instanceof Error ? createError.message : String(createError),
      });
      throw createError;
    }
  }

  private async shouldRecreateConsumer(
    subscription: JetStreamSubscription,
    streamName: string,
    durableName: string,
    deliverPolicy: 'all' | 'new'
  ): Promise<boolean> {
    if (deliverPolicy !== 'all') {
      return false;
    }

    const consumerInfo = await subscription.consumerInfo();
    const existingPolicy = consumerInfo.config?.deliver_policy;
    const existingPolicyValue = existingPolicy ? String(existingPolicy) : undefined;

    if (existingPolicyValue !== 'new') {
      return false;
    }

    logger.warn('Existing consumer uses incompatible deliver policy for replay recovery', {
      consumerName: durableName,
      streamName,
      existingPolicy: existingPolicyValue,
      expectedPolicy: 'all',
    });
    return true;
  }

  private isRetryableTerminalEventError(error: unknown): boolean {
    if (!(error instanceof Error)) {
      return false;
    }

    if (error.name !== 'RetryableTerminalEventError') {
      return false;
    }

    const reason = Reflect.get(error, 'reason');
    return reason === 'lock-contention' || reason === 'recent-cache-miss';
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

      const durableName = `discord-bot-${subject.replace(/\./g, '_')}`;
      const streamName = 'OPENNOTES';
      const deliverSubject = `_DELIVER.${durableName}`;

      this.consumerIterator = await this.bindOrCreateConsumer(
        js,
        streamName,
        durableName,
        subject,
        deliverSubject
      );

      logger.info('Subscribed to score update events with JetStream consumer group', {
        subject,
        consumerName: durableName,
        deliverPolicy: 'all',
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

  async subscribeToProgressUpdates(
    handler: (event: BulkScanProgressEvent) => Promise<void>
  ): Promise<void> {
    if (!this.nc) {
      throw new Error('NATS connection not established. Call connect() first.');
    }

    const subject = NATS_SUBJECTS.BULK_SCAN_PROGRESS;

    try {
      const js = this.nc.jetstream();

      const durableName = `discord-bot-${subject.replace(/\./g, '_')}`;
      const streamName = 'OPENNOTES';
      const deliverSubject = `_DELIVER.${durableName}`;

      const progressIterator = await this.bindOrCreateConsumer(
        js,
        streamName,
        durableName,
        subject,
        deliverSubject
      );

      logger.info('Subscribed to bulk scan progress events', {
        subject,
        consumerName: durableName,
      });

      void (async (): Promise<void> => {
        logger.info('Starting message consumer loop for progress updates');

        for await (const msg of progressIterator) {
          try {
            const data = this.codec.decode(msg.data);
            const event = safeJSONParse<BulkScanProgressEvent>(data, {
              validate: (parsed) => {
                const isValid =
                  typeof parsed === 'object' &&
                  parsed !== null &&
                  'scan_id' in parsed &&
                  'community_server_id' in parsed &&
                  'message_scores' in parsed;

                if (!isValid) {
                  logger.warn('Invalid progress event structure', { parsed });
                }

                return isValid;
              },
            });

            logger.debug('Received bulk scan progress event', {
              scanId: event.scan_id,
              batchNumber: event.batch_number,
              scoresCount: event.message_scores?.length || 0,
            });

            await handler(event);
            msg.ack();
          } catch (error) {
            logger.error('Error processing progress event', {
              error: error instanceof Error ? error.message : String(error),
            });
            msg.nak();
          }
        }
      })();
    } catch (error) {
      logger.error('Failed to subscribe to progress updates', {
        error: error instanceof Error ? error.message : String(error),
        subject,
      });
      throw error;
    }
  }

  async subscribeToBulkScanTerminalUpdates(
    handler: (event: BulkScanProcessingFinishedEvent | BulkScanFailedEvent) => Promise<void>
  ): Promise<void> {
    if (!this.nc) {
      throw new Error('NATS connection not established. Call connect() first.');
    }

    const subjects = [
      NATS_SUBJECTS.BULK_SCAN_PROCESSING_FINISHED,
      NATS_SUBJECTS.BULK_SCAN_FAILED,
    ];

    try {
      const js = this.nc.jetstream();

      await Promise.all(subjects.map(async (subject) => {
        const durableName = `discord-bot-${subject.replace(/\./g, '_')}`;
        const deliverSubject = `_DELIVER.${durableName}`;
        const terminalIterator = await this.bindOrCreateConsumer(
          js,
          'OPENNOTES',
          durableName,
          subject,
          deliverSubject
        );

        logger.info('Subscribed to bulk scan terminal events', {
          subject,
          consumerName: durableName,
        });

        void (async (): Promise<void> => {
          for await (const msg of terminalIterator) {
            try {
              const data = this.codec.decode(msg.data);
              const event = safeJSONParse<BulkScanProcessingFinishedEvent | BulkScanFailedEvent>(data, {
                validate: (parsed) =>
                  typeof parsed === 'object' &&
                  parsed !== null &&
                  'scan_id' in parsed &&
                  'community_server_id' in parsed &&
                  'event_type' in parsed &&
                  (
                    parsed.event_type === EventType.BULK_SCAN_PROCESSING_FINISHED ||
                    parsed.event_type === EventType.BULK_SCAN_FAILED
                  ),
              });

              await handler(event);
              msg.ack();
            } catch (error) {
              logger.error('Error processing bulk scan terminal event', {
                error: error instanceof Error ? error.message : String(error),
                subject,
              });

              if (this.isRetryableTerminalEventError(error)) {
                msg.nak(this.retryableTerminalRedeliveryDelayMs);
                continue;
              }

              msg.nak();
            }
          }
        })();
      }));
    } catch (error) {
      logger.error('Failed to subscribe to bulk scan terminal events', {
        error: error instanceof Error ? error.message : String(error),
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
