import type { Message, Client } from 'discord.js';
import { logger } from '../logger.js';
import { MonitoredChannelService } from './MonitoredChannelService.js';
import { GuildOnboardingService } from './GuildOnboardingService.js';
import { apiClient } from '../api-client.js';
import { RedisQueue } from '../utils/redis-queue.js';
import { NotificationRateLimiter } from '../utils/notification-rate-limiter.js';
import { ApiError } from '../lib/errors.js';
import type { MonitoredChannelResponse, SimilaritySearchResponse } from '../lib/api-client.js';
import { CONTENT_LIMITS } from '../lib/constants.js';
import type Redis from 'ioredis';

export interface MessageContent {
  messageId: string;
  channelId: string;
  guildId: string;
  authorId: string;
  content: string;
  timestamp: number;
  channelConfig: MonitoredChannelResponse;
}

export interface MessageWithMatches extends MessageContent {
  similarityMatches: SimilaritySearchResponse;
}

/**
 * Service for monitoring Discord messages and triggering similarity searches.
 *
 * Queue Management:
 * - Max queue size: 1000 messages
 * - Overflow strategy: Drop oldest messages (FIFO)
 * - Metrics tracking: Queue depth, overflow events
 *
 * For production at scale:
 * Consider migrating to external message queue:
 * - Redis Lists with LPUSH/RPOP for simple queue
 * - Redis Streams for reliable message delivery
 * - RabbitMQ or AWS SQS for enterprise-grade queuing
 *
 * Benefits of external queue:
 * - Persistence across bot restarts
 * - Distributed processing across multiple bot instances
 * - Better backpressure handling and retry logic
 * - Dead letter queues for failed messages
 */
export class MessageMonitorService {
  private monitoredChannelService: MonitoredChannelService;
  private redisQueue: RedisQueue<MessageContent>;
  private processingInterval?: NodeJS.Timeout;
  private isProcessing: boolean = false;
  private readonly maxQueueSize: number = 1000;
  private notificationRateLimiter: NotificationRateLimiter;

  // Batch processing configuration
  private readonly BATCH_SIZE: number = 10;
  private readonly MAX_CONCURRENT: number = 5;

  // Performance metrics
  private totalProcessed: number = 0;
  private totalBatches: number = 0;
  private maxQueueDepth: number = 0;
  private processingStartTime: number = Date.now();

  constructor(
    private client: Client,
    private guildOnboardingService: GuildOnboardingService,
    redis: Redis
  ) {
    this.monitoredChannelService = new MonitoredChannelService();
    this.notificationRateLimiter = new NotificationRateLimiter(redis);
    this.redisQueue = new RedisQueue<MessageContent>(redis, 'message-monitor', {
      maxSize: this.maxQueueSize,
      keyPrefix: 'opennotes',
    });
    logger.info('MessageMonitorService initialized with Redis backend');
  }

  initialize(): void {
    this.startProcessing();
    logger.info('MessageMonitorService initialized');
  }

  private startProcessing(): void {
    this.processingInterval = setInterval(() => {
      void this.processQueue();
    }, 1000);
  }

  async handleMessage(message: Message): Promise<void> {
    if (!this.shouldProcessMessage(message)) {
      return;
    }

    if (!message.guildId) {
      logger.debug('Ignoring DM message', { messageId: message.id });
      return;
    }

    try {
      const channelConfig = await this.monitoredChannelService.getChannelConfig(
        message.channelId,
        message.guildId
      );

      if (!channelConfig || !channelConfig.enabled) {
        return;
      }

      const content = this.extractMessageContent(message);

      if (!content || content.trim().length === 0) {
        logger.debug('Skipping message with no extractable content', {
          messageId: message.id,
          channelId: message.channelId,
        });
        return;
      }

      const messageContent: MessageContent = {
        messageId: message.id,
        channelId: message.channelId,
        guildId: message.guildId,
        authorId: message.author.id,
        content,
        timestamp: message.createdTimestamp,
        channelConfig,
      };

      void this.queueMessage(messageContent).catch((error: unknown) => {
        logger.error('Failed to queue message', {
          messageId: messageContent.messageId,
          error: error instanceof Error ? error.message : String(error),
        });
      });

      logger.info('Message queued for monitoring', {
        messageId: message.id,
        channelId: message.channelId,
        guildId: message.guildId,
        contentLength: content.length,
      });
    } catch (error) {
      logger.error('Failed to handle message for monitoring', {
        messageId: message.id,
        channelId: message.channelId,
        guildId: message.guildId,
        error: error instanceof Error ? error.message : String(error),
        stack: error instanceof Error ? error.stack : undefined,
      });
    }
  }

