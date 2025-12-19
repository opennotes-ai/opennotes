import {
  ChannelType,
  Collection,
  Guild,
  TextChannel,
  Message,
} from 'discord.js';
import { DiscordSnowflake } from '@sapphire/snowflake';
import { logger } from '../logger.js';
import { apiClient } from '../api-client.js';
import { natsPublisher } from '../events/NatsPublisher.js';
import {
  BULK_SCAN_BATCH_SIZE,
  NATS_SUBJECTS,
  type BulkScanMessage,
  type BulkScanBatch,
  type ScanProgress,
  type FlaggedMessage,
} from '../types/bulk-scan.js';

export const POLL_TIMEOUT_MS = 60000;
export const BACKOFF_INITIAL_MS = 1000;
export const BACKOFF_MULTIPLIER = 2;
export const BACKOFF_MAX_MS = 30000;

export interface BulkScanOptions {
  guild: Guild;
  days: number;
  initiatorId: string;
  errorId: string;
  progressCallback?: (progress: ScanProgress) => Promise<void>;
}

export interface BulkScanResult {
  scanId: string;
  messagesScanned: number;
  channelsScanned: number;
  batchesPublished: number;
  failedBatches: number;
  status: 'completed' | 'partial' | 'failed' | 'timeout';
  flaggedMessages: FlaggedMessage[];
  warningMessage?: string;
}

export async function executeBulkScan(options: BulkScanOptions): Promise<BulkScanResult> {
  const { guild, days, initiatorId, errorId, progressCallback } = options;
  const guildId = guild.id;

  const cutoffTimestamp = Date.now() - days * 24 * 60 * 60 * 1000;
  const cutoffSnowflake = DiscordSnowflake.generate({ timestamp: BigInt(cutoffTimestamp) });

  const textChannels = guild.channels.cache.filter(
    (channel): channel is TextChannel =>
      channel.type === ChannelType.GuildText && channel.viewable === true
  );

  const totalChannels = textChannels.size;

  if (totalChannels === 0) {
    return {
      scanId: '',
      messagesScanned: 0,
      channelsScanned: 0,
      batchesPublished: 0,
      failedBatches: 0,
      status: 'completed',
      flaggedMessages: [],
    };
  }

  const communityServer = await apiClient.getCommunityServerByPlatformId(guildId);
  const communityServerUuid = communityServer.id;

  const scanResponse = await apiClient.initiateBulkScan(communityServerUuid, days);
  const scanId = scanResponse.scan_id;

  logger.info('Initiated bulk scan', {
    error_id: errorId,
    scan_id: scanId,
    guild_id: guildId,
    days,
    total_channels: totalChannels,
  });

  let messagesProcessed = 0;
  let channelsProcessed = 0;
  let batchNumber = 0;
  let batchesPublished = 0;
  let failedBatches = 0;
  let currentBatch: BulkScanMessage[] = [];
  let pendingBatch: BulkScanMessage[] | null = null;

  const publishPendingBatch = async (isFinalBatch: boolean): Promise<void> => {
    if (pendingBatch === null || pendingBatch.length === 0) {
      return;
    }

    batchNumber++;

    const batch: BulkScanBatch = {
      scan_id: scanId,
      community_server_id: communityServerUuid,
      initiated_by: initiatorId,
      batch_number: batchNumber,
      is_final_batch: isFinalBatch,
      messages: pendingBatch,
      cutoff_timestamp: new Date(cutoffTimestamp).toISOString(),
    };

    try {
      await natsPublisher.publishBulkScanBatch(NATS_SUBJECTS.BULK_SCAN_BATCH, batch);
      batchesPublished++;
      logger.debug('Published batch', {
        scanId,
        batchNumber,
        isFinalBatch,
        messageCount: pendingBatch.length,
      });
    } catch (error) {
      failedBatches++;
      logger.warn('Failed to publish batch to NATS, continuing scan', {
        error: error instanceof Error ? error.message : String(error),
        scanId,
        batchNumber,
      });
    }

    pendingBatch = null;
  };

  const queueBatch = async (): Promise<void> => {
    if (currentBatch.length === 0) {
      return;
    }

    if (pendingBatch !== null) {
      await publishPendingBatch(false);
    }

    pendingBatch = currentBatch;
    currentBatch = [];
  };

  for (const [, channel] of textChannels) {
    try {
      if (progressCallback) {
        progressCallback({
          channelsProcessed,
          totalChannels,
          messagesProcessed,
          currentChannel: channel.name,
        }).catch((error) => {
          logger.warn('Progress callback failed', {
            error: error instanceof Error ? error.message : String(error),
            scanId,
            channelsProcessed,
            totalChannels,
          });
        });
      }

      let lastMessageId: string | undefined;
      let reachedCutoff = false;

      while (!reachedCutoff) {
        const fetchOptions: { limit: number; before?: string } = { limit: 100 };
        if (lastMessageId) {
          fetchOptions.before = lastMessageId;
        }

        let messages: Collection<string, Message>;
        try {
          messages = await channel.messages.fetch(fetchOptions);
        } catch (fetchError) {
          logger.warn('Failed to fetch messages from channel', {
            error_id: errorId,
            channel_id: channel.id,
            channel_name: channel.name,
            error: fetchError instanceof Error ? fetchError.message : String(fetchError),
          });
          break;
        }

        if (messages.size === 0) {
          break;
        }

        for (const [messageId, message] of messages) {
          if (BigInt(messageId) < cutoffSnowflake) {
            reachedCutoff = true;
            break;
          }

          if (message.author.bot) {
            continue;
          }

          if (!message.content && message.attachments.size === 0 && message.embeds.length === 0) {
            continue;
          }

          const scanMessage: BulkScanMessage = {
            message_id: message.id,
            channel_id: channel.id,
            community_server_id: communityServerUuid,
            content: message.content,
            author_id: message.author.id,
            author_username: message.author.username,
            timestamp: message.createdAt.toISOString(),
            attachment_urls: message.attachments.size > 0
              ? Array.from(message.attachments.values()).map(a => a.url)
              : undefined,
            embed_content: message.embeds.length > 0
              ? message.embeds.map(e => e.description || e.title || '').filter(Boolean).join('\n')
              : undefined,
          };

          currentBatch.push(scanMessage);
          messagesProcessed++;

          if (currentBatch.length >= BULK_SCAN_BATCH_SIZE) {
            await queueBatch();
          }

          lastMessageId = messageId;
        }

        if (messages.size < 100) {
          break;
        }

        lastMessageId = messages.last()?.id;
        if (!lastMessageId) {
          break;
        }
      }

      channelsProcessed++;
    } catch (channelError) {
      logger.error('Error processing channel', {
        error_id: errorId,
        channel_id: channel.id,
        channel_name: channel.name,
        error: channelError instanceof Error ? channelError.message : String(channelError),
      });
      channelsProcessed++;
    }
  }

  if (currentBatch.length > 0) {
    await queueBatch();
  }

  if (pendingBatch !== null) {
    await publishPendingBatch(true);
  }

  const totalBatches = batchNumber;

  logger.info('Bulk scan Discord scan complete, polling for results', {
    error_id: errorId,
    scan_id: scanId,
    guild_id: guildId,
    days,
    channels_scanned: channelsProcessed,
    messages_processed: messagesProcessed,
    batches_published: batchesPublished,
    failed_batches: failedBatches,
    total_batches: totalBatches,
  });

  if (batchesPublished === 0 && failedBatches > 0) {
    return {
      scanId,
      messagesScanned: messagesProcessed,
      channelsScanned: channelsProcessed,
      batchesPublished: 0,
      failedBatches,
      status: 'failed',
      flaggedMessages: [],
      warningMessage: 'Scan failed: unable to publish any message batches for analysis.',
    };
  }

  const results = await pollForResults(scanId, errorId);

  if (!results || results.status === 'failed') {
    return {
      scanId,
      messagesScanned: messagesProcessed,
      channelsScanned: channelsProcessed,
      batchesPublished,
      failedBatches,
      status: results?.status === 'failed' ? 'failed' : 'timeout',
      flaggedMessages: [],
    };
  }

  if (failedBatches > 0) {
    return {
      scanId,
      messagesScanned: results.messages_scanned,
      channelsScanned: channelsProcessed,
      batchesPublished,
      failedBatches,
      status: 'partial',
      flaggedMessages: results.flagged_messages,
      warningMessage: 'Scan encountered some issues so results may be incomplete.',
    };
  }

  return {
    scanId,
    messagesScanned: results.messages_scanned,
    channelsScanned: channelsProcessed,
    batchesPublished,
    failedBatches: 0,
    status: 'completed',
    flaggedMessages: results.flagged_messages,
  };
}

