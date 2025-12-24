import { Factory } from 'fishery';
import { jest } from '@jest/globals';
import type { RateLimiterInterface } from '../../src/services/RateLimitFactory.js';
import type { RateLimitResult, ServiceError } from '../../src/services/types.js';
import { ErrorCode } from '../../src/services/types.js';

export interface MockRateLimiter extends RateLimiterInterface {
  check: jest.Mock<(userId: string) => Promise<RateLimitResult>>;
  reset: jest.Mock<(userId: string) => Promise<void>>;
  createError: jest.Mock<(resetAt: number) => ServiceError>;
  cleanup: jest.Mock<() => Promise<void>>;
}

export interface RateLimiterTransientParams {
  allowed?: boolean;
  remaining?: number;
  resetAt?: number;
  rateLimitWindowMs?: number;
}

export const rateLimiterFactory = Factory.define<MockRateLimiter, RateLimiterTransientParams>(
  ({ transientParams }) => {
    const {
      allowed = true,
      remaining = 5,
      resetAt,
      rateLimitWindowMs = 60000,
    } = transientParams;

    const defaultResetAt = resetAt ?? Date.now() + rateLimitWindowMs;

    return {
      check: jest.fn<(userId: string) => Promise<RateLimitResult>>().mockResolvedValue({
        allowed,
        remaining,
        resetAt: defaultResetAt,
      }),
      reset: jest.fn<(userId: string) => Promise<void>>().mockResolvedValue(undefined),
      createError: jest.fn<(resetAt: number) => ServiceError>().mockImplementation((resetTime: number) => ({
        code: ErrorCode.RATE_LIMIT_EXCEEDED,
        message: 'Rate limit exceeded. Please try again later.',
        details: { resetAt: resetTime },
      })),
      cleanup: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
    };
  }
);

export const rateLimitedFactory = rateLimiterFactory.transient({
  allowed: false,
  remaining: 0,
});

export const unlimitedRateLimiterFactory = rateLimiterFactory.transient({
  allowed: true,
  remaining: 999,
});
