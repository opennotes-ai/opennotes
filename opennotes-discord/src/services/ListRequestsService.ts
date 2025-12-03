import { ApiClient } from '../lib/api-client.js';
import { logger } from '../logger.js';
import {
  ServiceResult,
  ListRequestsInput,
  ListRequestsResult,
  ErrorCode,
  ServiceError,
} from './types.js';
import type { RateLimiterInterface } from './RateLimitFactory.js';
import { getErrorMessage, getErrorStack, hasMessage } from '../utils/error-handlers.js';

export class ListRequestsService {
  constructor(
    private apiClient: ApiClient,
    private rateLimiter: RateLimiterInterface
  ) {}

  async execute(input: ListRequestsInput): Promise<ServiceResult<ListRequestsResult>> {
    const validationError = this.validate(input);
    if (validationError) {
      return { success: false, error: validationError };
    }

    const rateLimit = await this.rateLimiter.check(input.userId);
    if (!rateLimit.allowed) {
      return {
        success: false,
        error: this.rateLimiter.createError(rateLimit.resetAt),
      };
    }

    try {
      const response = await this.apiClient.listRequests({
        page: input.page,
        size: input.size,
        status: input.status,
        requestedBy: input.myRequestsOnly ? input.userId : undefined,
        communityServerId: input.communityServerId,
      });

      logger.info('Requests listed via service', {
        userId: input.userId,
        page: input.page,
        size: input.size,
        status: input.status,
        myRequestsOnly: input.myRequestsOnly,
        communityServerId: input.communityServerId,
        total: response.total,
      });

      return {
        success: true,
        data: {
          requests: response.requests,
          total: response.total,
          page: response.page,
          size: response.size,
        },
      };
    } catch (error: unknown) {
      logger.error('Failed to list requests in service', {
        errorMessage: getErrorMessage(error),
        errorStack: getErrorStack(error),
        userId: input.userId,
        page: input.page,
        status: input.status,
      });

      return {
        success: false,
        error: this.mapError(error),
      };
    }
  }

  private validate(input: ListRequestsInput): ServiceError | null {
    if (!input.userId || input.userId.trim().length === 0) {
      return {
        code: ErrorCode.VALIDATION_ERROR,
        message: 'User ID is required',
      };
    }

    if (input.page !== undefined && input.page < 1) {
      return {
        code: ErrorCode.VALIDATION_ERROR,
        message: 'Page must be at least 1',
      };
    }

    if (input.size !== undefined && (input.size < 1 || input.size > 100)) {
      return {
        code: ErrorCode.VALIDATION_ERROR,
        message: 'Page size must be between 1 and 100',
      };
    }

    return null;
  }

  private mapError(error: unknown): ServiceError {
    const message = hasMessage(error) ? error.message : '';

    if (message.includes('401') || message.includes('403')) {
      return {
        code: ErrorCode.UNAUTHORIZED,
        message: 'Unauthorized to list requests',
      };
    }

    return {
      code: ErrorCode.API_ERROR,
      message: 'Failed to retrieve requests. Please try again later.',
    };
  }
}
