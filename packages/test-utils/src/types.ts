export interface Note {
  id: string;
  messageId: string;
  authorId: string;
  content: string;
  createdAt: number;
  helpfulCount: number;
  notHelpfulCount: number;
}

export interface Rating {
  noteId: string;
  userId: string;
  helpful: boolean;
  createdAt: number;
}

export interface ServiceResult<T> {
  success: boolean;
  data?: T;
  error?: {
    code: string;
    message: string;
    details?: any;
  };
}

export type ErrorCode =
  | 'API_ERROR'
  | 'NETWORK_ERROR'
  | 'VALIDATION_ERROR'
  | 'NOT_FOUND'
  | 'UNAUTHORIZED'
  | 'RATE_LIMITED'
  | 'INTERNAL_ERROR';
