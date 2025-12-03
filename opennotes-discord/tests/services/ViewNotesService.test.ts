import { jest } from '@jest/globals';
import { ViewNotesService } from '../../src/services/ViewNotesService.js';
import { ApiClient } from '../../src/lib/api-client.js';
import type { RateLimiterInterface } from '../../src/services/RateLimitFactory.js';
import { ErrorCode } from '../../src/services/types.js';

// Mock the logger
jest.mock('../../src/logger.js', () => ({
  logger: {
    info: jest.fn(),
    error: jest.fn(),
    warn: jest.fn(),
    debug: jest.fn(),
  },
}));

describe('ViewNotesService', () => {
  let service: ViewNotesService;
  let mockApiClient: jest.Mocked<ApiClient>;
  let mockRateLimiter: jest.Mocked<RateLimiterInterface>;

  beforeEach(() => {
    mockApiClient = {
      getNotes: jest.fn(),
    } as any;

    mockRateLimiter = {
      check: jest.fn(),
      createError: jest.fn(),
    } as any;

    service = new ViewNotesService(mockApiClient, mockRateLimiter);
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe('Validation', () => {
    it('should return error for missing messageId', async () => {
      const result = await service.execute({
        messageId: '',
      });

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe(ErrorCode.VALIDATION_ERROR);
      expect(result.error?.message).toBe('Message ID is required');
    });

    it('should return error for whitespace-only messageId', async () => {
      const result = await service.execute({
        messageId: '   ',
      });

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe(ErrorCode.VALIDATION_ERROR);
      expect(result.error?.message).toBe('Message ID is required');
    });

    it('should accept valid messageId', async () => {
      mockRateLimiter.check.mockResolvedValue({
        allowed: true,
        remaining: 5,
        resetAt: Date.now() + 60000,
      });

      mockApiClient.getNotes.mockResolvedValue([]);

      const result = await service.execute(
        {
          messageId: 'msg-123',
        },
        'user-123'
      );

      expect(result.success).toBe(true);
    });
  });

  describe('Viewing Notes', () => {
    beforeEach(() => {
      mockRateLimiter.check.mockResolvedValue({
        allowed: true,
        remaining: 5,
        resetAt: Date.now() + 60000,
      });
    });

    it('should retrieve notes successfully', async () => {
      const mockNotes = [
        {
          id: '1',
          messageId: 'msg-123',
          authorId: 'user-456',
          content: 'First note content',
          createdAt: Date.now(),
          helpfulCount: 0,
          notHelpfulCount: 0,
        },
        {
          id: '2',
          messageId: 'msg-123',
          authorId: 'user-789',
          content: 'Second note content',
          createdAt: Date.now(),
          helpfulCount: 0,
          notHelpfulCount: 0,
        },
      ];

      mockApiClient.getNotes.mockResolvedValue(mockNotes);

      const result = await service.execute(
        {
          messageId: 'msg-123',
        },
        'user-123'
      );

      expect(result.success).toBe(true);
      expect(result.data?.notes).toEqual(mockNotes);
      expect(mockApiClient.getNotes).toHaveBeenCalledWith('msg-123');
    });

    it('should handle empty notes array', async () => {
      mockApiClient.getNotes.mockResolvedValue([]);

      const result = await service.execute(
        {
          messageId: 'msg-123',
        },
        'user-123'
      );

      expect(result.success).toBe(true);
      expect(result.data?.notes).toEqual([]);
      expect(result.data?.notes.length).toBe(0);
    });

    it('should retrieve notes without userId', async () => {
      const mockNotes = [
        {
          id: '1',
          messageId: 'msg-123',
          authorId: 'user-456',
          content: 'Note content',
          createdAt: Date.now(),
          helpfulCount: 0,
          notHelpfulCount: 0,
        },
      ];

      mockApiClient.getNotes.mockResolvedValue(mockNotes);

      const result = await service.execute({
        messageId: 'msg-123',
      });

      expect(result.success).toBe(true);
      expect(result.data?.notes).toEqual(mockNotes);
    });

    it('should handle single note', async () => {
      const mockNotes = [
        {
          id: '1',
          messageId: 'msg-123',
          authorId: 'user-456',
          content: 'Single note content',
          createdAt: Date.now(),
          helpfulCount: 0,
          notHelpfulCount: 0,
        },
      ];

      mockApiClient.getNotes.mockResolvedValue(mockNotes);

      const result = await service.execute(
        {
          messageId: 'msg-123',
        },
        'user-123'
      );

      expect(result.success).toBe(true);
      expect(result.data?.notes.length).toBe(1);
    });

    it('should handle multiple notes', async () => {
      const mockNotes = Array.from({ length: 10 }, (_, i) => ({
        id: String(i + 1),
        messageId: 'msg-123',
        authorId: `user-${i}`,
        content: `Note content ${i}`,
        createdAt: Date.now(),
        helpfulCount: 0,
        notHelpfulCount: 0,
      }));

      mockApiClient.getNotes.mockResolvedValue(mockNotes);

      const result = await service.execute(
        {
          messageId: 'msg-123',
        },
        'user-123'
      );

      expect(result.success).toBe(true);
      expect(result.data?.notes.length).toBe(10);
    });
  });

  describe('Error Handling', () => {
    beforeEach(() => {
      mockRateLimiter.check.mockResolvedValue({
        allowed: true,
        remaining: 5,
        resetAt: Date.now() + 60000,
      });
    });

    it('should handle 404 not found error', async () => {
      mockApiClient.getNotes.mockRejectedValue(new Error('404 Not Found'));

      const result = await service.execute(
        {
          messageId: 'msg-123',
        },
        'user-123'
      );

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe(ErrorCode.NOT_FOUND);
      expect(result.error?.message).toBe('Message not found');
    });

    it('should handle 404 error in message text', async () => {
      mockApiClient.getNotes.mockRejectedValue(
        new Error('Message not found (404)')
      );

      const result = await service.execute(
        {
          messageId: 'msg-123',
        },
        'user-123'
      );

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe(ErrorCode.NOT_FOUND);
      expect(result.error?.message).toBe('Message not found');
    });

    it('should handle generic errors', async () => {
      mockApiClient.getNotes.mockRejectedValue(new Error('Network error'));

      const result = await service.execute(
        {
          messageId: 'msg-123',
        },
        'user-123'
      );

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe(ErrorCode.API_ERROR);
      expect(result.error?.message).toBe('Failed to retrieve notes. Please try again later.');
    });

    it('should handle non-Error exceptions', async () => {
      mockApiClient.getNotes.mockRejectedValue('String error');

      const result = await service.execute(
        {
          messageId: 'msg-123',
        },
        'user-123'
      );

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe(ErrorCode.API_ERROR);
    });

    it('should handle API timeout', async () => {
      mockApiClient.getNotes.mockRejectedValue(new Error('Request timeout'));

      const result = await service.execute(
        {
          messageId: 'msg-123',
        },
        'user-123'
      );

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe(ErrorCode.API_ERROR);
    });

    it('should handle malformed response', async () => {
      mockApiClient.getNotes.mockRejectedValue(
        new Error('Invalid JSON response')
      );

      const result = await service.execute(
        {
          messageId: 'msg-123',
        },
        'user-123'
      );

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe(ErrorCode.API_ERROR);
    });
  });

  describe('Edge Cases', () => {
    beforeEach(() => {
      mockRateLimiter.check.mockResolvedValue({
        allowed: true,
        remaining: 5,
        resetAt: Date.now() + 60000,
      });
    });

    it('should handle special characters in messageId', async () => {
      mockApiClient.getNotes.mockResolvedValue([]);

      const result = await service.execute(
        {
          messageId: 'msg-123-special_chars',
        },
        'user-123'
      );

      expect(result.success).toBe(true);
      expect(mockApiClient.getNotes).toHaveBeenCalledWith('msg-123-special_chars');
    });

    it('should handle very long messageId', async () => {
      const longMessageId = 'msg-' + 'a'.repeat(100);
      mockApiClient.getNotes.mockResolvedValue([]);

      const result = await service.execute(
        {
          messageId: longMessageId,
        },
        'user-123'
      );

      expect(result.success).toBe(true);
      expect(mockApiClient.getNotes).toHaveBeenCalledWith(longMessageId);
    });

    it('should handle numeric messageId as string', async () => {
      mockApiClient.getNotes.mockResolvedValue([]);

      const result = await service.execute(
        {
          messageId: '123456789',
        },
        'user-123'
      );

      expect(result.success).toBe(true);
      expect(mockApiClient.getNotes).toHaveBeenCalledWith('123456789');
    });

    it('should handle notes with different helpful counts', async () => {
      const mockNotes = [
        {
          id: '1',
          messageId: 'msg-123',
          authorId: 'user-456',
          content: 'Active note',
          createdAt: Date.now(),
          helpfulCount: 5,
          notHelpfulCount: 1,
        },
        {
          id: '2',
          messageId: 'msg-123',
          authorId: 'user-789',
          content: 'Another note',
          createdAt: Date.now(),
          helpfulCount: 2,
          notHelpfulCount: 3,
        },
      ];

      mockApiClient.getNotes.mockResolvedValue(mockNotes);

      const result = await service.execute(
        {
          messageId: 'msg-123',
        },
        'user-123'
      );

      expect(result.success).toBe(true);
      expect(result.data?.notes.length).toBe(2);
    });

    it('should handle concurrent requests for same message', async () => {
      const mockNotes = [
        {
          id: '1',
          messageId: 'msg-123',
          authorId: 'user-456',
          content: 'Note content',
          createdAt: Date.now(),
          helpfulCount: 0,
          notHelpfulCount: 0,
        },
      ];

      mockApiClient.getNotes.mockResolvedValue(mockNotes);

      const results = await Promise.all([
        service.execute({ messageId: 'msg-123' }, 'user-1'),
        service.execute({ messageId: 'msg-123' }, 'user-2'),
        service.execute({ messageId: 'msg-123' }, 'user-3'),
      ]);

      expect(results.every(r => r.success)).toBe(true);
      expect(mockApiClient.getNotes).toHaveBeenCalledTimes(3);
    });
  });
});
