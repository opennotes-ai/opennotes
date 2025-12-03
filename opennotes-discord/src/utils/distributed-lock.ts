import { randomBytes } from 'crypto';
import Redis from 'ioredis';
import { logger } from '../logger.js';

export interface DistributedLockOptions {
  ttlMs?: number;
  retryDelayMs?: number;
  maxRetries?: number;
}

export interface LockMetrics {
  acquisitions: number;
  releases: number;
  timeouts: number;
  contentions: number;
  averageAcquisitionTimeMs: number;
  averageHoldTimeMs: number;
}

export class DistributedLock {
  private readonly redis: Redis;
  private readonly lockKeyPrefix: string = 'lock:';
  private readonly defaultTtlMs: number = 5000;
  private readonly defaultRetryDelayMs: number = 50;
  private readonly defaultMaxRetries: number = 10;
  private readonly locks: Map<string, { acquiredAt: number; lockValue: string }> = new Map();

  private metrics: {
    acquisitions: number;
    releases: number;
    timeouts: number;
    contentions: number;
    totalAcquisitionTimeMs: number;
    totalHoldTimeMs: number;
  } = {
    acquisitions: 0,
    releases: 0,
    timeouts: 0,
    contentions: 0,
    totalAcquisitionTimeMs: 0,
    totalHoldTimeMs: 0,
  };

  constructor(redis: Redis) {
    this.redis = redis;
  }

  async acquire(
    lockKey: string,
    options: DistributedLockOptions = {}
  ): Promise<boolean> {
    const ttlMs = options.ttlMs ?? this.defaultTtlMs;
    const retryDelayMs = options.retryDelayMs ?? this.defaultRetryDelayMs;
    const maxRetries = options.maxRetries ?? this.defaultMaxRetries;

    const fullLockKey = this.buildLockKey(lockKey);
    const lockValue = this.generateLockValue();
    const startTime = Date.now();

    let attempts = 0;
    let acquired = false;

    while (attempts <= maxRetries && !acquired) {
      try {
        const result = await this.redis.set(
          fullLockKey,
          lockValue,
          'PX',
          ttlMs,
          'NX'
        );

        if (result === 'OK') {
          acquired = true;
          const acquisitionTime = Date.now() - startTime;

          this.locks.set(lockKey, {
            acquiredAt: Date.now(),
            lockValue,
          });

          this.metrics.acquisitions++;
          this.metrics.totalAcquisitionTimeMs += acquisitionTime;

          logger.debug('Distributed lock acquired', {
            lockKey,
            ttlMs,
            attempts: attempts + 1,
            acquisitionTimeMs: acquisitionTime,
          });

          return true;
        }

        this.metrics.contentions++;

        if (attempts < maxRetries) {
          await this.sleep(retryDelayMs);
        }

        attempts++;
      } catch (error) {
        logger.error('Failed to acquire distributed lock', {
          lockKey,
          attempts: attempts + 1,
          error: error instanceof Error ? error.message : String(error),
        });
        throw error;
      }
    }

    this.metrics.timeouts++;
    const totalTime = Date.now() - startTime;

    logger.warn('Failed to acquire distributed lock after retries', {
      lockKey,
      maxRetries,
      totalTimeMs: totalTime,
    });

    return false;
  }

  async release(lockKey: string): Promise<boolean> {
    const fullLockKey = this.buildLockKey(lockKey);
    const lockInfo = this.locks.get(lockKey);

    if (!lockInfo) {
      logger.warn('Attempted to release lock that was not acquired by this instance', {
        lockKey,
      });
      return false;
    }

    const { acquiredAt, lockValue } = lockInfo;

    try {
      const luaScript = `
        if redis.call("get", KEYS[1]) == ARGV[1] then
          return redis.call("del", KEYS[1])
        else
          return 0
        end
      `;

      const result = await this.redis.eval(luaScript, 1, fullLockKey, lockValue);

      if (result === 1) {
        const holdTime = Date.now() - acquiredAt;
        this.locks.delete(lockKey);

        this.metrics.releases++;
        this.metrics.totalHoldTimeMs += holdTime;

        logger.debug('Distributed lock released', {
          lockKey,
          holdTimeMs: holdTime,
        });

        return true;
      }

      logger.warn('Failed to release lock: lock value mismatch or already expired', {
        lockKey,
      });
      this.locks.delete(lockKey);
      return false;
    } catch (error) {
      logger.error('Failed to release distributed lock', {
        lockKey,
        error: error instanceof Error ? error.message : String(error),
      });
      this.locks.delete(lockKey);
      return false;
    }
  }

  async extend(lockKey: string, ttlMs: number): Promise<boolean> {
    const fullLockKey = this.buildLockKey(lockKey);
    const lockInfo = this.locks.get(lockKey);

    if (!lockInfo) {
      logger.warn('Attempted to extend lock that was not acquired by this instance', {
        lockKey,
      });
      return false;
    }

    const { lockValue } = lockInfo;

    try {
      const luaScript = `
        if redis.call("get", KEYS[1]) == ARGV[1] then
          return redis.call("pexpire", KEYS[1], ARGV[2])
        else
          return 0
        end
      `;

      const result = await this.redis.eval(
        luaScript,
        1,
        fullLockKey,
        lockValue,
        ttlMs.toString()
      );

      if (result === 1) {
        logger.debug('Distributed lock extended', {
          lockKey,
          ttlMs,
        });
        return true;
      }

      logger.warn('Failed to extend lock: lock value mismatch or already expired', {
        lockKey,
      });
      this.locks.delete(lockKey);
      return false;
    } catch (error) {
      logger.error('Failed to extend distributed lock', {
        lockKey,
        error: error instanceof Error ? error.message : String(error),
      });
      return false;
    }
  }

  async withLock<T>(
    lockKey: string,
    fn: () => Promise<T>,
    options: DistributedLockOptions = {}
  ): Promise<T | null> {
    const acquired = await this.acquire(lockKey, options);

    if (!acquired) {
      logger.warn('Failed to acquire lock, skipping operation', { lockKey });
      return null;
    }

    try {
      return await fn();
    } finally {
      await this.release(lockKey);
    }
  }

  getMetrics(): LockMetrics {
    const averageAcquisitionTimeMs =
      this.metrics.acquisitions > 0
        ? this.metrics.totalAcquisitionTimeMs / this.metrics.acquisitions
        : 0;

    const averageHoldTimeMs =
      this.metrics.releases > 0
        ? this.metrics.totalHoldTimeMs / this.metrics.releases
        : 0;

    return {
      acquisitions: this.metrics.acquisitions,
      releases: this.metrics.releases,
      timeouts: this.metrics.timeouts,
      contentions: this.metrics.contentions,
      averageAcquisitionTimeMs: parseFloat(averageAcquisitionTimeMs.toFixed(2)),
      averageHoldTimeMs: parseFloat(averageHoldTimeMs.toFixed(2)),
    };
  }

  private buildLockKey(key: string): string {
    return `${this.lockKeyPrefix}${key}`;
  }

  private generateLockValue(): string {
    return `${process.pid}-${Date.now()}-${randomBytes(16).toString('hex')}`;
  }

  private sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
}
