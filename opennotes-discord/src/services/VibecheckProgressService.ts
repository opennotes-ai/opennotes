import { Client, EmbedBuilder, Guild } from 'discord.js';
import { logger } from '../logger.js';
import { BotChannelService } from './BotChannelService.js';
import { GuildConfigService } from './GuildConfigService.js';
import { ConfigKey } from '../lib/config-schema.js';
import { apiClient } from '../api-client.js';
import type { BulkScanProgressEvent, MessageScoreInfo } from '../types/bulk-scan.js';

export class VibecheckProgressService {
  private readonly client: Client;
  private readonly guildConfigService: GuildConfigService;
  private readonly botChannelService: BotChannelService;

  constructor(client: Client) {
    this.client = client;
    this.guildConfigService = new GuildConfigService(apiClient);
    this.botChannelService = new BotChannelService();
  }

  async handleProgressEvent(event: BulkScanProgressEvent): Promise<void> {
    const { platform_id, scan_id, batch_number, message_scores } = event;

    const guild = this.client.guilds.cache.get(platform_id);
    if (!guild) {
      logger.debug('Guild not found for progress event', {
        platformId: platform_id,
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
      const embed = this.formatProgressEmbed(event, guild);
      await channel.send({ embeds: [embed] });

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

  private formatProgressEmbed(event: BulkScanProgressEvent, guild: Guild): EmbedBuilder {
    const { batch_number, messages_in_batch, message_scores, threshold_used, channel_ids, messages_processed } = event;

    const flaggedCount = message_scores.filter((s) => s.is_flagged).length;
    const shortScanId = event.scan_id.substring(0, 8);

    // Resolve channel IDs to names (AC #4)
    const channelNames = channel_ids
      .map((id) => guild.channels.cache.get(id)?.name)
      .filter((name): name is string => Boolean(name))
      .map((name) => `#${name}`);

    // Format channel display: show up to 3 channels, then ellipsis
    let channelDisplay = '';
    if (channelNames.length > 0) {
      const displayNames = channelNames.slice(0, 3);
      channelDisplay = `Analyzing ${displayNames.join(', ')}${channelNames.length > 3 ? '...' : ''}`;
    } else {
      channelDisplay = `Processing batch ${batch_number}`;
    }

    const messageCount = messages_processed > 0 ? messages_processed : messages_in_batch;

    const embed = new EmbedBuilder()
      .setTitle(`🔍 Vibecheck Progress - Batch ${batch_number}`)
      .setColor(flaggedCount > 0 ? 0xff9900 : 0x00aa00)
      .setDescription(
        `${channelDisplay} (${messageCount} messages) | Threshold: ${(threshold_used * 100).toFixed(0)}%`
      )
      .setFooter({ text: `Scan ID: ${shortScanId}` })
      .setTimestamp();

    const scoreLines = this.formatScoreLines(message_scores, threshold_used);
    if (scoreLines.length > 0) {
      const truncated = scoreLines.slice(0, 10);
      const remaining = scoreLines.length - truncated.length;

      let scoreText = truncated.join('\n');
      if (remaining > 0) {
        scoreText += `\n... and ${remaining} more`;
      }

      embed.addFields({
        name: `Message Scores (${flaggedCount} flagged)`,
        value: scoreText || 'No messages processed',
        inline: false,
      });
    }

    return embed;
  }

  private formatScoreLines(scores: MessageScoreInfo[], threshold: number): string[] {
    return scores.map((score) => {
      const percentage = (score.similarity_score * 100).toFixed(1);
      const thresholdPct = (threshold * 100).toFixed(0);
      const flag = score.is_flagged ? '✓ FLAGGED' : '✗';
      const shortMsgId = score.message_id.substring(0, 8);

      let line = `\`${shortMsgId}\`: ${percentage}% (thresh: ${thresholdPct}%) ${flag}`;

      if (score.is_flagged && score.matched_claim) {
        const claim = score.matched_claim.substring(0, 50);
        line += `\n  └─ *"${claim}${score.matched_claim.length > 50 ? '...' : ''}"*`;
      }

      return line;
    });
  }
}
