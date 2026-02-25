import { jest } from '@jest/globals';
import { ViewNotesService } from '../../src/services/ViewNotesService.js';
import { ErrorCode } from '../../src/services/types.js';
import { apiClientFactory, rateLimiterFactory, type MockApiClient, type MockRateLimiter } from '../factories/index.js';

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
  let mockApiClient: MockApiClient;
  let mockRateLimiter: MockRateLimiter;

  beforeEach(() => {
    mockApiClient = apiClientFactory.build();
    mockRateLimiter = rateLimiterFactory.build();

    service = new ViewNotesService(mockApiClient as any, mockRateLimiter);
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
    it('should retrieve notes successfully', async () => {
      const result = await service.execute(
        {
          messageId: 'msg-123',
        },
        'user-123'
      );

      expect(result.success).toBe(true);
      expect(result.data?.notes.data.length).toBeGreaterThanOrEqual(0);
      expect(mockApiClient.getNotes).toHaveBeenCalledWith('msg-123');
    });

    it('should handle empty notes array', async () => {
      mockApiClient.getNotes.mockResolvedValue({
        data: [],
        jsonapi: { version: '1.1' },
        meta: { count: 0 },
      });

      const result = await service.execute(
        {
          messageId: 'msg-123',
        },
        'user-123'
      );

      expect(result.success).toBe(true);
      expect(result.data?.notes.data.length).toBe(0);
    });

    it('should retrieve notes without userId', async () => {
      const result = await service.execute({
        messageId: 'msg-123',
      });

      expect(result.success).toBe(true);
      expect(result.data?.notes).toBeDefined();
    });

    it('should handle single note', async () => {
      const result = await service.execute(
        {
          messageId: 'msg-123',
        },
        'user-123'
      );

      expect(result.success).toBe(true);
      expect(result.data?.notes.data.length).toBeGreaterThanOrEqual(1);
    });

    it('should handle multiple notes', async () => {
      mockApiClient.getNotes.mockResolvedValue({
        data: Array.from({ length: 10 }, (_, i) => ({
          type: 'notes' as const,
          id: String(i + 1),
          attributes: {
            summary: `Note content ${i}`,
            classification: 'NOT_MISLEADING',
            status: 'NEEDS_MORE_RATINGS' as const,
            helpfulness_score: 0,
            author_id: `user-${i}`,
            community_server_id: 'server-123',
            channel_id: null,
            request_id: null,
            ratings_count: 0,
            force_published: false,
            force_published_at: null,
            created_at: new Date().toISOString(),
            updated_at: null,
            ai_generated: false,
          },
        })),
        jsonapi: { version: '1.1' },
        meta: { count: 10 },
      });

      const result = await service.execute(
        {
          messageId: 'msg-123',
        },
        'user-123'
      );

      expect(result.success).toBe(true);
      expect(result.data?.notes.data.length).toBe(10);
    });
  });

  describe('Error Handling', () => {
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
    it('should handle special characters in messageId', async () => {
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
      const result = await service.execute(
        {
          messageId: 'msg-123',
        },
        'user-123'
      );

      expect(result.success).toBe(true);
      expect(result.data?.notes).toBeDefined();
    });

    it('should handle concurrent requests for same message', async () => {
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
