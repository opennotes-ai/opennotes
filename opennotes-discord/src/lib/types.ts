// Re-export types from generated types (these are still defined there)
import type { components } from './generated-types.js';
export type { components } from './generated-types.js';
export type RequestStatus = components['schemas']['RequestStatus'];
export type NoteStatus = components['schemas']['NoteStatus'];
export type HelpfulnessLevel = components['schemas']['HelpfulnessLevel'];
export type RatingThresholds = components['schemas']['RatingThresholdsResponse'];

// Flattened API types (defined locally in api-client.ts, not in generated-types.ts)
// Import these separately to avoid circular dependency issues
import type { NoteResponse, RatingResponse, RequestResponse } from './api-client.js';
export type { NoteResponse, RatingResponse, RequestResponse };

// Discord bot-specific types (different from server API types)
// These types represent Discord bot's internal data model

export interface Note {
  id: string;
  messageId: string;
  authorId: string;
  content: string;
  createdAt: number;
  helpfulCount: number;
  notHelpfulCount: number;
}

export interface NoteRequest {
  messageId: string;
  userId: string;
  community_server_id: string; // Required: Platform ID (e.g., Discord guild ID) - server handles lookup/auto-creation
  reason?: string;
  originalMessageContent?: string;
  discord_channel_id?: string;
  discord_author_id?: string;
  discord_timestamp?: Date;
  fact_check_metadata?: {
    dataset_item_id: string;
    similarity_score: number;
    dataset_name: string;
    rating?: string;
  };
  attachmentUrl?: string;
  attachmentType?: 'image' | 'video' | 'file';
  attachmentMetadata?: Record<string, unknown>;
  embeddedImageUrl?: string;
}

export interface CreateNoteRequest {
  messageId: string;
  authorId: string;
  content: string;
  channelId?: string;
  requestId?: string;
  originalMessageContent?: string;
  classification?: 'NOT_MISLEADING' | 'MISINFORMED_OR_POTENTIALLY_MISLEADING';
}

export interface CreateRatingRequest {
  noteId: string;
  userId: string;
  helpful: boolean;
}

export interface ListRequestsFilters {
  page?: number;
  size?: number;
  status?: RequestStatus;
  tweetId?: string;
  requestedBy?: string;
  communityServerId?: string;
}

// Server response type for requests
// This type maps to the server's RequestResponse schema
// Use RequestResponse from components['schemas'] for full API compatibility
export interface RequestItem {
  id: string;
  request_id: string;
  requested_by: string;
  requested_at: string;
  status: RequestStatus;
  note_id?: string | null;
  created_at: string;
  updated_at?: string | null;
  platform_message_id?: string | null;
  content?: string | null;
  community_server_id?: string | null;
  metadata?: Record<string, unknown> | null;
}

// Server response type for request info
// Maps to components['schemas']['RequestInfo'] from generated types
export interface RequestInfo {
  request_id: string;
  content?: string | null;
  requested_by: string;
  requested_at: string;
}

// Server response type for notes with ratings (used in queue)
// Note: tweet_id has been removed - platform message ID now comes from the linked request
export interface NoteWithRatings {
  id: string;
  author_id: string;  // User profile UUID
  channel_id?: string | null;
  summary: string;
  classification: string;
  helpfulness_score: number;
  status: NoteStatus;
  created_at: string;
  updated_at?: string | null;
  ratings: RatingResponse[];  // Server format ratings, not Discord bot format
  ratings_count: number;
  request?: RequestInfo | null;
}
