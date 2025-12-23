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

export const EventType = {
  BULK_SCAN_MESSAGE_BATCH: 'bulk_scan.message_batch',
  BULK_SCAN_ALL_BATCHES_TRANSMITTED: 'bulk_scan.all_batches_transmitted',
  BULK_SCAN_PROCESSING_FINISHED: 'bulk_scan.processing_finished',
  BULK_SCAN_RESULTS: 'bulk_scan.results',
  BULK_SCAN_PROGRESS: 'bulk_scan.progress',
  BULK_SCAN_FAILED: 'bulk_scan.failed',
} as const;

export type EventTypeValue = (typeof EventType)[keyof typeof EventType];

export interface BaseEvent {
  event_id: string;
  event_type: EventTypeValue;
  version: string;
  timestamp: string;
  metadata: Record<string, unknown>;
}

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
  batch_number: number;
  is_final_batch: boolean;
  messages: BulkScanMessage[];
  cutoff_timestamp: string;
}

export interface BulkScanBatchEvent extends BaseEvent {
  event_type: typeof EventType.BULK_SCAN_MESSAGE_BATCH;
  scan_id: string;
  community_server_id: string;
  messages: BulkScanMessage[];
  batch_number: number;
  is_final_batch: boolean;
}

export interface BulkScanAllBatchesTransmitted {
  scan_id: string;
  community_server_id: string;
  messages_scanned: number;
}

export interface BulkScanAllBatchesTransmittedEvent extends BaseEvent {
  event_type: typeof EventType.BULK_SCAN_ALL_BATCHES_TRANSMITTED;
  scan_id: string;
  community_server_id: string;
  messages_scanned: number;
}

export interface BulkScanProcessingFinishedEvent extends BaseEvent {
  event_type: typeof EventType.BULK_SCAN_PROCESSING_FINISHED;
  scan_id: string;
  community_server_id: string;
  messages_scanned: number;
  messages_flagged: number;
}

export interface MessageScoreInfo {
  message_id: string;
  channel_id: string;
  similarity_score: number;
  threshold: number;
  is_flagged: boolean;
  matched_claim?: string;
  moderation_flagged?: boolean | null;
  moderation_categories?: Record<string, boolean> | null;
  moderation_scores?: Record<string, number> | null;
}

export interface BulkScanProgressEvent extends BaseEvent {
  event_type: typeof EventType.BULK_SCAN_PROGRESS;
  scan_id: string;
  community_server_id: string;
  platform_id: string;
  batch_number: number;
  messages_in_batch: number;
  messages_processed: number;
  channel_ids: string[];
  message_scores: MessageScoreInfo[];
  threshold_used: number;
}

export interface BulkScanFailedEvent extends BaseEvent {
  event_type: typeof EventType.BULK_SCAN_FAILED;
  scan_id: string;
  community_server_id: string;
  error_message: string;
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
  BULK_SCAN_BATCH: 'OPENNOTES.bulk_scan_message_batch',
  BULK_SCAN_ALL_BATCHES_TRANSMITTED: 'OPENNOTES.bulk_scan_all_batches_transmitted',
  BULK_SCAN_PROCESSING_FINISHED: 'OPENNOTES.bulk_scan_processing_finished',
  BULK_SCAN_RESULT: 'OPENNOTES.bulk_scan_results',
  BULK_SCAN_PROGRESS: 'OPENNOTES.bulk_scan_progress',
  BULK_SCAN_FAILED: 'OPENNOTES.bulk_scan_failed',
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

// Re-export API types from generated schema (single source of truth)
export type {
  SimilarityMatch,
  OpenAIModerationMatch,
  MatchResult,
  ScanErrorInfoSchema as ScanErrorInfo,
  ScanErrorSummarySchema as ScanErrorSummary,
  FlaggedMessageAttributes as FlaggedMessage,
} from '../lib/api-client.js';

export interface CreateNoteRequestsRequest {
  message_ids: string[];
  generate_ai_notes: boolean;
}

export interface CreateNoteRequestsResponse {
  created_count: number;
  scan_id: string;
}