  private shouldProcessMessage(message: Message): boolean {
    if (message.author.bot) {
      return false;
    }

    if (message.system) {
      return false;
    }

    if (message.webhookId) {
      return false;
    }

    return true;
  }

  private extractMessageContent(message: Message): string {
    const parts: string[] = [];

    if (message.content && message.content.trim().length > 0) {
      parts.push(message.content.trim());
    }

    if (message.embeds && message.embeds.length > 0) {
      for (const embed of message.embeds) {
        if (embed.title) {
          parts.push(embed.title);
        }
        if (embed.description) {
          parts.push(embed.description);
        }
        if (embed.fields && embed.fields.length > 0) {
          for (const field of embed.fields) {
            if (field.name) {
              parts.push(field.name);
            }
            if (field.value) {
              parts.push(field.value);
            }
          }
        }
      }
    }

    return parts.join('\n').trim();
  }

  private async queueMessage(messageContent: MessageContent): Promise<void> {
    await this.redisQueue.enqueue(messageContent);

    const metrics = await this.redisQueue.getMetrics();
    if (metrics.currentSize > this.maxQueueDepth) {
      this.maxQueueDepth = metrics.currentSize;
    }

    logger.debug('Message added to Redis queue', {
      queueSize: metrics.currentSize,
      maxQueueSize: this.maxQueueSize,
      utilizationPercent: ((metrics.currentSize / this.maxQueueSize) * 100).toFixed(2),
      messageId: messageContent.messageId,
    });
  }

  private async processQueue(): Promise<void> {
    if (this.isProcessing) {
      return;
    }

    this.isProcessing = true;

    try {
      const currentQueueDepth = await this.redisQueue.size();

      if (currentQueueDepth === 0) {
        return;
      }

      if (currentQueueDepth > this.maxQueueDepth) {
        this.maxQueueDepth = currentQueueDepth;
      }

      const batchSize = Math.min(this.BATCH_SIZE, currentQueueDepth);
      const batch = await this.redisQueue.dequeueBatch(batchSize);

      if (batch.length === 0) {
        return;
      }

      this.totalBatches++;
      const batchStartTime = Date.now();

      logger.debug('Processing message batch', {
        batchSize: batch.length,
        queueDepth: currentQueueDepth,
        totalProcessed: this.totalProcessed,
      });

      const results = await this.processBatch(batch);

      const batchDuration = Date.now() - batchStartTime;
      const successCount = results.filter((r) => r.status === 'fulfilled').length;
      const failureCount = results.filter((r) => r.status === 'rejected').length;

      this.totalProcessed += batch.length;

      const remainingQueueDepth = await this.redisQueue.size();

      logger.info('Batch processing completed', {
        batchSize: batch.length,
        successCount,
        failureCount,
        durationMs: batchDuration,
        remainingQueueDepth,
        totalProcessed: this.totalProcessed,
      });
    } catch (error) {
      logger.error('Failed to process message batch', {
        error: error instanceof Error ? error.message : String(error),
        stack: error instanceof Error ? error.stack : undefined,
      });
    } finally {
      this.isProcessing = false;
    }
  }

  private async processBatch(batch: MessageContent[]): Promise<PromiseSettledResult<void>[]> {
    const chunks: MessageContent[][] = [];
    for (let i = 0; i < batch.length; i += this.MAX_CONCURRENT) {
      chunks.push(batch.slice(i, i + this.MAX_CONCURRENT));
    }

    const allResults: PromiseSettledResult<void>[] = [];

    for (const chunk of chunks) {
      const chunkResults = await Promise.allSettled(
        chunk.map((messageContent) => this.processMessage(messageContent))
      );
      allResults.push(...chunkResults);
    }

    return allResults;
  }

