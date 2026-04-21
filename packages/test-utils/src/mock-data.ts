import type { Note, Rating, ServiceResult, ErrorCode } from './types.js';

export function createMockNote(overrides?: Partial<Note>): Note {
  const now = Date.now();
  return {
    id: 'note-123',
    messageId: 'msg-456',
    authorId: 'user-789',
    content: 'Test community note',
    createdAt: now,
    helpfulCount: 0,
    notHelpfulCount: 0,
    ...overrides,
  };
}

export function createMockRating(overrides?: Partial<Rating>): Rating {
  const now = Date.now();
  return {
    noteId: 'note-456',
    userId: 'user-789',
    helpful: true,
    createdAt: now,
    ...overrides,
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
