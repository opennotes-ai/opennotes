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
  messageId: string;
  channelId: string;
  guildId: string;
  content: string;
  authorId: string;
  authorUsername?: string;
  timestamp: string;
  attachmentUrls?: string[];
  embedContent?: string;
}

export interface BulkScanBatch {
  scanId: string;
  guildId: string;
  initiatedBy: string;
  batchIndex: number;
  totalBatches: number;
  messages: BulkScanMessage[];
  cutoffTimestamp: string;
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
