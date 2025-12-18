export interface VibeCheckDaysOption {
  name: string;
  value: number;
}

export const VIBE_CHECK_DAYS_OPTIONS: VibeCheckDaysOption[] = [
  { name: '1 day', value: 1 },
  { name: '3 days', value: 3 },
  { name: '7 days', value: 7 },
  { name: '14 days', value: 14 },
  { name: '30 days', value: 30 },
];

export interface BulkScanMessage {
  message_id: string;
  channel_id: string;
  community_server_id: string;
  content: string;
  author_id: string;
  author_username?: string;
  timestamp: string;
  attachment_urls?: string[];
  embed_content?: string;
}

export interface BulkScanBatch {
  scan_id: string;
  community_server_id: string;
  initiated_by: string;
  batch_index: number;
  total_batches: number;
  messages: BulkScanMessage[];
  cutoff_timestamp: string;
}

export interface FlaggedContent {
  messageId: string;
  channelId: string;
  guildId: string;
  content: string;
  authorId: string;
  authorUsername?: string;
  timestamp: string;
  matchType: 'misinformation' | 'harmful' | 'misleading' | 'needs_context';
  confidence: number;
  matchReason: string;
  messageUrl: string;
}

export interface BulkScanResult {
  scanId: string;
  guildId: string;
  initiatedBy: string;
  startedAt: string;
  completedAt: string;
  messagesScanned: number;
  channelsScanned: number;
  flaggedCount: number;
  flaggedContent: FlaggedContent[];
}

export interface ScanProgress {
  channelsProcessed: number;
  totalChannels: number;
  messagesProcessed: number;
  currentChannel?: string;
  estimatedTimeRemaining?: string;
}

export const BULK_SCAN_BATCH_SIZE = 100;

export const NATS_SUBJECTS = {
  BULK_SCAN_BATCH: 'OPENNOTES.bulk_scan.batch',
  BULK_SCAN_COMPLETE: 'OPENNOTES.bulk_scan.complete',
  BULK_SCAN_RESULT: 'OPENNOTES.bulk_scan.result',
} as const;

export interface BulkScanInitiateRequest {
  community_server_id: string;
  scan_window_days: number;
}

export interface BulkScanInitiateResponse {
  scan_id: string;
  status: string;
  community_server_id: string;
  scan_window_days: number;
}

export interface FlaggedMessage {
  message_id: string;
  channel_id: string;
  content: string;
  author_id: string;
  timestamp: string;
  match_score: number;
  matched_claim: string;
  matched_source: string;
}

export interface BulkScanResultsResponse {
  scan_id: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
  messages_scanned: number;
  flagged_messages: FlaggedMessage[];
}

export interface CreateNoteRequestsRequest {
  message_ids: string[];
  generate_ai_notes: boolean;
}

export interface CreateNoteRequestsResponse {
  created_count: number;
  scan_id: string;
}
