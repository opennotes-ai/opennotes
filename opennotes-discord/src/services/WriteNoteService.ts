import { ApiClient, UserContext } from '../lib/api-client.js';
import { logger } from '../logger.js';
import {
  ServiceResult,
  WriteNoteInput,
  WriteNoteResult,
  ErrorCode,
  ServiceError,
} from './types.js';
import type { RateLimiterInterface } from './RateLimitFactory.js';
import { NoteContextService } from './NoteContextService.js';
import { getErrorMessage, getErrorStack, hasMessage } from '../utils/error-handlers.js';

export class WriteNoteService {
  private noteContextService: NoteContextService;

  constructor(
    private apiClient: ApiClient,
    private rateLimiter: RateLimiterInterface
  ) {
    this.noteContextService = new NoteContextService();
  }

  async execute(input: WriteNoteInput): Promise<ServiceResult<WriteNoteResult>> {
    const validationError = this.validate(input);
    if (validationError) {
      return { success: false, error: validationError };
    }

    const rateLimit = await this.rateLimiter.check(input.authorId);
    if (!rateLimit.allowed) {
      return {
        success: false,
        error: this.rateLimiter.createError(rateLimit.resetAt),
      };
    }

    try {
      const userContext: UserContext = {
        userId: input.authorId,
        username: input.username,
        displayName: input.displayName,
        avatarUrl: input.avatarUrl,
        guildId: input.guildId,
      };

      const note = await this.apiClient.createNote({
        messageId: input.messageId,
        authorId: input.authorId,
        content: input.content,
        channelId: input.channelId,
        requestId: input.requestId,
        originalMessageContent: input.originalMessageContent,
        classification: input.classification,
      }, userContext);

      logger.info('Note created via service', {
        noteId: note.id,
        userId: input.authorId,
        messageId: input.messageId,
      });

      // Store note context for auto-posting
      if (input.channelId && input.guildId) {
        try {
          await this.noteContextService.storeNoteContext({
            noteId: String(note.id),
            originalMessageId: input.messageId,
            channelId: input.channelId,
            guildId: input.guildId,
            authorId: input.authorId,
          });
        } catch (error: unknown) {
          logger.warn('Failed to store note context, auto-posting may not work for this note', {
            noteId: note.id,
            error: getErrorMessage(error),
          });
          // Don't fail note creation if context storage fails
        }
      }

      return {
        success: true,
        data: { note },
      };
    } catch (error: unknown) {
      logger.error('Failed to create note in service', {
        errorMessage: getErrorMessage(error),
        errorStack: getErrorStack(error),
        userId: input.authorId,
        messageId: input.messageId,
      });

      return {
        success: false,
        error: this.mapError(error),
      };
    }
  }

  private validate(input: WriteNoteInput): ServiceError | null {
    if (!input.messageId || input.messageId.trim().length === 0) {
      return {
        code: ErrorCode.VALIDATION_ERROR,
        message: 'Message ID is required',
      };
    }

    if (!input.authorId || input.authorId.trim().length === 0) {
      return {
        code: ErrorCode.VALIDATION_ERROR,
        message: 'Author ID is required',
      };
    }

    if (!input.content || input.content.trim().length === 0) {
      return {
        code: ErrorCode.VALIDATION_ERROR,
        message: 'Note content is required',
      };
    }

    if (input.content.length < 10) {
      return {
        code: ErrorCode.VALIDATION_ERROR,
        message: 'Note content must be at least 10 characters',
      };
    }

    if (input.content.length > 1000) {
      return {
        code: ErrorCode.VALIDATION_ERROR,
        message: 'Note content must not exceed 1000 characters',
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
        message: 'Unauthorized to create note',
      };
    }

    return {
      code: ErrorCode.API_ERROR,
      message: 'Failed to create note. Please try again later.',
    };
  }
}
