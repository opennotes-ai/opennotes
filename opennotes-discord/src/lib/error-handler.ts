/**
 * Error classification and user-friendly message generation for API failures
 */

export enum ApiErrorType {
  NETWORK_ERROR = 'NETWORK_ERROR',
  SERVER_ERROR = 'SERVER_ERROR',
  AUTH_ERROR = 'AUTH_ERROR',
  RATE_LIMIT_ERROR = 'RATE_LIMIT_ERROR',
  NOT_FOUND_ERROR = 'NOT_FOUND_ERROR',
  UNKNOWN_ERROR = 'UNKNOWN_ERROR',
}

/**
 * Classifies an error based on its message and type
 */
export function classifyApiError(error: unknown): ApiErrorType {
  if (!error) {
    return ApiErrorType.UNKNOWN_ERROR;
  }

  const errorMessage = error instanceof Error ? error.message : String(error);
  const lowerMessage = errorMessage.toLowerCase();

  // Check for authentication/authorization errors
  if (lowerMessage.includes('api error: 401') || lowerMessage.includes('api error: 403')) {
    return ApiErrorType.AUTH_ERROR;
  }

  // Check for rate limiting
  if (lowerMessage.includes('api error: 429')) {
    return ApiErrorType.RATE_LIMIT_ERROR;
  }

  // Check for not found errors
  if (lowerMessage.includes('api error: 404')) {
    return ApiErrorType.NOT_FOUND_ERROR;
  }

  // Check for server errors (5xx)
  if (/api error: 5\d{2}/.test(lowerMessage)) {
    return ApiErrorType.SERVER_ERROR;
  }

  // Check for network/connection errors
  if (
    lowerMessage.includes('fetch failed') ||
    lowerMessage.includes('network') ||
    lowerMessage.includes('econnrefused') ||
    lowerMessage.includes('enotfound') ||
    lowerMessage.includes('etimedout') ||
    lowerMessage.includes('connection') ||
    lowerMessage.includes('timeout')
  ) {
    return ApiErrorType.NETWORK_ERROR;
  }

  return ApiErrorType.UNKNOWN_ERROR;
}

/**
 * Returns a user-friendly error message based on error type and context
 */
export function getErrorMessage(errorType: ApiErrorType, context: string): string {
  switch (errorType) {
    case ApiErrorType.NETWORK_ERROR:
      return `Unable to connect to the notes server. Please check your connection and try again in a moment.`;

    case ApiErrorType.SERVER_ERROR:
      return `The notes server is experiencing issues. Please try again later.`;

    case ApiErrorType.AUTH_ERROR:
      return `Authentication failed. Please contact an administrator to verify bot permissions.`;

    case ApiErrorType.RATE_LIMIT_ERROR:
      return `Too many requests to the server. Please wait a moment before trying again.`;

    case ApiErrorType.NOT_FOUND_ERROR:
      return `The requested resource was not found on the server.`;

    case ApiErrorType.UNKNOWN_ERROR:
    default:
      return `An unexpected error occurred while ${context}. Please try again later.`;
  }
}

/**
 * Generates context-specific error messages for the notes queue command
 */
export function getQueueErrorMessage(errorType: ApiErrorType): string {
  switch (errorType) {
    case ApiErrorType.NETWORK_ERROR:
      return `Unable to connect to the notes server. The queue could not be created. Please try again in a moment.`;

    case ApiErrorType.SERVER_ERROR:
      return `The notes server is experiencing issues. The queue could not be created. Please try again later.`;

    case ApiErrorType.AUTH_ERROR:
      return `Authentication failed. Unable to access the notes queue. Please contact an administrator.`;

    case ApiErrorType.RATE_LIMIT_ERROR:
      return `Too many requests to the server. Please wait before creating another queue.`;

    case ApiErrorType.UNKNOWN_ERROR:
    default:
      return `Failed to create the notes queue due to an unexpected error. Please try again later.`;
  }
}

/**
 * Generates error messages specific to pagination failures
 */
export function getPaginationErrorMessage(errorType: ApiErrorType): string {
  switch (errorType) {
    case ApiErrorType.NETWORK_ERROR:
      return `Unable to connect to the server. Failed to load the next page. Please close and reopen the queue.`;

    case ApiErrorType.SERVER_ERROR:
      return `Server error while loading the next page. Please close and reopen the queue.`;

    case ApiErrorType.AUTH_ERROR:
      return `Authentication failed. Please close the queue and try again.`;

    case ApiErrorType.RATE_LIMIT_ERROR:
      return `Too many requests. Please wait a moment before navigating pages.`;

    case ApiErrorType.UNKNOWN_ERROR:
    default:
      return `Failed to load the next page. Please close and reopen the queue.`;
  }
}
