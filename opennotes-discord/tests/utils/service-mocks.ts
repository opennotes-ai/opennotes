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
