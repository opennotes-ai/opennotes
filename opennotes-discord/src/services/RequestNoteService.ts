import { ApiClient, UserContext } from '../lib/api-client.js';
import { logger } from '../logger.js';
import {
  ServiceResult,
  RequestNoteInput,
  ErrorCode,
  ServiceError,
} from './types.js';
import type { RateLimiterInterface } from './RateLimitFactory.js';
import { getErrorMessage, getErrorStack, hasMessage } from '../utils/error-handlers.js';

export class RequestNoteService {
  constructor(
    private apiClient: ApiClient,
    private rateLimiter: RateLimiterInterface
  ) {}

  async execute(input: RequestNoteInput): Promise<ServiceResult<void>> {
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
        guildId: input.community_server_id,
      };

      await this.apiClient.requestNote({
        messageId: input.messageId,
        userId: input.userId,
        community_server_id: input.community_server_id, // Required: Discord guild/server ID
        discord_channel_id: input.channelId,
        reason: input.reason,
        originalMessageContent: input.originalMessageContent,
        attachmentUrl: input.attachmentUrl,
        attachmentType: input.attachmentType,
        attachmentMetadata: input.attachmentMetadata,
        embeddedImageUrl: input.embeddedImageUrl,
      }, userContext);

      logger.info('Note requested via service', {
        userId: input.userId,
        messageId: input.messageId,
        hasReason: !!input.reason,
        hasOriginalContent: !!input.originalMessageContent,
        hasAttachment: !!input.attachmentUrl,
        attachmentType: input.attachmentType,
        hasEmbeddedImage: !!input.embeddedImageUrl,
      });

      return { success: true };
    } catch (error: unknown) {
      logger.error('Failed to request note in service', {
        errorMessage: getErrorMessage(error),
        errorStack: getErrorStack(error),
        userId: input.userId,
        messageId: input.messageId,
      });

      return {
        success: false,
        error: this.mapError(error),
      };
    }
  }

  private validate(input: RequestNoteInput): ServiceError | null {
    if (!input.messageId || input.messageId.trim().length === 0) {
      return {
        code: ErrorCode.VALIDATION_ERROR,
        message: 'Message ID is required',
      };
    }

    if (!input.userId || input.userId.trim().length === 0) {
      return {
        code: ErrorCode.VALIDATION_ERROR,
        message: 'User ID is required',
      };
    }

    if (input.reason && input.reason.length > 500) {
      return {
        code: ErrorCode.VALIDATION_ERROR,
        message: 'Reason must not exceed 500 characters',
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

    if (message.includes('401') || message.includes('403')) {
      return {
        code: ErrorCode.UNAUTHORIZED,
        message: 'Unauthorized to request note',
      };
    }

    return {
      code: ErrorCode.API_ERROR,
      message: 'Failed to submit note request. Please try again later.',
    };
  }
}