  private async createNoteRequestForMatch(
    messageContent: MessageContent,
    similarityMatches: SimilaritySearchResponse
  ): Promise<void> {
    try {
      const topMatch = similarityMatches.matches[0];

      const noteRequestContext = [
        `**Fact-Check Match Found** (Confidence: ${(topMatch.similarity_score * 100).toFixed(1)}%)`,
        '',
        `**Source:** ${topMatch.dataset_name.toUpperCase()} - ${topMatch.rating || 'Unknown'}`,
        `**Title:** ${topMatch.title}`,
        '',
        `**Summary:** ${topMatch.summary || topMatch.content.substring(0, CONTENT_LIMITS.MAX_NOTE_EXCERPT_LENGTH) + '...'}`,
        '',
        `**Source URL:** ${topMatch.source_url || 'N/A'}`,
        '',
        `**Matched Message:**`,
        `> ${messageContent.content.substring(0, CONTENT_LIMITS.MAX_DESCRIPTION_PREVIEW_LENGTH)}${messageContent.content.length > CONTENT_LIMITS.MAX_DESCRIPTION_PREVIEW_LENGTH ? '...' : ''}`,
        '',
        `**Match Metadata:**`,
        `- Dataset Item ID: ${topMatch.id}`,
        `- Similarity Score: ${topMatch.similarity_score.toFixed(4)}`,
        `- Dataset Tags: ${topMatch.dataset_tags.join(', ')}`,
      ].join('\n');

      await apiClient.requestNote({
        messageId: messageContent.messageId,
        userId: 'system-factcheck',
        community_server_id: messageContent.guildId, // Required: Discord guild/server ID
        originalMessageContent: noteRequestContext,
        discord_channel_id: messageContent.channelId,
        discord_author_id: messageContent.authorId,
        discord_timestamp: new Date(messageContent.timestamp),
        fact_check_metadata: {
          dataset_item_id: topMatch.id,
          similarity_score: topMatch.similarity_score,
          dataset_name: topMatch.dataset_name,
          rating: topMatch.rating ?? undefined,
        },
      });

      logger.info('Note request created for similarity match', {
        messageId: messageContent.messageId,
        channelId: messageContent.channelId,
        guildId: messageContent.guildId,
        datasetItemId: topMatch.id,
        similarityScore: topMatch.similarity_score,
        datasetName: topMatch.dataset_name,
        rating: topMatch.rating,
      });
    } catch (error) {
      logger.error('Failed to create note request for similarity match', {
        messageId: messageContent.messageId,
        channelId: messageContent.channelId,
        guildId: messageContent.guildId,
        error: error instanceof Error ? error.message : String(error),
        stack: error instanceof Error ? error.stack : undefined,
      });
    }
  }

  private async processMessage(messageContent: MessageContent): Promise<void> {
    try {
      logger.debug('Processing message for similarity search', {
        messageId: messageContent.messageId,
        channelId: messageContent.channelId,
        guildId: messageContent.guildId,
      });

      // Check for previously seen messages first
      try {
        const previouslySeenResult = await apiClient.checkPreviouslySeen(
          messageContent.content,
          messageContent.guildId,
          messageContent.channelId
        );

        // Handle auto-publish (high similarity >= 0.9)
        if (previouslySeenResult.shouldAutoPublish && previouslySeenResult.topMatch) {
          logger.info('Auto-publishing previously seen note', {
            messageId: messageContent.messageId,
            channelId: messageContent.channelId,
            guildId: messageContent.guildId,
            similarity: previouslySeenResult.topMatch.similarity_score,
            publishedNoteId: previouslySeenResult.topMatch.published_note_id,
            threshold: previouslySeenResult.autopublishThreshold,
          });

          await this.autoPublishPreviousNote(messageContent, previouslySeenResult);
          return; // Skip normal processing
        }

        // Handle auto-request (moderate similarity 0.75-0.89)
        if (previouslySeenResult.shouldAutoRequest && previouslySeenResult.topMatch) {
          logger.info('Auto-requesting note due to similarity with previously seen message', {
            messageId: messageContent.messageId,
            channelId: messageContent.channelId,
            guildId: messageContent.guildId,
            similarity: previouslySeenResult.topMatch.similarity_score,
            threshold: previouslySeenResult.autorequestThreshold,
          });

          await this.createAutoRequestForSimilarContent(messageContent, previouslySeenResult);
          return; // Skip normal processing
        }

        logger.debug('No previously seen matches above thresholds', {
          messageId: messageContent.messageId,
          autopublishThreshold: previouslySeenResult.autopublishThreshold,
          autorequestThreshold: previouslySeenResult.autorequestThreshold,
          matchCount: previouslySeenResult.matches.length,
        });
      } catch (error) {
        // Log error but continue with normal flow if previously-seen check fails
        logger.error('Failed to check previously seen messages, continuing with normal flow', {
          messageId: messageContent.messageId,
          channelId: messageContent.channelId,
          guildId: messageContent.guildId,
          error: error instanceof Error ? error.message : String(error),
          stack: error instanceof Error ? error.stack : undefined,
        });
      }

      // Normal fact-check similarity search
      const similarityMatches = await apiClient.similaritySearch(
        messageContent.content,
        messageContent.guildId,
        messageContent.channelConfig.dataset_tags,
        messageContent.channelConfig.similarity_threshold,
        5
      );

      if (similarityMatches.matches.length > 0) {
        logger.info('Found similarity matches for message', {
          messageId: messageContent.messageId,
          channelId: messageContent.channelId,
          guildId: messageContent.guildId,
          matchCount: similarityMatches.matches.length,
          topScore: similarityMatches.matches[0].similarity_score,
          topMatch: similarityMatches.matches[0].title,
        });

        await this.createNoteRequestForMatch(messageContent, similarityMatches);
      } else {
        logger.debug('No similarity matches found for message', {
          messageId: messageContent.messageId,
          channelId: messageContent.channelId,
        });
      }
    } catch (error) {
      if (this.isProviderNotConfiguredError(error)) {
        await this.handleMissingOpenAIConfig(messageContent.guildId);
      }

      logger.error('Failed to process message for similarity search', {
        messageId: messageContent.messageId,
        channelId: messageContent.channelId,
        guildId: messageContent.guildId,
        error: error instanceof Error ? error.message : String(error),
        stack: error instanceof Error ? error.stack : undefined,
      });
    }
  }