function calculateBackoffDelay(attempt: number): number {
  const delay = BACKOFF_INITIAL_MS * Math.pow(BACKOFF_MULTIPLIER, attempt);
  return Math.min(delay, BACKOFF_MAX_MS);
}

export async function pollForResults(
  scanId: string,
  errorId: string
): Promise<Awaited<ReturnType<typeof apiClient.getBulkScanResults>> | null> {
  const startTime = Date.now();
  let attempt = 0;

  while (Date.now() - startTime < POLL_TIMEOUT_MS) {
    try {
      const results = await apiClient.getBulkScanResults(scanId);

      if (results.status === 'completed' || results.status === 'failed') {
        return results;
      }

      const delay = calculateBackoffDelay(attempt);
      await new Promise(resolve => setTimeout(resolve, delay));
      attempt++;
    } catch (error) {
      logger.warn('Error polling for scan results', {
        error_id: errorId,
        scan_id: scanId,
        error: error instanceof Error ? error.message : String(error),
      });
      const delay = calculateBackoffDelay(attempt);
      await new Promise(resolve => setTimeout(resolve, delay));
      attempt++;
    }
  }

  logger.warn('Scan polling timed out', {
    error_id: errorId,
    scan_id: scanId,
    timeout_ms: POLL_TIMEOUT_MS,
  });

  return null;
}

export function formatMatchScore(score: number): string {
  return `${Math.round(score * 100)}%`;
}

export function formatMessageLink(guildId: string, channelId: string, messageId: string): string {
  return `https://discord.com/channels/${guildId}/${channelId}/${messageId}`;
}

export function truncateContent(content: string, maxLength: number = 100): string {
  if (content.length <= maxLength) {
    return content;
  }

  const ellipsis = '...';
  const targetLength = maxLength - ellipsis.length;

  if (targetLength <= 0) {
    return ellipsis;
  }

  const segmenter = new Intl.Segmenter(undefined, { granularity: 'grapheme' });
  const segments = Array.from(segmenter.segment(content));

  let result = '';
  for (const { segment } of segments) {
    if (result.length + segment.length > targetLength) {
      break;
    }
    result += segment;
  }

  return result + ellipsis;
}
