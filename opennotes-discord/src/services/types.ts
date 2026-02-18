import { RequestItem, RequestStatus } from '../lib/types.js';
import type { NoteJSONAPIResponse, NoteListJSONAPIResponse, RatingJSONAPIResponse } from '../lib/api-client.js';

export interface ServiceResult<T> {
  success: boolean;
  data?: T;
  error?: ServiceError;
}

export interface ServiceError {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

export interface RateLimitResult {
  allowed: boolean;
  remaining: number;
  resetAt: number;
}

export interface WriteNoteInput {
  messageId: string;
  authorId: string;
  content: string;
  requestId?: string;
  originalMessageContent?: string;
  channelId?: string;
  guildId?: string;
  classification?: 'NOT_MISLEADING' | 'MISINFORMED_OR_POTENTIALLY_MISLEADING';
  username?: string;
  displayName?: string;
  avatarUrl?: string;
}

export interface WriteNoteResult {
  note: NoteJSONAPIResponse;
}

export interface ViewNotesInput {
  messageId: string;
}

export interface ViewNotesResult {
  notes: NoteListJSONAPIResponse;
}

export interface RateNoteInput {
  noteId: string;
  userId: string;
  helpful: boolean;
  username?: string;
  displayName?: string;
  avatarUrl?: string;
  guildId?: string;
  channelId?: string;
}

export interface RateNoteResult {
  rating: RatingJSONAPIResponse;
}

export interface RequestNoteInput {
  messageId: string;
  userId: string;
  community_server_id: string; // Required: Discord guild/server ID
  channelId?: string;
  reason?: string;
  originalMessageContent?: string;
  attachmentUrl?: string;
  attachmentType?: 'image' | 'video' | 'file';
  attachmentMetadata?: Record<string, unknown>;
  embeddedImageUrl?: string;
  username?: string;
  displayName?: string;
  avatarUrl?: string;
}

export interface ListRequestsInput {
  userId: string;
  page?: number;
  size?: number;
  status?: RequestStatus;
  myRequestsOnly?: boolean;
  communityServerId?: string;
}

export interface ListRequestsResult {
  requests: RequestItem[];
  total: number;
  page: number;
  size: number;
}

export interface StatusResult {
  bot: {
    uptime: number;
    cacheSize: number;
    guilds?: number;
  };
  server: {
    status: string;
    version: string;
    latency: number;
  };
}

export enum ErrorCode {
  RATE_LIMIT_EXCEEDED = 'RATE_LIMIT_EXCEEDED',
  VALIDATION_ERROR = 'VALIDATION_ERROR',
  API_ERROR = 'API_ERROR',
  NOT_FOUND = 'NOT_FOUND',
  UNAUTHORIZED = 'UNAUTHORIZED',
  CONFLICT = 'CONFLICT',
  RATE_LIMIT = 'RATE_LIMIT',
  UNKNOWN_ERROR = 'UNKNOWN_ERROR',
}
