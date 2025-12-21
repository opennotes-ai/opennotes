import { jest } from '@jest/globals';
import type {
  NoteScoreJSONAPIResponse,
  TopNotesJSONAPIResponse,
  BatchScoreJSONAPIResponse,
  ScoringStatusJSONAPIResponse,
} from '../../src/services/ScoringService.js';
import { TEST_SCORE_ABOVE_THRESHOLD } from '../test-constants.js';
import {
  createMockNoteScoreJSONAPIResponse,
  createMockTopNotesJSONAPIResponse,
  createMockScoringStatusJSONAPIResponse,
  createMockBatchScoreJSONAPIResponse,
} from '../utils/service-mocks.js';

const TEST_UUID_1 = '550e8400-e29b-41d4-a716-446655440001';
const TEST_UUID_2 = '550e8400-e29b-41d4-a716-446655440002';

const mockCache = {
  get: jest.fn<(key: string) => unknown>(),
  set: jest.fn<(key: string, value: unknown, ttl?: number) => void>(),
  delete: jest.fn<(key: string) => void>(),
  start: jest.fn<() => void>(),
  stop: jest.fn<() => void>(),
};

const mockApiClient = {
  getNoteScore: jest.fn<(noteId: string) => Promise<NoteScoreJSONAPIResponse>>(),
  getBatchNoteScores: jest.fn<(noteIds: string[]) => Promise<BatchScoreJSONAPIResponse>>(),
  getTopNotes: jest.fn<(limit?: number, minConfidence?: string, tier?: number) => Promise<TopNotesJSONAPIResponse>>(),
  getScoringStatus: jest.fn<() => Promise<ScoringStatusJSONAPIResponse>>(),
};

jest.unstable_mockModule('../../src/cache.js', () => ({
  cache: mockCache,
}));

jest.unstable_mockModule('../../src/lib/api-client.js', () => ({
  ApiClient: jest.fn().mockImplementation(() => mockApiClient),
}));

const { ScoringService } = await import('../../src/services/ScoringService.js');

