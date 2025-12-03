import { ApiClient } from '../lib/api-client.js';
import { cache } from '../cache.js';
import type { components } from '../lib/generated-types.js';
import { logger } from '../logger.js';
import { getErrorMessage, getStatusCode, hasStatusCode } from '../utils/error-handlers.js';
import { isValidUUID } from '../lib/validation.js';

export type NoteScoreResponse = components['schemas']['NoteScoreResponse'];
export type TopNotesResponse = components['schemas']['TopNotesResponse'];
export type ScoringStatusResponse = components['schemas']['ScoringStatusResponse'];
export type ScoreConfidence = components['schemas']['ScoreConfidence'];
export type BatchScoreResponse = components['schemas']['BatchScoreResponse'];

export interface TopNotesParams {
  limit?: number;
  minConfidence?: ScoreConfidence;
  tier?: number;
}

export interface ScoringServiceResult<T> {
  success: boolean;
  data?: T;
  error?: {
    code: string;
    message: string;
    statusCode?: number;
  };
}

export class ScoringService {
  private apiClient: ApiClient;
  private readonly CACHE_TTL = 300;

  constructor(apiClient: ApiClient) {
    this.apiClient = apiClient;
  }

  async getNoteScore(noteId: string): Promise<ScoringServiceResult<NoteScoreResponse>> {
    const noteIdNum = this.validateNoteId(noteId);
    if (typeof noteIdNum === 'object') {
      return noteIdNum;
    }

    const cacheKey = `score:${noteId}`;

    try {
      const cached = await cache.get<NoteScoreResponse>(cacheKey);
      if (cached) {
        logger.debug('Cache hit for note score', { noteId });
        return { success: true, data: cached };
      }

      logger.debug('Fetching note score from API', { noteId });

      const response = await this.apiClient.getNoteScore(noteIdNum);

      void cache.set(cacheKey, response, this.CACHE_TTL);

      logger.debug('Note score retrieved successfully', { noteId });

      return { success: true, data: response };
    } catch (error: unknown) {
      logger.error('Failed to get note score', {
        noteId,
        error: getErrorMessage(error),
        statusCode: getStatusCode(error),
      });

      if (hasStatusCode(error) && error.statusCode === 404) {
        return {
          success: false,
          error: {
            code: 'NOT_FOUND',
            message: 'Note not found or score not available',
            statusCode: 404,
          },
        };
      }

      if (hasStatusCode(error) && error.statusCode === 202) {
        return {
          success: false,
          error: {
            code: 'SCORE_PENDING',
            message: 'Score calculation is in progress. Please try again in a moment.',
            statusCode: 202,
          },
        };
      }

      if (hasStatusCode(error) && error.statusCode === 503) {
        return {
          success: false,
          error: {
            code: 'SERVICE_UNAVAILABLE',
            message: 'Scoring system is temporarily unavailable. Please try again later.',
            statusCode: 503,
          },
        };
      }

      return {
        success: false,
        error: {
          code: 'API_ERROR',
          message: 'Failed to retrieve note score',
          statusCode: getStatusCode(error),
        },
      };
    }
  }

