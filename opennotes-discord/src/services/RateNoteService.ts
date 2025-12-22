import { ApiClient, UserContext, RatingJSONAPIResponse } from '../lib/api-client.js';
import { logger } from '../logger.js';
import {
  ServiceResult,
  RateNoteInput,
  RateNoteResult,
  ErrorCode,
  ServiceError,
} from './types.js';
import type { RateLimiterInterface } from './RateLimitFactory.js';
import { getErrorMessage, getErrorStack, isApiError } from '../utils/error-handlers.js';

export class RateNoteService {
  constructor(
    private apiClient: ApiClient,
    private rateLimiter: RateLimiterInterface
  ) {}

  async execute(input: RateNoteInput): Promise<ServiceResult<RateNoteResult>> {
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
      const userContext: UserContext = {
        userId: input.userId,
        username: input.username,
        displayName: input.displayName,
        avatarUrl: input.avatarUrl,
        guildId: input.guildId,
      };

      // First, check if the user already has a rating for this note
      const existingRatingsResponse = await this.apiClient.getRatingsForNote(input.noteId);
      const existingRating = existingRatingsResponse.data.find(
        r => r.attributes.rater_participant_id === input.userId
      );

      let rating: RatingJSONAPIResponse;
      if (existingRating) {
        // Update existing rating
        rating = await this.apiClient.updateRating(existingRating.id, input.helpful, userContext);
        logger.info('Note rating updated via service', {
          noteId: input.noteId,
          userId: input.userId,
          ratingId: existingRating.id,
          helpful: input.helpful,
        });
      } else {
        // Create new rating
        rating = await this.apiClient.rateNote({
          noteId: input.noteId,
          userId: input.userId,
          helpful: input.helpful,
        }, userContext);
        logger.info('Note rated via service', {
          noteId: input.noteId,
          userId: input.userId,
          helpful: input.helpful,
        });
      }

      return {
        success: true,
        data: { rating },
      };
    } catch (error: unknown) {
      logger.error('Failed to rate note in service', {
        errorMessage: getErrorMessage(error),
        errorStack: getErrorStack(error),
        userId: input.userId,
        noteId: input.noteId,
      });

      return {
        success: false,
        error: this.mapError(error),
      };
    }
  }

  private validate(input: RateNoteInput): ServiceError | null {
    if (!input.noteId || input.noteId.trim().length === 0) {
      return {
        code: ErrorCode.VALIDATION_ERROR,
        message: 'Note ID is required',
      };
    }

    if (!input.userId || input.userId.trim().length === 0) {
      return {
        code: ErrorCode.VALIDATION_ERROR,
        message: 'User ID is required',
      };
    }

    if (typeof input.helpful !== 'boolean') {
      return {
        code: ErrorCode.VALIDATION_ERROR,
        message: 'Helpful rating must be a boolean',
      };
    }

    return null;
  }

  private mapError(error: unknown): ServiceError {
    if (isApiError(error)) {
      return {
        code: this.getErrorCode(error.statusCode),
        message: error.getUserMessage(),
        details: {
          errorId: error.errorId,
          statusCode: error.statusCode,
          endpoint: error.endpoint,
        },
      };
    }

    const message = error instanceof Error ? error.message : String(error);

    if (message.includes('404')) {
      return {
        code: ErrorCode.NOT_FOUND,
        message: 'Note not found',
      };
    }

    if (message.includes('401') || message.includes('403')) {
      return {
        code: ErrorCode.UNAUTHORIZED,
        message: 'Unauthorized to rate note',
      };
    }

    return {
      code: ErrorCode.API_ERROR,
      message: 'Failed to submit rating. Please try again later.',
    };
  }

  private getErrorCode(statusCode: number): ErrorCode {
    switch (statusCode) {
      case 400:
        return ErrorCode.VALIDATION_ERROR;
      case 401:
      case 403:
        return ErrorCode.UNAUTHORIZED;
      case 404:
        return ErrorCode.NOT_FOUND;
      case 409:
        return ErrorCode.CONFLICT;
      case 429:
        return ErrorCode.RATE_LIMIT;
      default:
        return ErrorCode.API_ERROR;
    }
  }
}
