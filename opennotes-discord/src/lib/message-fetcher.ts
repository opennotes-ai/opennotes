import { Client, Message, TextChannel } from 'discord.js';
import { LRUCache } from 'lru-cache';
import { logger } from '../logger.js';
import { CONTENT_LIMITS } from './constants.js';

export interface MessageInfo {
  content: string;
  author: string;
  url: string;
}

export interface MessageFetcherCacheMetrics {
  hits: number;
  misses: number;
  size: number;
  maxSize: number;
  hitRate: number;
  searchPerformance: {
    totalSearches: number;
    limitReached: number;
    averageChannelsChecked: number;
  };
}

export class MessageFetcher {
  private cache: LRUCache<string, MessageInfo>;
  private notFoundCache: Set<string>;      // Track messages that don't exist
  private client: Client;
  private cacheHits = 0;
  private cacheMisses = 0;

  // Search performance metrics
  private totalSearches = 0;
  private totalChannelsChecked = 0;
  private searchLimitReached = 0;

  // Circuit breaker for repeated failures
  private failureCount = 0;
  private circuitBreakerOpen = false;
  private circuitBreakerResetTime = 0;
  private readonly FAILURE_THRESHOLD = 5;
  private readonly CIRCUIT_BREAKER_TIMEOUT = 60000; // 1 minute

  // Parallel fetching configuration
  private readonly BATCH_SIZE = 10;
  private readonly CHANNEL_TIMEOUT = 2000; // 2 seconds per channel

  constructor(client: Client, maxCacheSize: number = 1000, cacheTTL: number = 3600000) {
    this.client = client;
    this.notFoundCache = new Set();

    // Initialize LRU cache with bounds and TTL
    this.cache = new LRUCache<string, MessageInfo>({
      max: maxCacheSize,                    // Maximum 1000 entries by default
      ttl: cacheTTL,                        // 1 hour TTL by default (in milliseconds)
      updateAgeOnGet: true,                 // Reset TTL on cache hit
      allowStale: false,                    // Don't return stale entries
    });

    logger.debug('MessageFetcher initialized', {
      maxCacheSize,
      cacheTTLMinutes: cacheTTL / 60000,
      batchSize: this.BATCH_SIZE,
      channelTimeout: this.CHANNEL_TIMEOUT,
    });
  }

  async fetchMessage(messageId: string, channelId?: string): Promise<MessageInfo | null> {
    // Check if we've already determined this message doesn't exist
    if (this.notFoundCache.has(messageId)) {
      this.cacheHits++;
      logger.debug('MessageFetcher not-found cache hit', { messageId });
      return null;
    }

    // Check cache for found messages
    const cached = this.cache.get(messageId);
    if (cached !== undefined) {
      this.cacheHits++;
      logger.debug('MessageFetcher cache hit', { messageId, cacheSize: this.cache.size });
      return cached;
    }

    this.cacheMisses++;
    logger.debug('MessageFetcher cache miss', { messageId, cacheSize: this.cache.size });

    try {
      let message: Message | undefined;

      // If channelId provided, try that channel first
      if (channelId) {
        const channel = await this.client.channels.fetch(channelId);
        if (channel?.isTextBased()) {
          try {
            message = await (channel as TextChannel).messages.fetch(messageId);
          } catch {
            // Channel exists but message not found, continue to search
          }
        }
      }

      // If not found yet, search all accessible channels
      if (!message) {
        message = await this.searchAllChannels(messageId);
      }

      if (message) {
        const info: MessageInfo = {
          content: message.content.substring(0, CONTENT_LIMITS.MAX_NOTE_EXCERPT_LENGTH) + (message.content.length > CONTENT_LIMITS.MAX_NOTE_EXCERPT_LENGTH ? '...' : ''),
          author: message.author.username,
          url: message.url,
        };
        this.cache.set(messageId, info);
        return info;
      }

      // Message not found - add to not-found cache
      this.notFoundCache.add(messageId);
      return null;
    } catch (error) {
      logger.error('Error fetching message', { error, messageId, channelId });
      this.notFoundCache.add(messageId);
      return null;
    }
  }

  private checkCircuitBreaker(): boolean {
    if (!this.circuitBreakerOpen) {
      return true;
    }

    if (Date.now() >= this.circuitBreakerResetTime) {
      this.circuitBreakerOpen = false;
      this.failureCount = 0;
      logger.info('Circuit breaker reset');
      return true;
    }

    return false;
  }

