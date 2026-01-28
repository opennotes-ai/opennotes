import { jest } from '@jest/globals';
import { ErrorCode } from '../../src/services/types.js';
import { apiClientFactory, rateLimiterFactory, type MockApiClient, type MockRateLimiter } from '../factories/index.js';

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: {
    info: jest.fn(),
    error: jest.fn(),
    warn: jest.fn(),
    debug: jest.fn(),
  },
}));

const { RequestNoteService } = await import('../../src/services/RequestNoteService.js');

describe('RequestNoteService', () => {
  let service: InstanceType<typeof RequestNoteService>;
  let mockApiClient: MockApiClient;
  let mockRateLimiter: MockRateLimiter;

  const validInput = {
    messageId: 'msg-123',
    userId: '00000000-0000-0001-aaaa-000000000123',
    community_server_id: '1234567890123456789',
    channelId: 'channel-123',
    reason: 'Test reason',
    originalMessageContent: 'Test content',
    username: 'testuser',
    displayName: 'Test User',
    avatarUrl: 'https://example.com/avatar.png',
  };

  beforeEach(() => {
    jest.clearAllMocks();

    mockApiClient = apiClientFactory.build();
    mockRateLimiter = rateLimiterFactory.build();

    service = new RequestNoteService(mockApiClient as any, mockRateLimiter);
  });

  describe('Validation', () => {
    it('should return error for missing messageId', async () => {
      const result = await service.execute({
        ...validInput,
        messageId: '',
      });

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe(ErrorCode.VALIDATION_ERROR);
      expect(result.error?.message).toBe('Message ID is required');
    });

    it('should return error for missing userId', async () => {
      const result = await service.execute({
        ...validInput,
        userId: '',
      });

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe(ErrorCode.VALIDATION_ERROR);
      expect(result.error?.message).toBe('User ID is required');
    });

    it('should return error for reason exceeding 500 characters', async () => {
      const result = await service.execute({
        ...validInput,
        reason: 'a'.repeat(501),
      });

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe(ErrorCode.VALIDATION_ERROR);
      expect(result.error?.message).toBe('Reason must not exceed 500 characters');
    });
  });

  describe('Rate limiting', () => {
    it('should return error when rate limited', async () => {
      mockRateLimiter.check.mockResolvedValue({
        allowed: false,
        remaining: 0,
        resetAt: Date.now() + 60000,
      });
      mockRateLimiter.createError.mockReturnValue({
        code: ErrorCode.RATE_LIMIT_EXCEEDED,
        message: 'Rate limit exceeded',
      });

      const result = await service.execute(validInput);

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe(ErrorCode.RATE_LIMIT_EXCEEDED);
    });
  });

  describe('Platform ID handling', () => {
    it('should pass platform ID (Discord guild ID) directly to API', async () => {
      mockApiClient.requestNote.mockResolvedValue(undefined);

      await service.execute(validInput);

      expect(mockApiClient.requestNote).toHaveBeenCalledWith(
        expect.objectContaining({
          community_server_id: '1234567890123456789',
        }),
        expect.any(Object)
      );
    });
  });

  describe('Successful request', () => {
    it('should request note successfully with platform ID', async () => {
      mockApiClient.requestNote.mockResolvedValue(undefined);

      const result = await service.execute(validInput);

      expect(result.success).toBe(true);
      expect(mockApiClient.requestNote).toHaveBeenCalledWith(
        {
          messageId: 'msg-123',
          userId: '00000000-0000-0001-aaaa-000000000123',
          community_server_id: '1234567890123456789',
          discord_channel_id: 'channel-123',
          reason: 'Test reason',
          originalMessageContent: 'Test content',
          attachmentUrl: undefined,
          attachmentType: undefined,
          attachmentMetadata: undefined,
          embeddedImageUrl: undefined,
        },
        {
          userId: '00000000-0000-0001-aaaa-000000000123',
          username: 'testuser',
          displayName: 'Test User',
          avatarUrl: 'https://example.com/avatar.png',
          guildId: '1234567890123456789',
        }
      );
    });
  });

  describe('Error handling', () => {
    it('should handle 404 not found error', async () => {
      mockApiClient.requestNote.mockRejectedValue(new Error('404 Not Found'));

      const result = await service.execute(validInput);

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe(ErrorCode.NOT_FOUND);
    });

    it('should handle 401 unauthorized error', async () => {
      mockApiClient.requestNote.mockRejectedValue(new Error('401 Unauthorized'));

      const result = await service.execute(validInput);

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe(ErrorCode.UNAUTHORIZED);
    });

    it('should handle generic errors', async () => {
      mockApiClient.requestNote.mockRejectedValue(new Error('Network error'));

      const result = await service.execute(validInput);

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe(ErrorCode.API_ERROR);
    });
  });
});
