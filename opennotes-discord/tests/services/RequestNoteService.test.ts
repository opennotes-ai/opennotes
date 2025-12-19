import { jest } from '@jest/globals';
import { ErrorCode } from '../../src/services/types.js';

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: {
    info: jest.fn(),
    error: jest.fn(),
    warn: jest.fn(),
    debug: jest.fn(),
  },
}));

const mockResolveCommunityServerId = jest.fn<(guildId: string) => Promise<string>>();
jest.unstable_mockModule('../../src/lib/community-server-resolver.js', () => ({
  resolveCommunityServerId: mockResolveCommunityServerId,
}));

const { RequestNoteService } = await import('../../src/services/RequestNoteService.js');
const { ApiClient } = await import('../../src/lib/api-client.js');

type RateLimitResult = { allowed: boolean; remaining: number; resetAt: number };
type RateLimitError = { code: string; message: string };
type RateLimiterInterface = {
  check(userId: string): Promise<RateLimitResult>;
  reset(userId: string): Promise<void>;
  createError(resetAt: number): RateLimitError;
  cleanup?(): Promise<void>;
};

describe('RequestNoteService', () => {
  let service: InstanceType<typeof RequestNoteService>;
  let mockApiClient: jest.Mocked<InstanceType<typeof ApiClient>>;
  let mockRateLimiter: jest.Mocked<RateLimiterInterface>;

  const validInput = {
    messageId: 'msg-123',
    userId: 'user-123',
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

    mockApiClient = {
      requestNote: jest.fn(),
    } as any;

    mockRateLimiter = {
      check: jest.fn(),
      reset: jest.fn(),
      createError: jest.fn(),
    } as any;

    mockRateLimiter.check.mockResolvedValue({
      allowed: true,
      remaining: 5,
      resetAt: Date.now() + 60000,
    });

    mockResolveCommunityServerId.mockResolvedValue('f47ac10b-58cc-4372-a567-0e02b2c3d479');

    service = new RequestNoteService(mockApiClient, mockRateLimiter);
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

  describe('Community Server ID Resolution', () => {
    it('should call resolveCommunityServerId with the guild ID', async () => {
      mockApiClient.requestNote.mockResolvedValue(undefined);

      await service.execute(validInput);

      expect(mockResolveCommunityServerId).toHaveBeenCalledWith('1234567890123456789');
    });

    it('should pass the resolved UUID to apiClient.requestNote', async () => {
      mockResolveCommunityServerId.mockResolvedValue('f47ac10b-58cc-4372-a567-0e02b2c3d479');
      mockApiClient.requestNote.mockResolvedValue(undefined);

      await service.execute(validInput);

      expect(mockApiClient.requestNote).toHaveBeenCalledWith(
        expect.objectContaining({
          community_server_id: 'f47ac10b-58cc-4372-a567-0e02b2c3d479',
        }),
        expect.any(Object)
      );
    });

    it('should handle resolver errors gracefully', async () => {
      mockResolveCommunityServerId.mockRejectedValue(new Error('Community server not found'));

      const result = await service.execute(validInput);

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe(ErrorCode.API_ERROR);
    });

    it('should handle 404 resolver errors as NOT_FOUND', async () => {
      mockResolveCommunityServerId.mockRejectedValue(new Error('404 Not Found'));

      const result = await service.execute(validInput);

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe(ErrorCode.NOT_FOUND);
      expect(result.error?.message).toContain('not found');
    });
  });

  describe('Successful request', () => {
    it('should request note successfully with resolved UUID', async () => {
      mockResolveCommunityServerId.mockResolvedValue('resolved-uuid-123');
      mockApiClient.requestNote.mockResolvedValue(undefined);

      const result = await service.execute(validInput);

      expect(result.success).toBe(true);
      expect(mockApiClient.requestNote).toHaveBeenCalledWith(
        {
          messageId: 'msg-123',
          userId: 'user-123',
          community_server_id: 'resolved-uuid-123',
          discord_channel_id: 'channel-123',
          reason: 'Test reason',
          originalMessageContent: 'Test content',
          attachmentUrl: undefined,
          attachmentType: undefined,
          attachmentMetadata: undefined,
          embeddedImageUrl: undefined,
        },
        {
          userId: 'user-123',
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
