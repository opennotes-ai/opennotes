import { jest } from '@jest/globals';
import { ErrorCode } from '../../src/services/types.js';

function createMockRatingJSONAPIResponse(overrides: {
  id?: string;
  noteId?: string;
  userId?: string;
  helpfulnessLevel?: string;
} = {}): any {
  return {
    data: {
      type: 'ratings',
      id: overrides.id ?? '1',
      attributes: {
        note_id: overrides.noteId ?? '123',
        rater_participant_id: overrides.userId ?? 'user-123',
        helpfulness_level: overrides.helpfulnessLevel ?? 'HELPFUL',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    },
    jsonapi: { version: '1.1' },
  };
}

function createMockRatingListJSONAPIResponse(ratings: Array<{
  id: string;
  noteId: string;
  userId: string;
  helpfulnessLevel: string;
}> = []): any {
  return {
    data: ratings.map(r => ({
      type: 'ratings',
      id: r.id,
      attributes: {
        note_id: r.noteId,
        rater_participant_id: r.userId,
        helpfulness_level: r.helpfulnessLevel,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    })),
    jsonapi: { version: '1.1' },
  };
}

// Mock ApiError class
class MockApiError extends Error {
  errorId: string;
  constructor(
    message: string,
    public endpoint: string,
    public statusCode: number,
    public responseBody?: any,
    public requestBody?: any
  ) {
    super(message);
    this.name = 'ApiError';
    this.errorId = 'test-error-id';
  }

  getUserMessage(): string {
    return this.message;
  }
}

// Mock the errors module using unstable_mockModule
jest.unstable_mockModule('../../src/lib/errors.js', () => ({
  ApiError: MockApiError,
  generateErrorId: jest.fn(() => 'test-error-id'),
  ErrorWithContext: Error,
  formatErrorForUser: jest.fn(),
  extractErrorDetails: jest.fn(),
}));

// Mock the logger
jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: {
    info: jest.fn(),
    error: jest.fn(),
    warn: jest.fn(),
    debug: jest.fn(),
  },
}));

// Now import the services after mocking
const { RateNoteService } = await import('../../src/services/RateNoteService.js');
const { ApiClient } = await import('../../src/lib/api-client.js');
const ApiError = MockApiError;

type RateLimitResult = { allowed: boolean; remaining: number; resetAt: number };
type RateLimitError = { code: string; message: string };
type RateLimiterInterface = {
  check(userId: string): Promise<RateLimitResult>;
  reset(userId: string): Promise<void>;
  createError(resetAt: number): RateLimitError;
  cleanup?(): Promise<void>;
};

