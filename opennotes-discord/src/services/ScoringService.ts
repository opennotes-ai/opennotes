import {
  ApiClient,
  NoteScoreJSONAPIResponse,
  TopNotesJSONAPIResponse,
  ScoringStatusJSONAPIResponse,
  BatchScoreJSONAPIResponse,
  ScoreConfidence,
  NoteScoreAttributes,
} from '../lib/api-client.js';
import { cache } from '../cache.js';
import { logger } from '../logger.js';
import { getErrorMessage, getStatusCode, hasStatusCode } from '../utils/error-handlers.js';
import { isValidUUID } from '../lib/validation.js';

export type {
  NoteScoreJSONAPIResponse,
  TopNotesJSONAPIResponse,
  ScoringStatusJSONAPIResponse,
  BatchScoreJSONAPIResponse,
  ScoreConfidence,
  NoteScoreAttributes,
};

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

  async getNoteScore(noteId: string): Promise<ScoringServiceResult<NoteScoreJSONAPIResponse>> {
    const noteIdNum = this.validateNoteId(noteId);
    if (typeof noteIdNum === 'object') {
      return noteIdNum;
    }

    const cacheKey = `score:${noteId}`;

    try {
      const cached = await cache.get<NoteScoreJSONAPIResponse>(cacheKey);
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

  async getBatchNoteScores(noteIds: string[]): Promise<ScoringServiceResult<BatchScoreJSONAPIResponse>> {
    const validatedIds = this.validateBatchNoteIds(noteIds);
    if (!validatedIds.success) {
      return validatedIds;
    }

    try {
      logger.debug('Fetching batch note scores from API', { count: noteIds.length });

      const cachedScores: Map<string, NoteScoreJSONAPIResponse> = new Map();
      const uncachedNoteIds: string[] = [];

      for (const noteId of noteIds) {
        const cacheKey = `score:${noteId}`;
        const cached = await cache.get<NoteScoreJSONAPIResponse>(cacheKey);
        if (cached) {
          cachedScores.set(noteId, cached);
          logger.debug('Cache hit for note score in batch', { noteId });
        } else {
          uncachedNoteIds.push(noteId);
        }
      }

      let apiResponse: BatchScoreJSONAPIResponse | null = null;

      if (uncachedNoteIds.length > 0) {
        apiResponse = await this.apiClient.getBatchNoteScores(uncachedNoteIds);

        for (const resource of apiResponse.data) {
          const cacheKey = `score:${resource.id}`;
          const singleResponse: NoteScoreJSONAPIResponse = {
            data: resource,
            jsonapi: apiResponse.jsonapi,
          };
          void cache.set(cacheKey, singleResponse, this.CACHE_TTL);
        }
      }

      if (cachedScores.size > 0 && apiResponse) {
        const mergedData = [
          ...Array.from(cachedScores.values()).map(r => r.data),
          ...apiResponse.data,
        ];
        const mergedResponse: BatchScoreJSONAPIResponse = {
          data: mergedData,
          jsonapi: apiResponse.jsonapi,
          meta: {
            total_requested: noteIds.length,
            total_found: mergedData.length,
            not_found: apiResponse.meta?.not_found ?? [],
          },
        };

        logger.debug('Batch note scores retrieved successfully', {
          totalRequested: noteIds.length,
          fromCache: cachedScores.size,
          fromAPI: apiResponse.data.length,
          notFound: apiResponse.meta?.not_found?.length ?? 0,
        });

        return { success: true, data: mergedResponse };
      } else if (cachedScores.size > 0) {
        const cachedData = Array.from(cachedScores.values()).map(r => r.data);
        const mergedResponse: BatchScoreJSONAPIResponse = {
          data: cachedData,
          jsonapi: { version: '1.0' },
          meta: {
            total_requested: noteIds.length,
            total_found: cachedData.length,
            not_found: [],
          },
        };

        logger.debug('Batch note scores retrieved from cache', {
          totalRequested: noteIds.length,
          fromCache: cachedScores.size,
        });

        return { success: true, data: mergedResponse };
      } else if (apiResponse) {
        logger.debug('Batch note scores retrieved successfully', {
          totalRequested: noteIds.length,
          fromAPI: apiResponse.data.length,
          notFound: apiResponse.meta?.not_found?.length ?? 0,
        });

        return { success: true, data: apiResponse };
      }

      return {
        success: true,
        data: {
          data: [],
          jsonapi: { version: '1.0' },
          meta: {
            total_requested: noteIds.length,
            total_found: 0,
            not_found: noteIds,
          },
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

  async getTopNotes(params: TopNotesParams = {}): Promise<ScoringServiceResult<TopNotesJSONAPIResponse>> {
    try {
      const { limit = 10, minConfidence, tier } = params;

      logger.debug('Fetching top notes', { limit, minConfidence, tier });

      const response = await this.apiClient.getTopNotes(limit, minConfidence, tier);

      logger.debug('Top notes retrieved successfully', {
        count: response.data.length,
        totalCount: response.meta?.total_count,
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

  async getScoringStatus(): Promise<ScoringServiceResult<ScoringStatusJSONAPIResponse>> {
    const cacheKey = 'scoring:status';

    try {
      const cached = await cache.get<ScoringStatusJSONAPIResponse>(cacheKey);
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

  private validateBatchNoteIds(noteIds: string[]): ScoringServiceResult<BatchScoreJSONAPIResponse> | { success: true } {
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
