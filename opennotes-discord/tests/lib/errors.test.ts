import {
  generateErrorId,
  ErrorWithContext,
  ApiError,
  formatErrorForUser,
  extractErrorDetails,
} from '../../src/lib/errors.js';

describe('Error Utilities', () => {
  describe('generateErrorId', () => {
    it('should generate unique error IDs with err_ prefix', () => {
      const id1 = generateErrorId();
      const id2 = generateErrorId();

      expect(id1).toMatch(/^err_[a-zA-Z0-9_-]{12}$/);
      expect(id2).toMatch(/^err_[a-zA-Z0-9_-]{12}$/);
      expect(id1).not.toBe(id2);
    });

    it('should generate IDs that are exactly 16 characters long', () => {
      const id = generateErrorId();
      expect(id.length).toBe(16); // 'err_' (4) + 12 characters
    });
  });

  describe('ErrorWithContext', () => {
    it('should create error with message and context', () => {
      const context = { userId: '123', command: 'test' };
      const error = new ErrorWithContext('Test error', context);

      expect(error.message).toBe('Test error');
      expect(error.context.userId).toBe('123');
      expect(error.context.command).toBe('test');
      expect(error.name).toBe('ErrorWithContext');
    });

    it('should auto-generate error ID if not provided', () => {
      const error = new ErrorWithContext('Test error');

      expect(error.errorId).toMatch(/^err_/);
      expect(error.errorId.length).toBe(16);
    });

    it('should use provided error ID', () => {
      const customId = 'err_custom12345';
      const error = new ErrorWithContext('Test error', {}, customId);

      expect(error.errorId).toBe(customId);
    });

    it('should include context in error object', () => {
      const context = { endpoint: '/api/test', statusCode: 500 };
      const error = new ErrorWithContext('API failed', context);

      expect(error.context.endpoint).toBe('/api/test');
      expect(error.context.statusCode).toBe(500);
    });

    it('should have stack trace', () => {
      const error = new ErrorWithContext('Test error');

      expect(error.stack).toBeDefined();
      expect(error.stack).toContain('ErrorWithContext');
    });
  });

  describe('ApiError', () => {
    it('should create API error with all details', () => {
      const error = new ApiError(
        'API request failed',
        '/api/v1/notes',
        500,
        { error: 'Internal Server Error' },
        { noteId: 123 }
      );

      expect(error.message).toBe('API request failed');
      expect(error.endpoint).toBe('/api/v1/notes');
      expect(error.statusCode).toBe(500);
      expect(error.responseBody).toEqual({ error: 'Internal Server Error' });
      expect(error.requestBody).toEqual({ noteId: 123 });
      expect(error.name).toBe('ApiError');
    });

    it('should include endpoint and status in context', () => {
      const error = new ApiError(
        'Not found',
        '/api/v1/users/999',
        404,
        { message: 'User not found' }
      );

      expect(error.context.endpoint).toBe('/api/v1/users/999');
      expect(error.context.statusCode).toBe(404);
      expect(error.context.responseBody).toEqual({ message: 'User not found' });
    });

    it('should merge additional context', () => {
      const error = new ApiError(
        'Rate limited',
        '/api/v2/ratings',
        429,
        { retry_after: 60 },
        undefined,
        { userId: '123', attempt: 3 }
      );

      expect(error.context.userId).toBe('123');
      expect(error.context.attempt).toBe(3);
      expect(error.context.endpoint).toBe('/api/v2/ratings');
      expect(error.context.statusCode).toBe(429);
    });

    it('should auto-generate error ID', () => {
      const error = new ApiError('Error', '/api/test', 500);

      expect(error.errorId).toMatch(/^err_/);
    });

    it('should extract detail from responseBody with detail field', () => {
      const error = new ApiError(
        'Conflict',
        '/api/v2/ratings',
        409,
        { detail: 'Rating already exists for this note by this user' }
      );

      expect(error.detail).toBe('Rating already exists for this note by this user');
    });

    it('should extract detail from responseBody with message field', () => {
      const error = new ApiError(
        'Not Found',
        '/api/v1/notes/999',
        404,
        { message: 'Note not found' }
      );

      expect(error.detail).toBe('Note not found');
    });

    it('should have undefined detail when responseBody has neither detail nor message', () => {
      const error = new ApiError(
        'Error',
        '/api/test',
        500,
        { error: 'Some error' }
      );

      expect(error.detail).toBeUndefined();
    });

    it('should have undefined detail when responseBody is not an object', () => {
      const error = new ApiError(
        'Error',
        '/api/test',
        500,
        'string response'
      );

      expect(error.detail).toBeUndefined();
    });

    it('should return detail in getUserMessage when detail exists', () => {
      const error = new ApiError(
        'Conflict',
        '/api/v2/ratings',
        409,
        { detail: 'Rating already exists' }
      );

      expect(error.getUserMessage()).toBe('Rating already exists');
    });

    it('should return generic message for 409 when no detail exists', () => {
      const error = new ApiError(
        'Conflict',
        '/api/v2/ratings',
        409
      );

      expect(error.getUserMessage()).toBe('This action conflicts with existing data.');
    });

    it('should return generic message for 404', () => {
      const error = new ApiError(
        'Not Found',
        '/api/v1/notes/999',
        404
      );

      expect(error.getUserMessage()).toBe('Resource not found.');
    });

    it('should return generic message for 403', () => {
      const error = new ApiError(
        'Forbidden',
        '/api/v1/admin',
        403
      );

      expect(error.getUserMessage()).toBe('You do not have permission to perform this action.');
    });

    it('should return generic message for 500', () => {
      const error = new ApiError(
        'Server Error',
        '/api/v1/test',
        500
      );

      expect(error.getUserMessage()).toBe('Server error occurred. Please try again later.');
    });

    it('should return generic message for unknown status codes', () => {
      const error = new ApiError(
        'Unknown Error',
        '/api/test',
        418
      );

      expect(error.getUserMessage()).toBe('An error occurred. Please try again.');
    });
  });

  describe('formatErrorForUser', () => {
    it('should format error with custom message and error ID', () => {
      const errorId = 'err_test123456';
      const message = 'Failed to create note';
      const result = formatErrorForUser(errorId, message);

      expect(result).toContain(message);
      expect(result).toContain(errorId);
      expect(result).toContain('Error ID:');
      expect(result).toContain('contact support');
    });

    it('should use default message when not provided', () => {
      const errorId = 'err_default123';
      const result = formatErrorForUser(errorId);

      expect(result).toContain('An error occurred');
      expect(result).toContain(errorId);
    });

    it('should include error ID in code block', () => {
      const errorId = 'err_abc123';
      const result = formatErrorForUser(errorId, 'Test error');

      expect(result).toMatch(/`err_abc123`/);
    });

    it('should include support instructions', () => {
      const result = formatErrorForUser('err_test');

      expect(result.toLowerCase()).toContain('support');
      expect(result.toLowerCase()).toContain('persist');
    });
  });

  describe('extractErrorDetails', () => {
    it('should extract details from Error instance', () => {
      const error = new Error('Something went wrong');
      const details = extractErrorDetails(error);

      expect(details.message).toBe('Something went wrong');
      expect(details.type).toBe('Error');
      expect(details.stack).toBeDefined();
      expect(details.stack).toContain('Something went wrong');
    });

    it('should extract details from custom error', () => {
      const error = new ErrorWithContext('Custom error', { userId: '123' });
      const details = extractErrorDetails(error);

      expect(details.message).toBe('Custom error');
      expect(details.type).toBe('ErrorWithContext');
      expect(details.stack).toBeDefined();
    });

    it('should handle non-Error objects', () => {
      const details = extractErrorDetails('String error');

      expect(details.message).toBe('String error');
      expect(details.type).toBe('UnknownError');
      expect(details.stack).toBeUndefined();
    });

    it('should handle null/undefined', () => {
      const nullDetails = extractErrorDetails(null);
      expect(nullDetails.message).toBe('null');
      expect(nullDetails.type).toBe('UnknownError');

      const undefinedDetails = extractErrorDetails(undefined);
      expect(undefinedDetails.message).toBe('undefined');
      expect(undefinedDetails.type).toBe('UnknownError');
    });

    it('should handle objects without message', () => {
      const details = extractErrorDetails({ code: 500, status: 'error' });

      expect(details.message).toBe('[object Object]');
      expect(details.type).toBe('UnknownError');
    });

    it('should preserve stack trace from Error', () => {
      const error = new Error('Test error');
      const details = extractErrorDetails(error);

      expect(details.stack).toBe(error.stack);
    });

    it('should handle ApiError correctly', () => {
      const error = new ApiError('API failed', '/api/test', 500);
      const details = extractErrorDetails(error);

      expect(details.message).toBe('API failed');
      expect(details.type).toBe('ApiError');
      expect(details.stack).toBeDefined();
    });
  });

  describe('Error integration scenarios', () => {
    it('should create error with ID and extract details', () => {
      const errorId = generateErrorId();
      const error = new ErrorWithContext('Integration test', { test: true }, errorId);
      const details = extractErrorDetails(error);

      expect(error.errorId).toBe(errorId);
      expect(details.message).toBe('Integration test');
      expect(details.type).toBe('ErrorWithContext');
    });

    it('should format user message from generated error', () => {
      const error = new ApiError('Failed', '/api/test', 500);
      const userMessage = formatErrorForUser(error.errorId, 'Operation failed');

      expect(userMessage).toContain(error.errorId);
      expect(userMessage).toContain('Operation failed');
    });

    it('should maintain error context through extraction', () => {
      const context = { userId: '123', command: 'test', attempt: 2 };
      const error = new ErrorWithContext('Test', context);
      const details = extractErrorDetails(error);

      expect(error.context).toEqual(expect.objectContaining(context));
      expect(details.message).toBe('Test');
    });
  });
});
