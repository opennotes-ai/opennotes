import { jest } from '@jest/globals';
import {
  ServiceResult,
  StatusResult,
  WriteNoteResult,
  ViewNotesResult,
  RateNoteResult,
  ErrorCode,
} from '../../src/services/types.js';
import type { Note, Rating } from '../../src/lib/types.js';
import {
  createMockLogger,
  createMockCache,
  createMockInteraction,
  createMockFetchResponse,
  createMockNote as createSharedMockNote,
  createMockRating as createSharedMockRating,
} from '@opennotes/test-utils';

export function createMockApiClient() {
  return {
    healthCheck: jest.fn<() => Promise<{ status: string; version: string }>>(),
    createNote: jest.fn<(req: any) => Promise<Note>>(),
    getNotes: jest.fn<(messageId: string) => Promise<Note[]>>(),
    rateNote: jest.fn<(req: any) => Promise<Rating>>(),
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

export function createMockRating(overrides?: Partial<Rating>): Rating {
  return createSharedMockRating(overrides) as Rating;
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
