import { ApiClient } from '../lib/api-client.js';
import { logger } from '../logger.js';
import {
  ServiceResult,
  ViewNotesInput,
  ViewNotesResult,
  ErrorCode,
  ServiceError,
} from './types.js';
import type { RateLimiterInterface } from './RateLimitFactory.js';
import { getErrorMessage, getErrorStack, hasMessage } from '../utils/error-handlers.js';

export class ViewNotesService {
  constructor(
    private apiClient: ApiClient,
    private rateLimiter: RateLimiterInterface
  ) {}

  async execute(input: ViewNotesInput, userId?: string): Promise<ServiceResult<ViewNotesResult>> {
    const validationError = this.validate(input);
    if (validationError) {
      return { success: false, error: validationError };
    }

    if (userId) {
      const rateLimit = await this.rateLimiter.check(userId);
      if (!rateLimit.allowed) {
        return {
          success: false,
          error: this.rateLimiter.createError(rateLimit.resetAt),
        };
      }
    }

    try {
      const notes = await this.apiClient.getNotes(input.messageId);

      logger.info('Notes viewed via service', {
        messageId: input.messageId,
        count: notes.data.length,
        userId,
      });

      return {
        success: true,
        data: { notes },
      };
    } catch (error: unknown) {
      logger.error('Failed to view notes in service', {
        errorMessage: getErrorMessage(error),
        errorStack: getErrorStack(error),
        messageId: input.messageId,
        userId,
      });

      return {
        success: false,
        error: this.mapError(error),
      };
    }
  }

  private validate(input: ViewNotesInput): ServiceError | null {
    if (!input.messageId || input.messageId.trim().length === 0) {
      return {
        code: ErrorCode.VALIDATION_ERROR,
        message: 'Message ID is required',
      };
    }

    return null;
  }

  private mapError(error: unknown): ServiceError {
    const message = hasMessage(error) ? error.message : '';

    if (message.includes('404')) {
      return {
        code: ErrorCode.NOT_FOUND,
        message: 'Message not found',
      };
    }

    return {
      code: ErrorCode.API_ERROR,
      message: 'Failed to retrieve notes. Please try again later.',
    };
  }
}
