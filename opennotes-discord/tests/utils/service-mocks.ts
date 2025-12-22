import { jest } from '@jest/globals';
import {
  ServiceResult,
  StatusResult,
  WriteNoteResult,
  ViewNotesResult,
  RateNoteResult,
  ErrorCode,
} from '../../src/services/types.js';
import type { Note } from '../../src/lib/types.js';
import type { RatingJSONAPIResponse } from '../../src/lib/api-client.js';
import {
  createMockLogger,
  createMockCache,
  createMockInteraction,
  createMockFetchResponse,
  createMockNote as createSharedMockNote,
} from '@opennotes/test-utils';

export function createMockApiClient() {
  return {
    healthCheck: jest.fn<() => Promise<{ status: string; version: string }>>(),
    createNote: jest.fn<(req: any) => Promise<Note>>(),
    getNotes: jest.fn<(messageId: string) => Promise<Note[]>>(),
    rateNote: jest.fn<(req: any) => Promise<RatingJSONAPIResponse>>(),
    scoreNotes: jest.fn<(req: any) => Promise<any>>(),
    createNoteRequest: jest.fn<(req: any) => Promise<any>>(),
  };
}

export { createMockLogger, createMockCache, createMockInteraction, createMockFetchResponse };

export function createMockStatusService() {
  return {
    execute: jest.fn<(guilds?: number) => Promise<ServiceResult<StatusResult>>>(),
  };
}

export function createMockWriteNoteService() {
  return {
    execute: jest.fn<(input: any) => Promise<ServiceResult<WriteNoteResult>>>(),
  };
}

export function createMockViewNotesService() {
  return {
    execute: jest.fn<(input: any) => Promise<ServiceResult<ViewNotesResult>>>(),
  };
}

export function createMockRateNoteService() {
  return {
    execute: jest.fn<(input: any) => Promise<ServiceResult<RateNoteResult>>>(),
  };
}

export function createMockRequestNoteService() {
  return {
    execute: jest.fn<(input: any) => Promise<ServiceResult<void>>>(),
  };
}

export function createMockServiceProvider(overrides?: {
  statusService?: ReturnType<typeof createMockStatusService>;
  writeNoteService?: ReturnType<typeof createMockWriteNoteService>;
  viewNotesService?: ReturnType<typeof createMockViewNotesService>;
  rateNoteService?: ReturnType<typeof createMockRateNoteService>;
  requestNoteService?: ReturnType<typeof createMockRequestNoteService>;
}) {
  const mockStatusService = overrides?.statusService ?? createMockStatusService();
  const mockWriteNoteService = overrides?.writeNoteService ?? createMockWriteNoteService();
  const mockViewNotesService = overrides?.viewNotesService ?? createMockViewNotesService();
  const mockRateNoteService = overrides?.rateNoteService ?? createMockRateNoteService();
  const mockRequestNoteService = overrides?.requestNoteService ?? createMockRequestNoteService();

  return {
    getStatusService: jest.fn(() => mockStatusService),
    getWriteNoteService: jest.fn(() => mockWriteNoteService),
    getViewNotesService: jest.fn(() => mockViewNotesService),
    getRateNoteService: jest.fn(() => mockRateNoteService),
    getRequestNoteService: jest.fn(() => mockRequestNoteService),
    services: {
      status: mockStatusService,
      writeNote: mockWriteNoteService,
      viewNotes: mockViewNotesService,
      rateNote: mockRateNoteService,
      requestNote: mockRequestNoteService,
    },
  };
}

export function createSuccessResult<T>(data: T): ServiceResult<T> {
  return {
    success: true,
    data,
  };
}

export function createErrorResult<T>(code: ErrorCode, message: string, details?: any): ServiceResult<T> {
  return {
    success: false,
    error: {
      code,
      message,
      details,
    },
  };
}

export function createMockNote(overrides?: Partial<Note>): Note {
  return createSharedMockNote(overrides) as Note;
}

