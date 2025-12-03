import { logger } from '../logger.js';

export interface RateLimitConfig {
  cooldownMs: number;
  cleanupIntervalMs?: number;
}

export class InteractionRateLimiter {
  private readonly userTimestamps = new Map<string, number>();
  private readonly cooldownMs: number;
  private cleanupInterval?: NodeJS.Timeout;

  constructor(config: RateLimitConfig) {
    this.cooldownMs = config.cooldownMs;

    if (config.cleanupIntervalMs) {
      this.cleanupInterval = setInterval(() => {
        this.cleanup();
      }, config.cleanupIntervalMs);
    }
  }

  isRateLimited(userId: string): boolean {
    const lastInteraction = this.userTimestamps.get(userId);
    if (!lastInteraction) {
      return false;
    }

    const now = Date.now();
    const timeSinceLastInteraction = now - lastInteraction;

    return timeSinceLastInteraction < this.cooldownMs;
  }

  recordInteraction(userId: string): void {
    this.userTimestamps.set(userId, Date.now());
  }

  checkAndRecord(userId: string): boolean {
    if (this.isRateLimited(userId)) {
      logger.warn('User rate limited on interaction', {
        userId,
        cooldownMs: this.cooldownMs,
      });
      return true;
    }

    this.recordInteraction(userId);
    return false;
  }

  private cleanup(): void {
    const now = Date.now();
    const expiredUsers: string[] = [];

    for (const [userId, timestamp] of this.userTimestamps.entries()) {
      if (now - timestamp > this.cooldownMs * 2) {
        expiredUsers.push(userId);
      }
    }

    for (const userId of expiredUsers) {
      this.userTimestamps.delete(userId);
    }

    if (expiredUsers.length > 0) {
      logger.debug('Cleaned up expired rate limit entries', {
        count: expiredUsers.length,
      });
    }
  }

  destroy(): void {
    if (this.cleanupInterval) {
      clearInterval(this.cleanupInterval);
      this.cleanupInterval = undefined;
    }
    this.userTimestamps.clear();
  }
}

export const buttonInteractionRateLimiter = new InteractionRateLimiter({
  cooldownMs: 1500,
  cleanupIntervalMs: 60000,
});

export const modalSubmissionRateLimiter = new InteractionRateLimiter({
  cooldownMs: 2000,
  cleanupIntervalMs: 60000,
});