  private async autoPublishPreviousNote(
    messageContent: MessageContent,
    previouslySeenResult: import('../lib/api-client.js').PreviouslySeenCheckResponse
  ): Promise<void> {
    try {
      if (!previouslySeenResult.topMatch) {
        return;
      }

      const topMatch = previouslySeenResult.topMatch;
      const publishedNoteId = topMatch.published_note_id;

      if (!publishedNoteId) {
        logger.warn('No published note ID in previously seen match', {
          messageId: messageContent.messageId,
          previouslySeenId: topMatch.id,
        });
        return;
      }

      const note = await apiClient.getNote(publishedNoteId.toString());

      const channel = this.client.channels.cache.get(messageContent.channelId);
      if (!channel || !('send' in channel)) {
        logger.warn('Channel not found or not a text channel for auto-publish', {
          channelId: messageContent.channelId,
        });
        return;
      }

      const replyContent = [
        `🔁 **Previously Published Note** (${(topMatch.similarity_score * 100).toFixed(1)}% match)`,
        '',
        note.summary || 'No content available',
        '',
        `*This note was automatically republished because it closely matches a previously seen message.*`,
      ].join('\n');

      await channel.send({
        content: replyContent,
        reply: {
          messageReference: messageContent.messageId,
          failIfNotExists: false,
        },
      });

      logger.info('Successfully auto-published previously seen note', {
        messageId: messageContent.messageId,
        publishedNoteId,
        similarity: topMatch.similarity_score,
      });
    } catch (error) {
      logger.error('Failed to auto-publish previously seen note', {
        messageId: messageContent.messageId,
        error: error instanceof Error ? error.message : String(error),
        stack: error instanceof Error ? error.stack : undefined,
      });
    }
  }

  private async createAutoRequestForSimilarContent(
    messageContent: MessageContent,
    previouslySeenResult: import('../lib/api-client.js').PreviouslySeenCheckResponse
  ): Promise<void> {
    try {
      const topMatch = previouslySeenResult.topMatch;
      if (!topMatch) {
        return;
      }

      const noteRequestContext = [
        `**Similar Previously Seen Message** (Similarity: ${(topMatch.similarity_score * 100).toFixed(1)}%)`,
        '',
        `**Original Message ID:** ${topMatch.original_message_id}`,
        `**Community Server:** ${topMatch.community_server_id}`,
        '',
        `**Current Message:**`,
        `> ${messageContent.content.substring(0, CONTENT_LIMITS.MAX_DESCRIPTION_PREVIEW_LENGTH)}${messageContent.content.length > CONTENT_LIMITS.MAX_DESCRIPTION_PREVIEW_LENGTH ? '...' : ''}`,
        '',
        `**Match Metadata:**`,
        `- Previously Seen ID: ${topMatch.id}`,
        `- Similarity Score: ${topMatch.similarity_score.toFixed(4)}`,
        `- Auto-Request Threshold: ${previouslySeenResult.autorequestThreshold}`,
      ].join('\n');

      await apiClient.requestNote({
        messageId: messageContent.messageId,
        userId: 'system-previously-seen',
        community_server_id: messageContent.guildId,
        originalMessageContent: noteRequestContext,
        discord_channel_id: messageContent.channelId,
        discord_author_id: messageContent.authorId,
        discord_timestamp: new Date(messageContent.timestamp),
      });

      logger.info('Note request created for similar previously seen content', {
        messageId: messageContent.messageId,
        channelId: messageContent.channelId,
        guildId: messageContent.guildId,
        previouslySeenId: topMatch.id,
        similarityScore: topMatch.similarity_score,
      });
    } catch (error) {
      logger.error('Failed to create note request for similar content', {
        messageId: messageContent.messageId,
        channelId: messageContent.channelId,
        guildId: messageContent.guildId,
        error: error instanceof Error ? error.message : String(error),
        stack: error instanceof Error ? error.stack : undefined,
      });
    }
  }