export function createMockRatingJSONAPIResponse(overrides: {
  id?: string;
  noteId?: string;
  userId?: string;
  helpfulnessLevel?: 'HELPFUL' | 'NOT_HELPFUL';
} = {}): RatingJSONAPIResponse {
  return {
    data: {
      type: 'ratings',
      id: overrides.id ?? 'rating-1',
      attributes: {
        note_id: overrides.noteId ?? 'note-123',
        rater_participant_id: overrides.userId ?? 'user-123',
        helpfulness_level: overrides.helpfulnessLevel ?? 'HELPFUL',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    },
    jsonapi: { version: '1.1' },
  };
}

export function createMockStatusResult(overrides?: Partial<StatusResult>): StatusResult {
  return {
    bot: {
      uptime: 3600,
      cacheSize: 10,
      guilds: 5,
    },
    server: {
      status: 'healthy',
      version: '1.0.0',
      latency: 50,
    },
    ...overrides,
  };
}

export function createMockNoteListJSONAPIResponse(notes: Array<{
  id: string;
  summary?: string;
  classification?: string;
  status?: string;
  authorParticipantId?: string;
  communityServerId?: string;
  channelId?: string | null;
  requestId?: string | null;
  helpfulnessScore?: number;
  ratingsCount?: number;
  forcePublished?: boolean;
}> = []) {
  return {
    data: notes.map(note => ({
      type: 'notes' as const,
      id: note.id,
      attributes: {
        summary: note.summary ?? 'Test note summary',
        classification: note.classification ?? 'NOT_MISLEADING',
        status: (note.status ?? 'NEEDS_MORE_RATINGS') as 'NEEDS_MORE_RATINGS' | 'CURRENTLY_RATED_HELPFUL' | 'CURRENTLY_RATED_NOT_HELPFUL',
        helpfulness_score: note.helpfulnessScore ?? 0.5,
        author_participant_id: note.authorParticipantId ?? 'author-123',
        community_server_id: note.communityServerId ?? 'server-123',
        channel_id: note.channelId ?? null,
        content: null,
        request_id: note.requestId ?? null,
        ratings_count: note.ratingsCount ?? 0,
        force_published: note.forcePublished ?? false,
        force_published_at: null,
        created_at: new Date().toISOString(),
        updated_at: null,
      },
    })),
    jsonapi: { version: '1.1' as const },
  };
}

export function createMockNoteScoreJSONAPIResponse(overrides: {
  noteId?: string;
  score?: number;
  confidence?: string;
  algorithm?: string;
  ratingCount?: number;
  tier?: number;
  tierName?: string;
} = {}) {
  return {
    data: {
      type: 'note-scores',
      id: overrides.noteId ?? 'note-123',
      attributes: {
        score: overrides.score ?? 0.75,
        confidence: overrides.confidence ?? 'standard',
        algorithm: overrides.algorithm ?? 'bayesian',
        rating_count: overrides.ratingCount ?? 10,
        tier: overrides.tier ?? 1,
        tier_name: overrides.tierName ?? 'Tier 1',
        calculated_at: new Date().toISOString(),
        content: null,
      },
    },
    jsonapi: { version: '1.0' },
  };
}

export function createMockTopNotesJSONAPIResponse(overrides: {
  notes?: Array<{
    noteId: string;
    score: number;
    confidence: string;
    ratingCount: number;
    tier: number;
  }>;
  totalCount?: number;
  currentTier?: number;
  filtersApplied?: Record<string, unknown>;
} = {}) {
  const defaultNotes = overrides.notes ?? [
    { noteId: 'note-1', score: 0.9, confidence: 'high', ratingCount: 20, tier: 1 },
  ];

  return {
    data: defaultNotes.map(n => ({
      type: 'note-scores',
      id: n.noteId,
      attributes: {
        score: n.score,
        confidence: n.confidence,
        algorithm: 'matrix-factorization',
        rating_count: n.ratingCount,
        tier: n.tier,
        tier_name: `Tier ${n.tier}`,
        calculated_at: new Date().toISOString(),
        content: null,
      },
    })),
    jsonapi: { version: '1.0' },
    meta: {
      total_count: overrides.totalCount ?? defaultNotes.length,
      current_tier: overrides.currentTier ?? 1,
      filters_applied: overrides.filtersApplied,
    },
  };
}

export function createMockScoringStatusJSONAPIResponse(overrides: {
  noteCount?: number;
  tierLevel?: number;
  tierName?: string;
  dataConfidence?: string;
} = {}) {
  return {
    data: {
      type: 'scoring-status',
      id: 'status',
      attributes: {
        current_note_count: overrides.noteCount ?? 100,
        active_tier: {
          level: overrides.tierLevel ?? 3,
          name: overrides.tierName ?? 'Matrix Factorization',
          scorer_components: ['base', 'matrix'],
        },
        data_confidence: overrides.dataConfidence ?? 'high',
        tier_thresholds: {
          'tier-1': { min: 0, max: 10, current: false },
          'tier-2': { min: 10, max: 50, current: false },
          'tier-3': { min: 50, max: null, current: true },
        },
        next_tier_upgrade: null,
        performance_metrics: {
          avg_scoring_time_ms: 50,
          last_scoring_time_ms: 45,
          scorer_success_rate: 0.99,
          total_scoring_operations: 1000,
          failed_scoring_operations: 10,
        },
        warnings: [],
        configuration: {},
      },
    },
    jsonapi: { version: '1.0' },
  };
}

export function createMockBatchScoreJSONAPIResponse(overrides: {
  scores?: Array<{
    noteId: string;
    score: number;
    confidence: string;
    ratingCount: number;
    tier: number;
  }>;
  notFound?: string[];
  totalRequested?: number;
} = {}) {
  const defaultScores = overrides.scores ?? [];

  return {
    data: defaultScores.map(s => ({
      type: 'note-scores',
      id: s.noteId,
      attributes: {
        score: s.score,
        confidence: s.confidence,
        algorithm: 'bayesian',
        rating_count: s.ratingCount,
        tier: s.tier,
        tier_name: `Tier ${s.tier}`,
        calculated_at: new Date().toISOString(),
        content: null,
      },
    })),
    jsonapi: { version: '1.0' },
    meta: {
      total_requested: overrides.totalRequested ?? defaultScores.length,
      total_found: defaultScores.length,
      not_found: overrides.notFound ?? [],
    },
  };
}