describe('ScoringService', () => {
  let scoringService: InstanceType<typeof ScoringService>;

  beforeEach(() => {
    scoringService = new ScoringService(mockApiClient as any);
    jest.clearAllMocks();
  });

  describe('getNoteScore', () => {
    const mockScoreResponse = createMockNoteScoreJSONAPIResponse({
      noteId: TEST_UUID_1,
      score: 0.75,
      confidence: 'standard',
      algorithm: 'MFCoreScorer',
      ratingCount: 10,
      tier: 2,
      tierName: 'Tier 2 (1k-5k notes)',
    });

    it('should return cached score if available', async () => {
      mockCache.get.mockReturnValue(mockScoreResponse);

      const result = await scoringService.getNoteScore(TEST_UUID_1);

      expect(result.success).toBe(true);
      expect(result.data).toEqual(mockScoreResponse);
      expect(mockCache.get).toHaveBeenCalledWith(`score:${TEST_UUID_1}`);
      expect(mockApiClient.getNoteScore).not.toHaveBeenCalled();
    });

    it('should fetch from API and cache on cache miss', async () => {
      mockCache.get.mockReturnValue(null);
      mockApiClient.getNoteScore.mockResolvedValue(mockScoreResponse);

      const result = await scoringService.getNoteScore(TEST_UUID_1);

      expect(result.success).toBe(true);
      expect(result.data).toEqual(mockScoreResponse);
      expect(mockApiClient.getNoteScore).toHaveBeenCalledWith(TEST_UUID_1);
      expect(mockCache.set).toHaveBeenCalledWith(`score:${TEST_UUID_1}`, mockScoreResponse, 300);
    });

    it('should handle invalid note ID format', async () => {
      const result = await scoringService.getNoteScore('invalid');

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe('VALIDATION_ERROR');
      expect(result.error?.message).toBe('Invalid note ID format');
    });

    it('should handle 404 not found', async () => {
      mockCache.get.mockReturnValue(null);
      mockApiClient.getNoteScore.mockRejectedValue({ statusCode: 404 });

      const result = await scoringService.getNoteScore(TEST_UUID_1);

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe('NOT_FOUND');
      expect(result.error?.statusCode).toBe(404);
    });

    it('should handle 202 score pending', async () => {
      mockCache.get.mockReturnValue(null);
      mockApiClient.getNoteScore.mockRejectedValue({ statusCode: 202 });

      const result = await scoringService.getNoteScore(TEST_UUID_1);

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe('SCORE_PENDING');
      expect(result.error?.statusCode).toBe(202);
    });

    it('should handle 503 service unavailable', async () => {
      mockCache.get.mockReturnValue(null);
      mockApiClient.getNoteScore.mockRejectedValue({ statusCode: 503 });

      const result = await scoringService.getNoteScore(TEST_UUID_1);

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe('SERVICE_UNAVAILABLE');
      expect(result.error?.statusCode).toBe(503);
    });
  });

  describe('getTopNotes', () => {
    const mockTopNotesResponse = createMockTopNotesJSONAPIResponse({
      notes: [
        { noteId: TEST_UUID_1, score: TEST_SCORE_ABOVE_THRESHOLD, confidence: 'standard', tier: 2, ratingCount: 15 },
        { noteId: TEST_UUID_2, score: 0.78, confidence: 'standard', tier: 2, ratingCount: 12 },
      ],
      totalCount: 50,
      currentTier: 2,
      filtersApplied: { min_confidence: 'standard', tier: 2 },
    });

    it('should fetch top notes with default params', async () => {
      mockApiClient.getTopNotes.mockResolvedValue(mockTopNotesResponse);

      const result = await scoringService.getTopNotes();

      expect(result.success).toBe(true);
      expect(result.data).toEqual(mockTopNotesResponse);
      expect(mockApiClient.getTopNotes).toHaveBeenCalledWith(10, undefined, undefined);
    });

    it('should fetch top notes with custom params', async () => {
      mockApiClient.getTopNotes.mockResolvedValue(mockTopNotesResponse);

      const result = await scoringService.getTopNotes({
        limit: 20,
        minConfidence: 'standard',
        tier: 2,
      });

      expect(result.success).toBe(true);
      expect(result.data).toEqual(mockTopNotesResponse);
      expect(mockApiClient.getTopNotes).toHaveBeenCalledWith(20, 'standard', 2);
    });

    it('should handle 503 service unavailable', async () => {
      mockApiClient.getTopNotes.mockRejectedValue({ statusCode: 503 });

      const result = await scoringService.getTopNotes();

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe('SERVICE_UNAVAILABLE');
    });
  });

  describe('getScoringStatus', () => {
    const mockStatusResponse = createMockScoringStatusJSONAPIResponse({
      noteCount: 2500,
      tierLevel: 2,
      tierName: 'Tier 2 (1k-5k notes)',
      dataConfidence: 'medium',
    });

    it('should return cached status if available', async () => {
      mockCache.get.mockReturnValue(mockStatusResponse);

      const result = await scoringService.getScoringStatus();

      expect(result.success).toBe(true);
      expect(result.data).toEqual(mockStatusResponse);
      expect(mockCache.get).toHaveBeenCalledWith('scoring:status');
      expect(mockApiClient.getScoringStatus).not.toHaveBeenCalled();
    });

    it('should fetch from API and cache on cache miss', async () => {
      mockCache.get.mockReturnValue(null);
      mockApiClient.getScoringStatus.mockResolvedValue(mockStatusResponse);

      const result = await scoringService.getScoringStatus();

      expect(result.success).toBe(true);
      expect(result.data).toEqual(mockStatusResponse);
      expect(mockApiClient.getScoringStatus).toHaveBeenCalled();
      expect(mockCache.set).toHaveBeenCalledWith('scoring:status', mockStatusResponse, 60);
    });
  });

  describe('getBatchNoteScores', () => {
    const mockBatchResponse = createMockBatchScoreJSONAPIResponse({
      scores: [
        { noteId: TEST_UUID_1, score: 0.75, confidence: 'standard', tier: 2, ratingCount: 10 },
        { noteId: TEST_UUID_2, score: 0.82, confidence: 'standard', tier: 2, ratingCount: 8 },
      ],
      notFound: [],
      totalRequested: 2,
    });

    it('should fetch batch scores from API when not cached', async () => {
      mockCache.get.mockReturnValue(null);
      mockApiClient.getBatchNoteScores.mockResolvedValue(mockBatchResponse);

      const result = await scoringService.getBatchNoteScores([TEST_UUID_1, TEST_UUID_2]);

      expect(result.success).toBe(true);
      expect(result.data?.data.length).toBe(2);
      expect(result.data?.meta?.total_found).toBe(2);
      expect(mockApiClient.getBatchNoteScores).toHaveBeenCalledWith([TEST_UUID_1, TEST_UUID_2]);
      expect(mockCache.set).toHaveBeenCalledTimes(2);
    });

    it('should use cached scores and only fetch uncached ones', async () => {
      const cachedScore = createMockNoteScoreJSONAPIResponse({
        noteId: TEST_UUID_1,
        score: 0.75,
        confidence: 'standard',
        tier: 2,
        ratingCount: 10,
      });
      mockCache.get.mockImplementation((key: string) => {
        if (key === `score:${TEST_UUID_1}`) return cachedScore;
        return null;
      });
      const partialResponse = createMockBatchScoreJSONAPIResponse({
        scores: [{ noteId: TEST_UUID_2, score: 0.82, confidence: 'standard', tier: 2, ratingCount: 8 }],
        notFound: [],
        totalRequested: 1,
      });
      mockApiClient.getBatchNoteScores.mockResolvedValue(partialResponse);

      const result = await scoringService.getBatchNoteScores([TEST_UUID_1, TEST_UUID_2]);

      expect(result.success).toBe(true);
      expect(result.data?.data.length).toBe(2);
      expect(mockApiClient.getBatchNoteScores).toHaveBeenCalledWith([TEST_UUID_2]);
    });

    it('should handle not found notes', async () => {
      mockCache.get.mockReturnValue(null);
      const responseWithNotFound = createMockBatchScoreJSONAPIResponse({
        scores: [{ noteId: TEST_UUID_1, score: 0.75, confidence: 'standard', tier: 2, ratingCount: 10 }],
        notFound: [TEST_UUID_2],
        totalRequested: 2,
      });
      mockApiClient.getBatchNoteScores.mockResolvedValue(responseWithNotFound);

      const result = await scoringService.getBatchNoteScores([TEST_UUID_1, TEST_UUID_2]);

      expect(result.success).toBe(true);
      expect(result.data?.data.length).toBe(1);
      expect(result.data?.meta?.not_found).toEqual([TEST_UUID_2]);
    });

    it('should handle invalid note ID format', async () => {
      const result = await scoringService.getBatchNoteScores(['invalid']);

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe('VALIDATION_ERROR');
      expect(result.error?.message).toContain('Invalid note ID format');
    });

    it('should handle service unavailable error', async () => {
      mockCache.get.mockReturnValue(null);
      mockApiClient.getBatchNoteScores.mockRejectedValue({ statusCode: 503 });

      const result = await scoringService.getBatchNoteScores([TEST_UUID_1, TEST_UUID_2]);

      expect(result.success).toBe(false);
      expect(result.error?.code).toBe('SERVICE_UNAVAILABLE');
      expect(result.error?.statusCode).toBe(503);
    });

    it('should handle all notes from cache', async () => {
      const cachedScore1 = createMockNoteScoreJSONAPIResponse({
        noteId: TEST_UUID_1,
        score: 0.75,
        confidence: 'standard',
        tier: 2,
        ratingCount: 10,
      });
      const cachedScore2 = createMockNoteScoreJSONAPIResponse({
        noteId: TEST_UUID_2,
        score: 0.82,
        confidence: 'standard',
        tier: 2,
        ratingCount: 8,
      });
      mockCache.get.mockImplementation((key: string) => {
        if (key === `score:${TEST_UUID_1}`) return cachedScore1;
        if (key === `score:${TEST_UUID_2}`) return cachedScore2;
        return null;
      });

      const result = await scoringService.getBatchNoteScores([TEST_UUID_1, TEST_UUID_2]);

      expect(result.success).toBe(true);
      expect(result.data?.data.length).toBe(2);
      expect(mockApiClient.getBatchNoteScores).not.toHaveBeenCalled();
    });
  });

  describe('cache invalidation', () => {
    it('should invalidate note score cache', () => {
      scoringService.invalidateNoteScoreCache(TEST_UUID_1);

      expect(mockCache.delete).toHaveBeenCalledWith(`score:${TEST_UUID_1}`);
    });

    it('should invalidate scoring status cache', () => {
      scoringService.invalidateScoringStatusCache();

      expect(mockCache.delete).toHaveBeenCalledWith('scoring:status');
    });
  });
});