  private isProviderNotConfiguredError(error: unknown): boolean {
    if (error instanceof ApiError) {
      const detail = error.detail?.toLowerCase() || '';
      return detail.includes('provider not configured') || detail.includes('provider') && detail.includes('disabled');
    }
    return false;
  }

  private async handleMissingOpenAIConfig(guildId: string): Promise<void> {
    try {
      const shouldNotify = await this.notificationRateLimiter.shouldNotify(guildId, 'missing-openai-config');

      if (!shouldNotify) {
        logger.debug('Skipping OpenAI config notification due to rate limit', {
          guildId,
        });
        return;
      }

      const guild = this.client.guilds.cache.get(guildId);

      if (!guild) {
        logger.warn('Could not find guild to notify about missing OpenAI config', {
          guildId,
        });
        return;
      }

      await this.guildOnboardingService.checkAndNotifyMissingOpenAIKey(guild);
      await this.notificationRateLimiter.markNotified(guildId, 'missing-openai-config');

      logger.info('Successfully notified guild owner about missing OpenAI configuration', {
        guildId,
        guildName: guild.name,
      });
    } catch (error) {
      logger.error('Failed to notify guild owner about missing OpenAI configuration', {
        guildId,
        error: error instanceof Error ? error.message : String(error),
        stack: error instanceof Error ? error.stack : undefined,
      });
    }
  }

  async getQueueSize(): Promise<number> {
    return await this.redisQueue.size();
  }

  async getNextMessage(): Promise<MessageContent | null> {
    return await this.redisQueue.dequeue(0);
  }

  async getMetrics(): Promise<{
    queueSize: number;
    maxQueueSize: number;
    utilizationPercent: number;
    overflowCount: number;
    backend: 'redis';
    performance: {
      totalProcessed: number;
      totalBatches: number;
      maxQueueDepth: number;
      averageBatchSize: number;
      processingRate: number;
      uptimeSeconds: number;
    };
  }> {
    const uptimeSeconds = (Date.now() - this.processingStartTime) / 1000;
    const processingRate = uptimeSeconds > 0 ? this.totalProcessed / uptimeSeconds : 0;
    const averageBatchSize = this.totalBatches > 0 ? this.totalProcessed / this.totalBatches : 0;

    const redisMetrics = await this.redisQueue.getMetrics();
    const queueSize = redisMetrics.currentSize;
    const overflowCount = redisMetrics.overflows;

    return {
      queueSize,
      maxQueueSize: this.maxQueueSize,
      utilizationPercent: (queueSize / this.maxQueueSize) * 100,
      overflowCount,
      backend: 'redis',
      performance: {
        totalProcessed: this.totalProcessed,
        totalBatches: this.totalBatches,
        maxQueueDepth: this.maxQueueDepth,
        averageBatchSize: parseFloat(averageBatchSize.toFixed(2)),
        processingRate: parseFloat(processingRate.toFixed(2)),
        uptimeSeconds: parseFloat(uptimeSeconds.toFixed(2)),
      },
    };
  }

  async shutdown(): Promise<void> {
    if (this.processingInterval) {
      clearInterval(this.processingInterval);
      this.processingInterval = undefined;
    }

    const metrics = await this.getMetrics();
    logger.info('MessageMonitorService shutdown', {
      remainingQueueSize: metrics.queueSize,
      maxQueueSize: metrics.maxQueueSize,
      totalOverflows: metrics.overflowCount,
      backend: metrics.backend,
    });
  }
}
