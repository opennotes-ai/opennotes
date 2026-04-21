import { nanoid } from 'nanoid';

/**
 * Generates a unique error ID with the format err_<random>
 */
export function generateErrorId(): string {
  return `err_${nanoid(12)}`;
}

/**
 * Base error class with contextual information for debugging
 */
export class ErrorWithContext extends Error {
  constructor(
    message: string,
    public readonly context: Record<string, unknown> = {},
    public readonly errorId: string = generateErrorId()
  ) {
    super(message);
    this.name = 'ErrorWithContext';
    Error.captureStackTrace(this, this.constructor);
  }
}

/**
 * API-specific error with endpoint and status code information
 */
export class ApiError extends ErrorWithContext {
  public readonly detail?: string;

  constructor(
    message: string,
    public readonly endpoint: string,
    public readonly statusCode: number,
    public readonly responseBody?: unknown,
    public readonly requestBody?: unknown,
    context: Record<string, unknown> = {}
  ) {
    super(message, { ...context, endpoint, statusCode, responseBody, requestBody });
    this.name = 'ApiError';
    this.detail = this.extractDetail(responseBody);
  }

  private extractDetail(responseBody: unknown): string | undefined {
    if (responseBody && typeof responseBody === 'object') {
      const body = responseBody as Record<string, unknown>;
      return (body.detail as string | undefined) || (body.message as string | undefined);
    }
    return undefined;
  }

  getUserMessage(): string {
    if (this.detail) {
      return this.detail;
    }
    return this.getGenericMessage(this.statusCode);
  }

  private getGenericMessage(status: number): string {
    switch (status) {
      case 400:
        return 'Invalid request. Please check your input.';
      case 401:
        return 'Authentication required.';
      case 403:
        return 'You do not have permission to perform this action.';
      case 404:
        return 'Resource not found.';
      case 409:
        return 'This action conflicts with existing data.';
      case 429:
        return 'Too many requests. Please try again later.';
      case 500:
        return 'Server error occurred. Please try again later.';
      case 503:
        return 'Service temporarily unavailable. Please try again later.';
      default:
        return 'An error occurred. Please try again.';
    }
  }
}

/**
 * Context information for command errors
 */
export interface CommandErrorContext {
  command: string;
  userId: string;
  guildId?: string;
  channelId?: string;
  messageId?: string;
  input?: Record<string, unknown>;
}

/**
 * Formats an error message for user display with error ID
 */
export function formatErrorForUser(errorId: string, message?: string): string {
  const baseMessage = message || 'An error occurred while processing your request.';
  return `${baseMessage}\n\nError ID: \`${errorId}\`\n\nIf this issue persists, please contact support with the Error ID.`;
}

/**
 * Extracts detailed information from an unknown error
 */
export function extractErrorDetails(error: unknown): {
  message: string;
  stack?: string;
  type: string;
} {
  if (error instanceof Error) {
    return {
      message: error.message,
      stack: error.stack,
      type: error.name,
    };
  }

  return {
    message: String(error),
    type: 'UnknownError',
  };
}
