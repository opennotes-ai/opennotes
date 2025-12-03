import type Redis from 'ioredis';
import { logger } from '../logger.js';

export class NotificationRateLimiter {
  private readonly RATE_LIMIT_DURATION_MS = 24 * 60 * 60 * 1000;

  constructor(private redis: Redis) {
    logger.info('NotificationRateLimiter initialized with Redis backend');
  }

  async shouldNotify(guildId: string, notificationType: string): Promise<boolean> {
    const key = this.getKey(guildId, notificationType);

    try {
      const lastNotified = await this.redis.get(key);

      if (!lastNotified) {
        return true;
      }

      const lastNotifiedTime = parseInt(lastNotified, 10);
      const timeSinceLastNotification = Date.now() - lastNotifiedTime;
      const shouldNotify = timeSinceLastNotification >= this.RATE_LIMIT_DURATION_MS;

      if (!shouldNotify) {
        const hoursRemaining = ((this.RATE_LIMIT_DURATION_MS - timeSinceLastNotification) / (1000 * 60 * 60)).toFixed(1);
        logger.debug('Notification rate limited', {
          key,
          timeSinceLastNotification,
          hoursRemaining,
        });
      }

      return shouldNotify;
    } catch (error) {
      logger.error('Failed to check notification rate limit in Redis', {
        key,
        error: error instanceof Error ? error.message : String(error),
      });

      return false;
    }
  }

  async markNotified(guildId: string, notificationType: string): Promise<void> {
    const key = this.getKey(guildId, notificationType);
    const timestamp = Date.now();

    try {
      const ttlSeconds = Math.floor(this.RATE_LIMIT_DURATION_MS / 1000);
      await this.redis.setex(key, ttlSeconds, timestamp.toString());

      logger.debug('Notification marked as sent', {
        guildId,
        notificationType,
        timestamp,
      });
    } catch (error) {
      logger.error('Failed to mark notification in Redis', {
        key,
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }

  private getKey(guildId: string, notificationType: string): string {
    return `opennotes:notification:${notificationType}:${guildId}`;
  }
}
