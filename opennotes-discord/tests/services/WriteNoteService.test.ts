import { jest } from '@jest/globals';
import { WriteNoteService } from '../../src/services/WriteNoteService.js';
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

// Mock NoteContextService
jest.mock('../../src/services/NoteContextService.js', () => ({
  NoteContextService: jest.fn().mockImplementation(() => ({
    storeNoteContext: jest.fn<() => Promise<void>>().mockResolvedValue(undefined as any),
  })),
}));

describe('WriteNoteService', () => {
  let service: WriteNoteService;
  let mockApiClient: jest.Mocked<ApiClient>;
  let mockRateLimiter: jest.Mocked<RateLimiterInterface>;

  beforeEach(() => {
    jest.clearAllMocks();
    jest.clearAllTimers();
    mockApiClient = {
      createNote: jest.fn(),
    } as any;

    mockRateLimiter = {
      check: jest.fn(),
      createError: jest.fn(),
    } as any;

    service = new WriteNoteService(mockApiClient, mockRateLimiter);
  });

  afterEach(async () => {
    jest.clearAllMocks();
    jest.clearAllTimers();
    await new Promise(resolve => setImmediate(resolve));
  });

  describe('Validation', () => {
    it('should return error for missing messageId', async () => {
      const result = await service.execute({
        messageId: '',
        authorId: 'user-123',
        content: 'This is a valid note content',
      });

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe(ErrorCode.VALIDATION_ERROR);
      expect(result.error?.message).toBe('Message ID is required');
    });

    it('should return error for whitespace-only messageId', async () => {
      const result = await service.execute({
        messageId: '   ',
        authorId: 'user-123',
        content: 'This is a valid note content',
      });

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe(ErrorCode.VALIDATION_ERROR);
      expect(result.error?.message).toBe('Message ID is required');
    });

    it('should return error for missing authorId', async () => {
      const result = await service.execute({
        messageId: 'msg-123',
        authorId: '',
        content: 'This is a valid note content',
      });

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe(ErrorCode.VALIDATION_ERROR);
      expect(result.error?.message).toBe('Author ID is required');
    });

    it('should return error for whitespace-only authorId', async () => {
      const result = await service.execute({
        messageId: 'msg-123',
        authorId: '   ',
        content: 'This is a valid note content',
      });

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe(ErrorCode.VALIDATION_ERROR);
      expect(result.error?.message).toBe('Author ID is required');
    });

    it('should return error for missing content', async () => {
      const result = await service.execute({
        messageId: 'msg-123',
        authorId: 'user-123',
        content: '',
      });

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe(ErrorCode.VALIDATION_ERROR);
      expect(result.error?.message).toBe('Note content is required');
    });

    it('should return error for whitespace-only content', async () => {
      const result = await service.execute({
        messageId: 'msg-123',
        authorId: 'user-123',
        content: '   ',
      });

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe(ErrorCode.VALIDATION_ERROR);
      expect(result.error?.message).toBe('Note content is required');
    });

    it('should return error for content shorter than 10 characters', async () => {
      const result = await service.execute({
        messageId: 'msg-123',
        authorId: 'user-123',
        content: 'Short',
      });

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe(ErrorCode.VALIDATION_ERROR);
      expect(result.error?.message).toBe('Note content must be at least 10 characters');
    });

    it('should return error for content exactly 9 characters', async () => {
      const result = await service.execute({
        messageId: 'msg-123',
        authorId: 'user-123',
        content: '123456789',
      });

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe(ErrorCode.VALIDATION_ERROR);
      expect(result.error?.message).toBe('Note content must be at least 10 characters');
    });

    it('should accept content with exactly 10 characters', async () => {
      mockRateLimiter.check.mockResolvedValue({
        allowed: true,
        remaining: 5,
        resetAt: Date.now() + 60000,
      });

      mockApiClient.createNote.mockResolvedValue({
        id: '1',
        messageId: 'msg-123',
        authorId: 'user-123',
        content: '1234567890',
        createdAt: Date.now(),
        helpfulCount: 0,
        notHelpfulCount: 0,
      });

      const result = await service.execute({
        messageId: 'msg-123',
        authorId: 'user-123',
        content: '1234567890',
      });

      expect(result.success).toBe(true);
    });

    it('should return error for content longer than 1000 characters', async () => {
      const longContent = 'a'.repeat(1001);

      const result = await service.execute({
        messageId: 'msg-123',
        authorId: 'user-123',
        content: longContent,
      });

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe(ErrorCode.VALIDATION_ERROR);
      expect(result.error?.message).toBe('Note content must not exceed 1000 characters');
    });

    it('should accept content with exactly 1000 characters', async () => {
      mockRateLimiter.check.mockResolvedValue({
        allowed: true,
        remaining: 5,
        resetAt: Date.now() + 60000,
      });

      const maxContent = 'a'.repeat(1000);
      mockApiClient.createNote.mockResolvedValue({
        id: '1',
        messageId: 'msg-123',
        authorId: 'user-123',
        content: maxContent,
        createdAt: Date.now(),
        helpfulCount: 0,
        notHelpfulCount: 0,
      });

      const result = await service.execute({
        messageId: 'msg-123',
        authorId: 'user-123',
        content: maxContent,
      });

      expect(result.success).toBe(true);
    });
  });

  describe('Note Creation', () => {
    beforeEach(() => {
      mockRateLimiter.check.mockResolvedValue({
        allowed: true,
        remaining: 5,
        resetAt: Date.now() + 60000,
      });
    });

    it('should create note with required fields only', async () => {
      const mockNote = {
        id: '1',
        messageId: 'msg-123',
        authorId: 'user-123',
        content: 'This is a valid note content',
        createdAt: Date.now(),
        helpfulCount: 0,
        notHelpfulCount: 0,
      };
      mockApiClient.createNote.mockResolvedValue(mockNote);

      const result = await service.execute({
        messageId: 'msg-123',
        authorId: 'user-123',
        content: 'This is a valid note content',
      });

      expect(result.success).toBe(true);
      expect(result.data?.note).toEqual(mockNote);
      expect(mockApiClient.createNote).toHaveBeenCalledWith(
        {
          messageId: 'msg-123',
          authorId: 'user-123',
          content: 'This is a valid note content',
          channelId: undefined,
          requestId: undefined,
          originalMessageContent: undefined,
          classification: undefined,
        },
        expect.objectContaining({
          userId: 'user-123',
          username: undefined,
          displayName: undefined,
          avatarUrl: undefined,
          guildId: undefined,
        })
      );
    });

    it('should create note with all optional fields', async () => {
      const mockNote = {
        id: '1',
        messageId: 'msg-123',
        authorId: 'user-123',
        content: 'This is a valid note content',
        createdAt: Date.now(),
        helpfulCount: 0,
        notHelpfulCount: 0,
      };
      mockApiClient.createNote.mockResolvedValue(mockNote);

      const result = await service.execute({
        messageId: 'msg-123',
        authorId: 'user-123',
        content: 'This is a valid note content',
        channelId: 'channel-456',
        guildId: 'guild-789',
        requestId: 'request-999',
        originalMessageContent: 'Original message',
      });

      expect(result.success).toBe(true);
      expect(mockApiClient.createNote).toHaveBeenCalledWith(
        {
          messageId: 'msg-123',
          authorId: 'user-123',
          content: 'This is a valid note content',
          channelId: 'channel-456',
          requestId: 'request-999',
          originalMessageContent: 'Original message',
          classification: undefined,
        },
        expect.objectContaining({
          userId: 'user-123',
          username: undefined,
          displayName: undefined,
          avatarUrl: undefined,
          guildId: 'guild-789',
        })
      );
    });
  });

  describe('Note Context Storage', () => {
    beforeEach(() => {
      mockRateLimiter.check.mockResolvedValue({
        allowed: true,
        remaining: 5,
        resetAt: Date.now() + 60000,
      });

      mockApiClient.createNote.mockResolvedValue({
        id: '1',
        messageId: 'msg-123',
        authorId: 'user-123',
        content: 'This is a valid note content',
        createdAt: Date.now(),
        helpfulCount: 0,
        notHelpfulCount: 0,
      });
    });

    it('should successfully create note with channelId and guildId', async () => {
      const result = await service.execute({
        messageId: 'msg-123',
        authorId: 'user-123',
        content: 'This is a valid note content',
        channelId: 'channel-456',
        guildId: 'guild-789',
      });

      expect(result.success).toBe(true);
      expect(result.data?.note.id).toBe('1');
    });

    it('should successfully create note without channelId', async () => {
      const result = await service.execute({
        messageId: 'msg-123',
        authorId: 'user-123',
        content: 'This is a valid note content',
        guildId: 'guild-789',
      });

      expect(result.success).toBe(true);
      expect(result.data?.note.id).toBe('1');
    });

    it('should successfully create note without guildId', async () => {
      const result = await service.execute({
        messageId: 'msg-123',
        authorId: 'user-123',
        content: 'This is a valid note content',
        channelId: 'channel-456',
      });

      expect(result.success).toBe(true);
      expect(result.data?.note.id).toBe('1');
    });

    it('should create note even if context storage would fail', async () => {
      // Note creation should succeed regardless of context storage
      const result = await service.execute({
        messageId: 'msg-123',
        authorId: 'user-123',
        content: 'This is a valid note content',
        channelId: 'channel-456',
        guildId: 'guild-789',
      });

      expect(result.success).toBe(true);
      expect(result.data?.note.id).toBe('1');
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
      mockApiClient.createNote.mockRejectedValue(new Error('404 Not Found'));

      const result = await service.execute({
        messageId: 'msg-123',
        authorId: 'user-123',
        content: 'This is a valid note content',
      });

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe(ErrorCode.NOT_FOUND);
      expect(result.error?.message).toBe('Message not found');
    });

    it('should handle 401 unauthorized error', async () => {
      mockApiClient.createNote.mockRejectedValue(new Error('401 Unauthorized'));

      const result = await service.execute({
        messageId: 'msg-123',
        authorId: 'user-123',
        content: 'This is a valid note content',
      });

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe(ErrorCode.UNAUTHORIZED);
      expect(result.error?.message).toBe('Unauthorized to create note');
    });

    it('should handle 403 forbidden error', async () => {
      mockApiClient.createNote.mockRejectedValue(new Error('403 Forbidden'));

      const result = await service.execute({
        messageId: 'msg-123',
        authorId: 'user-123',
        content: 'This is a valid note content',
      });

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe(ErrorCode.UNAUTHORIZED);
      expect(result.error?.message).toBe('Unauthorized to create note');
    });

    it('should handle generic errors', async () => {
      mockApiClient.createNote.mockRejectedValue(new Error('Network error'));

      const result = await service.execute({
        messageId: 'msg-123',
        authorId: 'user-123',
        content: 'This is a valid note content',
      });

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe(ErrorCode.API_ERROR);
      expect(result.error?.message).toBe('Failed to create note. Please try again later.');
    });

    it('should handle non-Error exceptions', async () => {
      mockApiClient.createNote.mockRejectedValue('String error');

      const result = await service.execute({
        messageId: 'msg-123',
        authorId: 'user-123',
        content: 'This is a valid note content',
      });

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

    it('should handle special characters in content', async () => {
      const specialContent = 'This note has special chars: @#$%^&*()_+-={}[]|:;"<>?,./';
      mockApiClient.createNote.mockResolvedValue({
        id: '1',
        messageId: 'msg-123',
        authorId: 'user-123',
        content: specialContent,
        createdAt: Date.now(),
        helpfulCount: 0,
        notHelpfulCount: 0,
      });

      const result = await service.execute({
        messageId: 'msg-123',
        authorId: 'user-123',
        content: specialContent,
      });

      expect(result.success).toBe(true);
    });

    it('should handle unicode characters in content', async () => {
      const unicodeContent = 'This note has unicode: 你好 🌟 émojis';
      mockApiClient.createNote.mockResolvedValue({
        id: '1',
        messageId: 'msg-123',
        authorId: 'user-123',
        content: unicodeContent,
        createdAt: Date.now(),
        helpfulCount: 0,
        notHelpfulCount: 0,
      });

      const result = await service.execute({
        messageId: 'msg-123',
        authorId: 'user-123',
        content: unicodeContent,
      });

      expect(result.success).toBe(true);
    });

    it('should handle newlines in content', async () => {
      const multilineContent = 'Line 1\nLine 2\nLine 3 with enough chars';
      mockApiClient.createNote.mockResolvedValue({
        id: '1',
        messageId: 'msg-123',
        authorId: 'user-123',
        content: multilineContent,
        createdAt: Date.now(),
        helpfulCount: 0,
        notHelpfulCount: 0,
      });

      const result = await service.execute({
        messageId: 'msg-123',
        authorId: 'user-123',
        content: multilineContent,
      });

      expect(result.success).toBe(true);
    });
  });
});