  async getBatchNoteScores(noteIds: string[]): Promise<ScoringServiceResult<BatchScoreResponse>> {
    const validatedIds = this.validateBatchNoteIds(noteIds);
    if (!validatedIds.success) {
      return validatedIds;
    }

    try {
      logger.debug('Fetching batch note scores from API', { count: noteIds.length });

      // Check cache for any existing scores
      const cachedScores: Record<string, NoteScoreResponse> = {};
      const uncachedNoteIds: string[] = [];

      for (const noteId of noteIds) {
        const cacheKey = `score:${noteId}`;
        const cached = await cache.get<NoteScoreResponse>(cacheKey);
        if (cached) {
          cachedScores[noteId] = cached;
          logger.debug('Cache hit for note score in batch', { noteId });
        } else {
          uncachedNoteIds.push(noteId);
        }
      }

      // Fetch uncached scores from API if any
      let apiScores: Record<string, NoteScoreResponse> = {};
      let notFound: string[] = [];

      if (uncachedNoteIds.length > 0) {
        const response = await this.apiClient.getBatchNoteScores(uncachedNoteIds);
        apiScores = response.scores;
        notFound = response.not_found ?? [];

        // Cache the newly fetched scores
        for (const [noteId, score] of Object.entries(apiScores)) {
          const cacheKey = `score:${noteId}`;
          void cache.set(cacheKey, score, this.CACHE_TTL);
        }
      }

      // Merge cached and API scores
      const allScores = { ...cachedScores, ...apiScores };

      logger.debug('Batch note scores retrieved successfully', {
        totalRequested: noteIds.length,
        fromCache: Object.keys(cachedScores).length,
        fromAPI: Object.keys(apiScores).length,
        notFound: notFound.length,
      });

      return {
        success: true,
        data: {
          scores: allScores,
          not_found: notFound,
          total_requested: noteIds.length,
          total_found: Object.keys(allScores).length,
        },
      };
    } catch (error: unknown) {
      logger.error('Failed to get batch note scores', {
        count: noteIds.length,
        error: getErrorMessage(error),
        statusCode: getStatusCode(error),
      });

      if (hasStatusCode(error) && error.statusCode === 503) {
        return {
          success: false,
          error: {
            code: 'SERVICE_UNAVAILABLE',
            message: 'Scoring system is temporarily unavailable. Please try again later.',
            statusCode: 503,
          },
        };
      }

      return {
        success: false,
        error: {
          code: 'API_ERROR',
          message: 'Failed to retrieve batch note scores',
          statusCode: getStatusCode(error),
        },
      };
    }
  }

  async getTopNotes(params: TopNotesParams = {}): Promise<ScoringServiceResult<TopNotesResponse>> {
    try {
      const { limit = 10, minConfidence, tier } = params;

      logger.debug('Fetching top notes', { limit, minConfidence, tier });

      const response = await this.apiClient.getTopNotes(limit, minConfidence, tier);

      logger.debug('Top notes retrieved successfully', {
        count: response.notes.length,
        totalCount: response.total_count,
      });

      return { success: true, data: response };
    } catch (error: unknown) {
      logger.error('Failed to get top notes', {
        params,
        error: getErrorMessage(error),
        statusCode: getStatusCode(error),
      });

      if (hasStatusCode(error) && error.statusCode === 503) {
        return {
          success: false,
          error: {
            code: 'SERVICE_UNAVAILABLE',
            message: 'Scoring system is temporarily unavailable. Please try again later.',
            statusCode: 503,
          },
        };
      }

      return {
        success: false,
        error: {
          code: 'API_ERROR',
          message: 'Failed to retrieve top notes',
          statusCode: getStatusCode(error),
        },
      };
    }
  }

  async getScoringStatus(): Promise<ScoringServiceResult<ScoringStatusResponse>> {
    const cacheKey = 'scoring:status';

    try {
      const cached = await cache.get<ScoringStatusResponse>(cacheKey);
      if (cached) {
        logger.debug('Cache hit for scoring status');
        return { success: true, data: cached };
      }

      logger.debug('Fetching scoring status from API');

      const response = await this.apiClient.getScoringStatus();

      void cache.set(cacheKey, response, 60);

      logger.debug('Scoring status retrieved successfully');

      return { success: true, data: response };
    } catch (error: unknown) {
      logger.error('Failed to get scoring status', {
        error: getErrorMessage(error),
        statusCode: getStatusCode(error),
      });

      return {
        success: false,
        error: {
          code: 'API_ERROR',
          message: 'Failed to retrieve scoring status',
          statusCode: getStatusCode(error),
        },
      };
    }
  }

  invalidateNoteScoreCache(noteId: string): void {
    const cacheKey = `score:${noteId}`;
    void cache.delete(cacheKey);
    logger.debug('Invalidated note score cache', { noteId });
  }

  invalidateScoringStatusCache(): void {
    void cache.delete('scoring:status');
    logger.debug('Invalidated scoring status cache');
  }

  private validateNoteId(noteId: string): string | ScoringServiceResult<never> {
    if (!isValidUUID(noteId)) {
      return {
        success: false,
        error: {
          code: 'VALIDATION_ERROR',
          message: 'Invalid note ID format',
        },
      };
    }
    return noteId;
  }

  private validateBatchNoteIds(noteIds: string[]): ScoringServiceResult<BatchScoreResponse> | { success: true } {
    for (const noteId of noteIds) {
      if (!isValidUUID(noteId)) {
        return {
          success: false,
          error: {
            code: 'VALIDATION_ERROR',
            message: 'Invalid note ID format',
          },
        };
      }
    }
    return { success: true };
  }
}