describe('RateNoteService', () => {
  let service: InstanceType<typeof RateNoteService>;
  let mockApiClient: jest.Mocked<InstanceType<typeof ApiClient>>;
  let mockRateLimiter: jest.Mocked<RateLimiterInterface>;

  beforeEach(() => {
    mockApiClient = {
      getRatingsForNote: jest.fn(),
      updateRating: jest.fn(),
      rateNote: jest.fn(),
    } as any;

    mockRateLimiter = {
      check: jest.fn(),
      createError: jest.fn(),
    } as any;

    service = new RateNoteService(mockApiClient, mockRateLimiter);
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe('Validation', () => {
    it('should return error for missing noteId', async () => {
      const result = await service.execute({
        noteId: '',
        userId: 'user-123',
        helpful: true,
      });

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe(ErrorCode.VALIDATION_ERROR);
      expect(result.error?.message).toBe('Note ID is required');
    });

    it('should return error for whitespace-only noteId', async () => {
      const result = await service.execute({
        noteId: '   ',
        userId: 'user-123',
        helpful: true,
      });

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe(ErrorCode.VALIDATION_ERROR);
      expect(result.error?.message).toBe('Note ID is required');
    });

    it('should return error for missing userId', async () => {
      const result = await service.execute({
        noteId: 'note-123',
        userId: '',
        helpful: true,
      });

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe(ErrorCode.VALIDATION_ERROR);
      expect(result.error?.message).toBe('User ID is required');
    });

    it('should return error for whitespace-only userId', async () => {
      const result = await service.execute({
        noteId: 'note-123',
        userId: '   ',
        helpful: true,
      });

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe(ErrorCode.VALIDATION_ERROR);
      expect(result.error?.message).toBe('User ID is required');
    });

    it('should return error for non-boolean helpful value', async () => {
      const result = await service.execute({
        noteId: 'note-123',
        userId: 'user-123',
        helpful: 'true' as any,
      });

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe(ErrorCode.VALIDATION_ERROR);
      expect(result.error?.message).toBe('Helpful rating must be a boolean');
    });

    it('should return error for undefined helpful value', async () => {
      const result = await service.execute({
        noteId: 'note-123',
        userId: 'user-123',
        helpful: undefined as any,
      });

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe(ErrorCode.VALIDATION_ERROR);
      expect(result.error?.message).toBe('Helpful rating must be a boolean');
    });
  });

  describe('Creating New Ratings', () => {
    beforeEach(() => {
      mockRateLimiter.check.mockResolvedValue({
        allowed: true,
        remaining: 5,
        resetAt: Date.now() + 60000,
      });
    });

    it('should create new rating when user has not rated before', async () => {
      mockApiClient.getRatingsForNote.mockResolvedValue(createMockRatingListJSONAPIResponse([]));
      const mockRating = createMockRatingJSONAPIResponse({
        id: '1',
        noteId: '123',
        userId: 'user-123',
        helpfulnessLevel: 'HELPFUL',
      });
      mockApiClient.rateNote.mockResolvedValue(mockRating);

      const result = await service.execute({
        noteId: '123',
        userId: 'user-123',
        helpful: true,
      });

      expect(result.success).toBe(true);
      expect(result.data?.rating).toEqual(mockRating);
      expect(mockApiClient.getRatingsForNote).toHaveBeenCalledWith('123');
      expect(mockApiClient.rateNote).toHaveBeenCalledWith(
        {
          noteId: '123',
          userId: 'user-123',
          helpful: true,
        },
        {
          userId: 'user-123',
          username: undefined,
          displayName: undefined,
          avatarUrl: undefined,
          guildId: undefined,
        }
      );
      expect(mockApiClient.updateRating).not.toHaveBeenCalled();
    });

    it('should create rating with helpful=false', async () => {
      mockApiClient.getRatingsForNote.mockResolvedValue(createMockRatingListJSONAPIResponse([]));
      const mockRating = createMockRatingJSONAPIResponse({
        id: '1',
        noteId: '123',
        userId: 'user-123',
        helpfulnessLevel: 'NOT_HELPFUL',
      });
      mockApiClient.rateNote.mockResolvedValue(mockRating);

      const result = await service.execute({
        noteId: '123',
        userId: 'user-123',
        helpful: false,
      });

      expect(result.success).toBe(true);
      expect(result.data?.rating.data.attributes.helpfulness_level).toBe('NOT_HELPFUL');
    });
  });

  describe('Updating Existing Ratings', () => {
    beforeEach(() => {
      mockRateLimiter.check.mockResolvedValue({
        allowed: true,
        remaining: 5,
        resetAt: Date.now() + 60000,
      });
    });

    it('should update existing rating when user has rated before', async () => {
      const existingRatingsResponse = createMockRatingListJSONAPIResponse([
        {
          id: '1',
          noteId: '123',
          userId: 'user-123',
          helpfulnessLevel: 'NOT_HELPFUL',
        },
      ]);
      mockApiClient.getRatingsForNote.mockResolvedValue(existingRatingsResponse);

      const updatedRating = createMockRatingJSONAPIResponse({
        id: '1',
        noteId: '123',
        userId: 'user-123',
        helpfulnessLevel: 'HELPFUL',
      });
      mockApiClient.updateRating.mockResolvedValue(updatedRating);

      const result = await service.execute({
        noteId: '123',
        userId: 'user-123',
        helpful: true,
      });

      expect(result.success).toBe(true);
      expect(result.data?.rating).toEqual(updatedRating);
      expect(mockApiClient.getRatingsForNote).toHaveBeenCalledWith('123');
      expect(mockApiClient.updateRating).toHaveBeenCalledWith('1', true, {
        userId: 'user-123',
        username: undefined,
        displayName: undefined,
        avatarUrl: undefined,
        guildId: undefined,
      });
      expect(mockApiClient.rateNote).not.toHaveBeenCalled();
    });

    it('should find existing rating among multiple ratings', async () => {
      const multipleRatingsResponse = createMockRatingListJSONAPIResponse([
        {
          id: '1',
          noteId: '123',
          userId: 'user-456',
          helpfulnessLevel: 'HELPFUL',
        },
        {
          id: '2',
          noteId: '123',
          userId: 'user-123',
          helpfulnessLevel: 'NOT_HELPFUL',
        },
        {
          id: '3',
          noteId: '123',
          userId: 'user-789',
          helpfulnessLevel: 'HELPFUL',
        },
      ]);
      mockApiClient.getRatingsForNote.mockResolvedValue(multipleRatingsResponse);

      const updatedRating = createMockRatingJSONAPIResponse({
        id: '2',
        noteId: '123',
        userId: 'user-123',
        helpfulnessLevel: 'HELPFUL',
      });
      mockApiClient.updateRating.mockResolvedValue(updatedRating);

      const result = await service.execute({
        noteId: '123',
        userId: 'user-123',
        helpful: true,
      });

      expect(result.success).toBe(true);
      expect(mockApiClient.updateRating).toHaveBeenCalledWith('2', true, {
        userId: 'user-123',
        username: undefined,
        displayName: undefined,
        avatarUrl: undefined,
        guildId: undefined,
      });
    });
  });

  describe('Error Handling', () => {
    beforeEach(() => {
      mockRateLimiter.check.mockResolvedValue({
        allowed: true,
        remaining: 5,
        resetAt: Date.now() + 60000,
      });
      mockApiClient.getRatingsForNote.mockResolvedValue(createMockRatingListJSONAPIResponse([]));
    });

    it('should handle 404 not found error', async () => {
      mockApiClient.rateNote.mockRejectedValue(new Error('404 Not Found'));

      const result = await service.execute({
        noteId: '123',
        userId: 'user-123',
        helpful: true,
      });

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe(ErrorCode.NOT_FOUND);
      expect(result.error?.message).toBe('Note not found');
    });

    it('should handle 401 unauthorized error', async () => {
      mockApiClient.rateNote.mockRejectedValue(new Error('401 Unauthorized'));

      const result = await service.execute({
        noteId: '123',
        userId: 'user-123',
        helpful: true,
      });

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe(ErrorCode.UNAUTHORIZED);
      expect(result.error?.message).toBe('Unauthorized to rate note');
    });

    it('should handle 403 forbidden error', async () => {
      mockApiClient.rateNote.mockRejectedValue(new Error('403 Forbidden'));

      const result = await service.execute({
        noteId: '123',
        userId: 'user-123',
        helpful: true,
      });

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe(ErrorCode.UNAUTHORIZED);
      expect(result.error?.message).toBe('Unauthorized to rate note');
    });

    it('should handle ApiError with proper mapping', async () => {
      const apiError = new ApiError(
        'Invalid rating',
        '/api/ratings',
        400,
        { detail: 'Invalid rating' }
      );
      mockApiClient.rateNote.mockRejectedValue(apiError);

      const result = await service.execute({
        noteId: '123',
        userId: 'user-123',
        helpful: true,
      });

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe(ErrorCode.VALIDATION_ERROR);
      expect(result.error?.details?.statusCode).toBe(400);
      expect(result.error?.details?.endpoint).toBe('/api/ratings');
    });

    it('should map status codes correctly', async () => {
      const testCases = [
        { statusCode: 400, expectedCode: ErrorCode.VALIDATION_ERROR },
        { statusCode: 401, expectedCode: ErrorCode.UNAUTHORIZED },
        { statusCode: 403, expectedCode: ErrorCode.UNAUTHORIZED },
        { statusCode: 404, expectedCode: ErrorCode.NOT_FOUND },
        { statusCode: 409, expectedCode: ErrorCode.CONFLICT },
        { statusCode: 429, expectedCode: ErrorCode.RATE_LIMIT },
        { statusCode: 500, expectedCode: ErrorCode.API_ERROR },
      ];

      for (const { statusCode, expectedCode } of testCases) {
        const apiError = new ApiError(
          'Error',
          '/api/ratings',
          statusCode,
          { detail: 'Error' }
        );
        mockApiClient.rateNote.mockRejectedValue(apiError);

        const result = await service.execute({
          noteId: '123',
          userId: 'user-123',
          helpful: true,
        });

        expect(result.error?.code).toBe(expectedCode);
      }
    });

    it('should handle generic errors', async () => {
      mockApiClient.rateNote.mockRejectedValue(new Error('Network error'));

      const result = await service.execute({
        noteId: '123',
        userId: 'user-123',
        helpful: true,
      });

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe(ErrorCode.API_ERROR);
      expect(result.error?.message).toBe('Failed to submit rating. Please try again later.');
    });

    it('should handle non-Error exceptions', async () => {
      mockApiClient.rateNote.mockRejectedValue('String error');

      const result = await service.execute({
        noteId: '123',
        userId: 'user-123',
        helpful: true,
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

    it('should handle string noteId correctly', async () => {
      mockApiClient.getRatingsForNote.mockResolvedValue(createMockRatingListJSONAPIResponse([]));
      mockApiClient.rateNote.mockResolvedValue(createMockRatingJSONAPIResponse({
        id: '1',
        noteId: '999',
        userId: 'user-123',
        helpfulnessLevel: 'HELPFUL',
      }));

      const result = await service.execute({
        noteId: '999',
        userId: 'user-123',
        helpful: true,
      });

      expect(result.success).toBe(true);
      expect(mockApiClient.getRatingsForNote).toHaveBeenCalledWith('999');
    });

    it('should handle empty ratings array', async () => {
      mockApiClient.getRatingsForNote.mockResolvedValue(createMockRatingListJSONAPIResponse([]));
      mockApiClient.rateNote.mockResolvedValue(createMockRatingJSONAPIResponse({
        id: '1',
        noteId: '123',
        userId: 'user-123',
        helpfulnessLevel: 'HELPFUL',
      }));

      const result = await service.execute({
        noteId: '123',
        userId: 'user-123',
        helpful: true,
      });

      expect(result.success).toBe(true);
      expect(mockApiClient.rateNote).toHaveBeenCalled();
    });
  });
});
