import type Redis from 'ioredis';
import { logger } from '../logger.js';
import { safeJSONStringify, safeJSONParse } from './safe-json.js';

export interface RedisQueueOptions {
  maxSize?: number;
  keyPrefix?: string;
}

export interface QueueMetrics {
  enqueued: number;
  dequeued: number;
  errors: number;
  currentSize: number;
  overflows: number;
}

export class RedisQueue<T> {
  private readonly redis: Redis;
  private readonly queueKey: string;
  private readonly maxSize: number;
  private metrics: {
    enqueued: number;
    dequeued: number;
    errors: number;
    overflows: number;
  };

  constructor(
    redis: Redis,
    queueName: string,
    options: RedisQueueOptions = {}
  ) {
    this.redis = redis;
    this.maxSize = options.maxSize ?? 10000;
    const keyPrefix = options.keyPrefix ?? 'queue';
    this.queueKey = `${keyPrefix}:${queueName}`;

    this.metrics = {
      enqueued: 0,
      dequeued: 0,
      errors: 0,
      overflows: 0,
    };
  }

  async enqueue(item: T): Promise<boolean> {
    try {
      const currentSize = await this.size();

      if (currentSize >= this.maxSize) {
        logger.warn('Redis queue at max capacity, dropping oldest item', {
          queueKey: this.queueKey,
          currentSize,
          maxSize: this.maxSize,
        });

        await this.redis.rpop(this.queueKey);
        this.metrics.overflows++;
      }

      const serialized = safeJSONStringify(item);
      await this.redis.lpush(this.queueKey, serialized);

      this.metrics.enqueued++;

      logger.debug('Item enqueued to Redis queue', {
        queueKey: this.queueKey,
        queueSize: await this.size(),
      });

      return true;
    } catch (error) {
      this.metrics.errors++;
      logger.error('Failed to enqueue item to Redis queue', {
        queueKey: this.queueKey,
        error: error instanceof Error ? error.message : String(error),
      });
      return false;
    }
  }

  async dequeue(timeoutSeconds: number = 1): Promise<T | null> {
    try {
      const result = await this.redis.brpop(this.queueKey, timeoutSeconds);

      if (!result) {
        return null;
      }

      const [, value] = result;
      const item = safeJSONParse<T>(value);

      this.metrics.dequeued++;

      logger.debug('Item dequeued from Redis queue', {
        queueKey: this.queueKey,
        queueSize: await this.size(),
      });

      return item;
    } catch (error) {
      this.metrics.errors++;
      logger.error('Failed to dequeue item from Redis queue', {
        queueKey: this.queueKey,
        error: error instanceof Error ? error.message : String(error),
      });
      return null;
    }
  }

  async dequeueBatch(batchSize: number): Promise<T[]> {
    const items: T[] = [];

    try {
      const pipeline = this.redis.pipeline();

      for (let i = 0; i < batchSize; i++) {
        pipeline.rpop(this.queueKey);
      }

      const results = await pipeline.exec();

      if (!results) {
        return items;
      }

      for (const [error, value] of results) {
        if (error || value === null) {
          continue;
        }

        try {
          const item = safeJSONParse<T>(value as string);
          items.push(item);
          this.metrics.dequeued++;
        } catch (parseError) {
          logger.error('Failed to parse dequeued item', {
            queueKey: this.queueKey,
            error: parseError instanceof Error ? parseError.message : String(parseError),
          });
          this.metrics.errors++;
        }
      }

      logger.debug('Batch dequeued from Redis queue', {
        queueKey: this.queueKey,
        batchSize: items.length,
        queueSize: await this.size(),
      });

      return items;
    } catch (error) {
      this.metrics.errors++;
      logger.error('Failed to dequeue batch from Redis queue', {
        queueKey: this.queueKey,
        error: error instanceof Error ? error.message : String(error),
      });
      return items;
    }
  }

  async size(): Promise<number> {
    try {
      return await this.redis.llen(this.queueKey);
    } catch (error) {
      logger.error('Failed to get Redis queue size', {
        queueKey: this.queueKey,
        error: error instanceof Error ? error.message : String(error),
      });
      return 0;
    }
  }

  async clear(): Promise<number> {
    try {
      const size = await this.size();
      await this.redis.del(this.queueKey);

      logger.info('Redis queue cleared', {
        queueKey: this.queueKey,
        itemsCleared: size,
      });

      return size;
    } catch (error) {
      logger.error('Failed to clear Redis queue', {
        queueKey: this.queueKey,
        error: error instanceof Error ? error.message : String(error),
      });
      return 0;
    }
  }

  async peek(): Promise<T | null> {
    try {
      const value = await this.redis.lindex(this.queueKey, -1);

      if (!value) {
        return null;
      }

      return safeJSONParse<T>(value);
    } catch (error) {
      logger.error('Failed to peek Redis queue', {
        queueKey: this.queueKey,
        error: error instanceof Error ? error.message : String(error),
      });
      return null;
    }
  }

  async getMetrics(): Promise<QueueMetrics> {
    const currentSize = await this.size();

    return {
      enqueued: this.metrics.enqueued,
      dequeued: this.metrics.dequeued,
      errors: this.metrics.errors,
      currentSize,
      overflows: this.metrics.overflows,
    };
  }

  getQueueKey(): string {
    return this.queueKey;
  }
}