  private recordFailure(): void {
    this.failureCount++;
    if (this.failureCount >= this.FAILURE_THRESHOLD) {
      this.circuitBreakerOpen = true;
      this.circuitBreakerResetTime = Date.now() + this.CIRCUIT_BREAKER_TIMEOUT;
      logger.warn('Circuit breaker opened due to repeated failures', {
        failureCount: this.failureCount,
        resetTime: new Date(this.circuitBreakerResetTime).toISOString(),
      });
    }
  }

  private async fetchMessageFromChannel(
    channel: TextChannel,
    messageId: string
  ): Promise<Message | null> {
    return new Promise((resolve) => {
      const timeout = setTimeout(() => {
        logger.debug('Channel fetch timeout', { channelId: channel.id, messageId });
        resolve(null);
      }, this.CHANNEL_TIMEOUT);

      channel.messages.fetch(messageId)
        .then((message) => {
          clearTimeout(timeout);
          resolve(message);
        })
        .catch(() => {
          clearTimeout(timeout);
          resolve(null);
        });
    });
  }

  private async searchAllChannels(messageId: string, maxChannels: number = 50): Promise<Message | undefined> {
    if (!this.checkCircuitBreaker()) {
      logger.warn('Circuit breaker open, skipping channel search', { messageId });
      return undefined;
    }

    this.totalSearches++;

    const allTextChannels = Array.from(this.client.channels.cache.values())
      .filter((channel): channel is TextChannel => channel.isTextBased());

    if (allTextChannels.length === 0) {
      return undefined;
    }

    if (allTextChannels.length > maxChannels) {
      this.searchLimitReached++;
      logger.warn('Channel search limit reached', {
        messageId,
        maxChannels,
        totalCachedChannels: allTextChannels.length,
      });
    }

    const textChannels = allTextChannels.slice(0, maxChannels);

    let checked = 0;
    let foundMessage: Message | undefined;

    for (let i = 0; i < textChannels.length; i += this.BATCH_SIZE) {
      if (foundMessage) {
        break;
      }

      const batch = textChannels.slice(i, i + this.BATCH_SIZE);
      const startTime = Date.now();

      const results = await Promise.allSettled(
        batch.map((channel) => this.fetchMessageFromChannel(channel, messageId))
      );

      const batchDuration = Date.now() - startTime;
      checked += batch.length;

      for (const result of results) {
        if (result.status === 'fulfilled' && result.value) {
          foundMessage = result.value;
          this.failureCount = 0;
          break;
        }
      }

      logger.debug('Batch search completed', {
        messageId,
        batchSize: batch.length,
        durationMs: batchDuration,
        found: !!foundMessage,
      });
    }

    this.totalChannelsChecked += checked;

    if (foundMessage) {
      logger.debug('Message found in parallel channel search', {
        messageId,
        channelsChecked: checked,
      });
      return foundMessage;
    }

    if (checked > 0) {
      this.recordFailure();
      logger.debug('Parallel channel search completed without finding message', {
        messageId,
        channelsChecked: checked,
      });
    }

    return undefined;
  }

  clearCache(): void {
    this.cache.clear();
    this.notFoundCache.clear();
    this.cacheHits = 0;
    this.cacheMisses = 0;
    this.totalSearches = 0;
    this.totalChannelsChecked = 0;
    this.searchLimitReached = 0;
    this.failureCount = 0;
    this.circuitBreakerOpen = false;
    this.circuitBreakerResetTime = 0;
    logger.debug('MessageFetcher cache and circuit breaker cleared');
  }

  getCacheSize(): number {
    return this.cache.size;
  }

  getCacheMetrics(): MessageFetcherCacheMetrics {
    const totalRequests = this.cacheHits + this.cacheMisses;
    const hitRate = totalRequests > 0 ? this.cacheHits / totalRequests : 0;
    const averageChannelsChecked = this.totalSearches > 0
      ? this.totalChannelsChecked / this.totalSearches
      : 0;

    return {
      hits: this.cacheHits,
      misses: this.cacheMisses,
      size: this.cache.size,
      maxSize: this.cache.max,
      hitRate: parseFloat(hitRate.toFixed(4)),
      searchPerformance: {
        totalSearches: this.totalSearches,
        limitReached: this.searchLimitReached,
        averageChannelsChecked: parseFloat(averageChannelsChecked.toFixed(2)),
      },
    };
  }
}
