import { Client, Guild } from 'discord.js';
import { logger } from '../logger.js';
import { BotChannelService } from './BotChannelService.js';
import { GuildConfigService } from './GuildConfigService.js';
import { ConfigKey } from '../lib/config-schema.js';
import { apiClient } from '../api-client.js';
import { formatMessageLink, truncateContentWithMeta } from '../lib/bulk-scan-executor.js';
import type { BulkScanProgressEvent, MessageScoreInfo } from '../types/bulk-scan.js';
import { ContainerBuilder } from 'discord.js';
import {
  createContainer,
  createTextSection,
  createDivider,
  v2MessageFlags,
} from '../utils/v2-components.js';

export class VibecheckProgressService {
  private static readonly MAX_SCORE_TEXT_LENGTH = 1024;
  private readonly client: Client;
  private readonly guildConfigService: GuildConfigService;
  private readonly botChannelService: BotChannelService;

  constructor(client: Client) {
    this.client = client;
    this.guildConfigService = new GuildConfigService(apiClient);
    this.botChannelService = new BotChannelService();
  }

  async handleProgressEvent(event: BulkScanProgressEvent): Promise<void> {
    const { platform_community_server_id, scan_id, batch_number, message_scores } = event;

    const guild = this.client.guilds.cache.get(platform_community_server_id);
    if (!guild) {
      logger.debug('Guild not found for progress event', {
        platformId: platform_community_server_id,
        scanId: scan_id,
      });
      return;
    }

    const debugModeEnabled = await this.guildConfigService.get(
      guild.id,
      ConfigKey.VIBECHECK_DEBUG_MODE
    );

    if (!debugModeEnabled) {
      logger.debug('Vibecheck debug mode not enabled for guild', {
        guildId: guild.id,
        scanId: scan_id,
      });
      return;
    }

    const botChannelName = await this.guildConfigService.get(
      guild.id,
      ConfigKey.BOT_CHANNEL_NAME
    );

    const channel = this.botChannelService.findChannel(guild, botChannelName as string);
    if (!channel) {
      logger.warn('Bot channel not found for progress event', {
        guildId: guild.id,
        channelName: botChannelName,
      });
      return;
    }

    try {
      const container = this.formatProgressContainer(event, guild);
      await channel.send({ components: [container], flags: v2MessageFlags() });

      logger.debug('Sent vibecheck progress to bot channel', {
        guildId: guild.id,
        scanId: scan_id,
        batchNumber: batch_number,
        scoresCount: message_scores.length,
      });
    } catch (error) {
      logger.error('Failed to send progress to bot channel', {
        error: error instanceof Error ? error.message : String(error),
        guildId: guild.id,
        scanId: scan_id,
      });
    }
  }

  private formatProgressContainer(event: BulkScanProgressEvent, guild: Guild): ContainerBuilder {
    const { batch_number, messages_in_batch, message_scores, threshold_used, channel_ids, messages_processed } = event;

    const flaggedCount = message_scores.filter((s) => s.is_flagged).length;
    const shortScanId = event.scan_id.substring(0, 8);

    const channelNames = channel_ids
      .map((id) => guild.channels.cache.get(id)?.name)
      .filter((name): name is string => Boolean(name))
      .map((name) => `#${name}`);

    let channelDisplay = '';
    if (channelNames.length > 0) {
      const displayNames = channelNames.slice(0, 3);
      channelDisplay = `Analyzing ${displayNames.join(', ')}${channelNames.length > 3 ? '...' : ''}`;
    } else {
      channelDisplay = `Processing batch ${batch_number}`;
    }

    const messageCount = messages_processed > 0 ? messages_processed : messages_in_batch;
    const now = new Date();
    const timestamp = `<t:${Math.floor(now.getTime() / 1000)}:R>`;

    const container = createContainer(flaggedCount > 0 ? 0xff9900 : 0x00aa00);

    container.addTextDisplayComponents(
      createTextSection(`## 🔍 Vibecheck Progress - Batch ${batch_number}`)
    );

    container.addTextDisplayComponents(
      createTextSection(
        `${channelDisplay} (${messageCount} messages) | Threshold: ${(threshold_used * 100).toFixed(0)}%`
      )
    );

    const scoreLines = this.formatScoreLines(message_scores, threshold_used, guild.id);
    if (scoreLines.length > 0) {
      const truncated = scoreLines.slice(0, 10);
      const remaining = scoreLines.length - truncated.length;
      const scoreBlocks = this.buildScoreBlocks(truncated, remaining, flaggedCount);

      container.addSeparatorComponents(createDivider());

      for (const block of scoreBlocks) {
        container.addTextDisplayComponents(createTextSection(block));
      }
    }

    container.addSeparatorComponents(createDivider());
    container.addTextDisplayComponents(
      createTextSection(`*Scan ID: ${shortScanId}* ${timestamp}`)
    );

    return container;
  }

  private formatScoreLines(scores: MessageScoreInfo[], threshold: number, guildId: string): string[] {
    return scores.map((score) => {
      const percentage = (score.similarity_score * 100).toFixed(1);
      const thresholdPct = (threshold * 100).toFixed(0);
      const flag = score.is_flagged ? '✓ FLAGGED' : '✗';
      const shortMsgId = score.message_id.substring(0, 8);

      let line = `\`${shortMsgId}\`: ${percentage}% (thresh: ${thresholdPct}%) ${flag}`;

      if (score.is_flagged && score.matched_claim) {
        const claim = truncateContentWithMeta(score.matched_claim, 50);
        line += `\n  └─ *"${claim.text}"*`;
        if (claim.isTruncated) {
          line += `\n  └─ [View Original Message](${formatMessageLink(guildId, score.channel_id, score.message_id)})`;
        }
      }

      return line;
    });
  }

  private buildScoreBlocks(
    scoreLines: string[],
    remainingCount: number,
    flaggedCount: number
  ): string[] {
    const blocks: string[] = [];
    let currentLines: string[] = [];
    let currentLength = 0;
    let isFirst = true;

    const flushBlock = (): void => {
      if (currentLines.length === 0) {
        return;
      }
      const header = isFirst
        ? `**Message Scores (${flaggedCount} flagged)**`
        : '**Message Scores (continued)**';
      blocks.push(`${header}\n${currentLines.join('\n')}`);
      isFirst = false;
      currentLines = [];
      currentLength = 0;
    };

    for (const line of scoreLines) {
      const lineLength = line.length + (currentLines.length > 0 ? 1 : 0);
      if (
        currentLines.length > 0 &&
        currentLength + lineLength > VibecheckProgressService.MAX_SCORE_TEXT_LENGTH
      ) {
        flushBlock();
      }

      currentLines.push(line);
      currentLength += line.length + (currentLines.length > 1 ? 1 : 0);
    }

    if (remainingCount > 0) {
      const remainderLine = `... and ${remainingCount} more`;
      const remainderLength = remainderLine.length + (currentLines.length > 0 ? 1 : 0);
      if (
        currentLines.length > 0 &&
        currentLength + remainderLength > VibecheckProgressService.MAX_SCORE_TEXT_LENGTH
      ) {
        flushBlock();
      }
      currentLines.push(remainderLine);
    }

    flushBlock();
    return blocks;
  }
}
