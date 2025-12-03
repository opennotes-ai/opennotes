export interface ScoreUpdateEvent {
  note_id: number;
  score: number;
  confidence: 'no_data' | 'provisional' | 'standard';
  algorithm: string;
  rating_count: number;
  tier: number;
  tier_name: string;
  timestamp: string;

  // Discord context (optional, may not be present for all notes)
  original_message_id?: string;
  channel_id?: string;
  community_server_id?: string;

  // Event metadata (optional)
  metadata?: {
    force_published?: boolean;
    force_published_by?: string;
    force_published_at?: string;
    admin_username?: string;
    [key: string]: unknown;
  };
}

export interface NotePublisherAttempt {
  noteId: number;
  originalMessageId: string;
  channelId: string;
  guildId: string;
  scoreAtPost: number;
  confidenceAtPost: string;
  success: boolean;
  errorMessage?: string;
}
