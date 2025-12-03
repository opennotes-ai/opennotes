import { EmbedBuilder, Colors, ActionRowBuilder, ButtonBuilder, ButtonStyle, GuildMember } from 'discord.js';
import { ServiceResult, WriteNoteResult, ViewNotesResult, RateNoteResult, StatusResult, ListRequestsResult, ErrorCode } from './types.js';
import type { RequestStatus } from '../lib/types.js';
import type { NoteScoreResponse, TopNotesResponse, ScoringStatusResponse, ScoreConfidence } from './ScoringService.js';
import { DISCORD_LIMITS } from '../lib/constants.js';
import { cache } from '../cache.js';
import { generateShortId } from '../lib/validation.js';
import { logger } from '../logger.js';
import type { QueueItem, QueueSummary, PaginationConfig } from '../lib/queue-renderer.js';
import { hasManageGuildPermission } from '../lib/permissions.js';
import { extractPlatformMessageId } from '../lib/discord-utils.js';

export class DiscordFormatter {
  private static formatMessageIdLink(messageId: string, guildId?: string, channelId?: string): string {
    if (guildId && channelId) {
      return `[${messageId}](https://discord.com/channels/${guildId}/${channelId}/${messageId})`;
    }
    return messageId;
  }

  static formatWriteNoteSuccess(
    result: WriteNoteResult,
    messageId: string,
    guildId?: string,
    channelId?: string
  ): { embeds: EmbedBuilder[] } {
    const messageIdDisplay = this.formatMessageIdLink(messageId, guildId, channelId);

    const embed = new EmbedBuilder()
      .setColor(Colors.Blue)
      .setTitle('Community Note Created')
      .setDescription(result.note.content)
      .addFields(
        { name: 'Message ID', value: messageIdDisplay, inline: true },
        { name: 'Author', value: `<@${result.note.authorId}>`, inline: true },
        { name: 'Note ID', value: String(result.note.id), inline: true }
      )
      .setTimestamp();

    return { embeds: [embed] };
  }

  static formatViewNotesSuccess(
    result: ViewNotesResult,
    scoresMap?: Map<string, NoteScoreResponse>
  ): { embeds: EmbedBuilder[] } {
    if (result.notes.length === 0) {
      return { embeds: [] };
    }

    const embeds = result.notes.map(note => {
      const embed = new EmbedBuilder()
        .setColor(Colors.Blue)
        .setTitle('Community Note')
        .setDescription(note.content)
        .addFields(
          { name: 'Author', value: `<@${note.authorId}>`, inline: true },
          { name: 'Note ID', value: String(note.id), inline: true },
          {
            name: 'Ratings',
            value: `👍 ${note.helpfulCount} | 👎 ${note.notHelpfulCount}`,
            inline: true
          }
        )
        .setTimestamp(note.createdAt);

      const scoreData = scoresMap?.get(String(note.id));
      const scoreField = this.formatScoreInNoteEmbed(scoreData || null);
      if (scoreField) {
        embed.addFields(scoreField);
      }

      return embed;
    });

    return { embeds: embeds.slice(0, DISCORD_LIMITS.MAX_EMBEDS_PER_MESSAGE) };
  }

  static formatRateNoteSuccess(result: RateNoteResult, noteId: string, helpful: boolean): { embeds: EmbedBuilder[] } {
    const embed = new EmbedBuilder()
      .setColor(helpful ? Colors.Green : Colors.Red)
      .setTitle('Rating Submitted')
      .setDescription(`You rated this note as **${helpful ? 'Helpful' : 'Not Helpful'}**`)
      .addFields(
        { name: 'Note ID', value: noteId, inline: true },
        { name: 'Rated by', value: `<@${result.rating.userId}>`, inline: true }
      )
      .setTimestamp();

    return { embeds: [embed] };
  }

  static formatRequestNoteSuccess(
    messageId: string,
    userId: string,
    reason?: string,
    guildId?: string,
    channelId?: string
  ): { embeds: EmbedBuilder[] } {
    const messageIdDisplay = this.formatMessageIdLink(messageId, guildId, channelId);

    const embed = new EmbedBuilder()
      .setColor(Colors.Green)
      .setTitle('Note Request Submitted')
      .setDescription('Your request for a community note has been recorded.')
      .addFields(
        { name: 'Message ID', value: messageIdDisplay, inline: true },
        { name: 'Requested by', value: `<@${userId}>`, inline: true }
      )
      .setTimestamp();

    if (reason) {
      embed.addFields({ name: 'Reason', value: reason });
    }

    return { embeds: [embed] };
  }

  static async formatListRequestsSuccess(
    result: ListRequestsResult,
    options?: { status?: string; myRequestsOnly?: boolean; communityServerId?: string }
  ): Promise<{
    summary: QueueSummary;
    items: QueueItem[];
    pagination?: PaginationConfig;
    stateId?: string;
  }> {
    const totalPages = Math.ceil(result.total / result.size);

    // Create summary embed
    const summaryEmbed = new EmbedBuilder()
      .setColor(Colors.Blue)
      .setTitle('📋 Note Requests')
      .setFooter({ text: `Page ${result.page} of ${totalPages} • Total: ${result.total} requests` })
      .setTimestamp();

    if (result.requests.length === 0) {
      summaryEmbed.setDescription('No requests found');
      return {
        summary: { embed: summaryEmbed },
        items: [],
      };
    }

    summaryEmbed.setDescription(
      `Showing requests ${(result.page - 1) * result.size + 1}-${Math.min(result.page * result.size, result.total)} of ${result.total}\n\n` +
      `Each pending request has action buttons directly below it.`
    );

    // Create one item per request (with async cache operations for button state)
    const items: QueueItem[] = await Promise.all(
      result.requests.map(async (request) => {
        const statusEmojiMap: Record<RequestStatus, string> = {
          PENDING: '⏳',
          IN_PROGRESS: '🔄',
          COMPLETED: '✅',
          FAILED: '❌',
        };
        const statusEmoji = statusEmojiMap[request.status] || '❓';

        const timestamp = Math.floor(new Date(request.requested_at).getTime() / 1000);
        const requestedBy = `<@${request.requested_by}>`;
        const noteInfo = request.note_id ? `Note: ${request.note_id}` : 'No note yet';
        const effectiveMessageId = extractPlatformMessageId(request.platform_message_id, request.request_id);
        const messageIdDisplay = effectiveMessageId || 'No message ID';

        // Format message preview from archive content
        const contentPreview = this.formatMessagePreview(request.content);

        const fieldValues = [
          `**Message:** ${messageIdDisplay}`,
          `**Status:** ${request.status}`,
          `**Requester:** ${requestedBy}`,
          `**Requested:** <t:${timestamp}:R>`,
          `**${noteInfo}**`,
        ];

        // Add content preview if available
        if (contentPreview) {
          fieldValues.push(`**Original message content:** ${contentPreview}`);
        }

        // Add instruction for write note buttons if status is PENDING and we have a message ID
        if (request.status === 'PENDING' && effectiveMessageId) {
          fieldValues.push('\n**Write a note that this message is:**');
        }

        const embed = new EmbedBuilder()
          .setColor(Colors.Blue)
          .setTitle(`${statusEmoji} ${request.request_id}`)
          .setDescription(fieldValues.join('\n'))
          .setTimestamp(new Date(request.requested_at));

        // If content is an image URL, embed it directly
        if (request.content && this.isImageUrl(request.content)) {
          embed.setImage(request.content.trim());
        }

        // Add action buttons for PENDING requests with a message ID (from platform_message_id or extracted from request_id)
        const buttons: ActionRowBuilder<ButtonBuilder>[] = [];
        if (effectiveMessageId && request.status === 'PENDING') {
          // Generate short IDs and cache the request_id to avoid exceeding 100-char custom ID limit
          const writeNoteNotMisleadingShortId = generateShortId();
          const writeNoteMisinformedShortId = generateShortId();
          const aiWriteNoteShortId = generateShortId();

          const writeNoteNotMisleadingCacheKey = `write_note_state:${writeNoteNotMisleadingShortId}`;
          const writeNoteMisinformedCacheKey = `write_note_state:${writeNoteMisinformedShortId}`;
          const aiWriteNoteCacheKey = `write_note_state:${aiWriteNoteShortId}`;
          const ttl = 300; // 5 minutes

          // Store request_id in cache
          try {
            await cache.set(writeNoteNotMisleadingCacheKey, request.request_id, ttl);
            await cache.set(writeNoteMisinformedCacheKey, request.request_id, ttl);
            await cache.set(aiWriteNoteCacheKey, request.request_id, ttl);
            logger.debug('Stored write note button state in cache', {
              writeNoteNotMisleadingShortId,
              writeNoteMisinformedShortId,
              aiWriteNoteShortId,
              request_id: request.request_id,
            });
          } catch (error) {
            logger.error('Failed to store write note button state in cache', {
              error: error instanceof Error ? error.message : String(error),
              request_id: request.request_id,
            });
          }

          const row = new ActionRowBuilder<ButtonBuilder>().addComponents(
            new ButtonBuilder()
              .setCustomId(`write_note:NOT_MISLEADING:${writeNoteNotMisleadingShortId}`)
              .setLabel('Not Misleading')
              .setStyle(ButtonStyle.Success),
            new ButtonBuilder()
              .setCustomId(`write_note:MISINFORMED_OR_POTENTIALLY_MISLEADING:${writeNoteMisinformedShortId}`)
              .setLabel('Misinformed or Misleading')
              .setStyle(ButtonStyle.Danger),
            new ButtonBuilder()
              .setCustomId(`ai_write_note:${aiWriteNoteShortId}`)
              .setLabel('✨ AI Generate')
              .setStyle(ButtonStyle.Primary)
          );
          buttons.push(row);
        }

        return {
          id: request.request_id,
          embed,
          buttons,
        };
      })
    );

    // Setup pagination if needed
    let stateId: string | undefined;
    let paginationConfig: PaginationConfig | undefined;

    if (totalPages > 1) {
      // Store filter options in cache with short random ID
      stateId = generateShortId();
      const filterState = {
        status: options?.status,
        myRequestsOnly: options?.myRequestsOnly,
        communityServerId: options?.communityServerId,
      };

      const cacheKey = `pagination:${stateId}`;
      const ttl = 300; // 5 minutes

      try {
        await cache.set(cacheKey, filterState, ttl);
        logger.debug('Stored pagination state in cache', { stateId, cacheKey, filterState });
      } catch (error) {
        logger.error('Failed to store pagination state in cache', {
          error: error instanceof Error ? error.message : String(error),
          stateId,
        });
      }

      paginationConfig = {
        currentPage: result.page,
        totalPages,
        previousButtonId: `request_queue_page:${result.page - 1}:${stateId}`,
        nextButtonId: `request_queue_page:${result.page + 1}:${stateId}`,
      };
    }

    return {
      summary: { embed: summaryEmbed },
      items,
      pagination: paginationConfig,
      stateId,
    };
  }

  static formatStatusSuccess(result: StatusResult): { embeds: EmbedBuilder[] } {
    const hours = Math.floor(result.bot.uptime / 3600);
    const minutes = Math.floor((result.bot.uptime % 3600) / 60);
    const seconds = Math.floor(result.bot.uptime % 60);

    const botValue = [
      `**Uptime:** ${hours}h ${minutes}m ${seconds}s`,
      `**Cache Size:** ${result.bot.cacheSize} entries`,
    ];

    if (result.bot.guilds !== undefined) {
      botValue.push(`**Guilds:** ${result.bot.guilds}`);
    }

    const embed = new EmbedBuilder()
      .setColor(Colors.Green)
      .setTitle('Bot Status')
      .addFields(
        {
          name: 'Bot',
          value: botValue.join('\n'),
          inline: true
        },
        {
          name: 'Server',
          value: [
            `**Status:** ${result.server.status}`,
            `**Version:** ${result.server.version}`,
            `**Latency:** ${result.server.latency}ms`,
          ].join('\n'),
          inline: true
        }
      )
      .setTimestamp();

    return { embeds: [embed] };
  }

  static formatError<T>(result: ServiceResult<T>): { content?: string; embeds?: EmbedBuilder[] } {
    if (!result.error) {
      return { content: 'An unknown error occurred' };
    }

    switch (result.error.code as ErrorCode) {
      case ErrorCode.RATE_LIMIT_EXCEEDED: {
        const resetAt = result.error.details?.resetAt;
        const resetTime = typeof resetAt === 'number' ? Math.floor(resetAt / 1000) : 0;
        return {
          content: `Rate limit exceeded. Try again <t:${resetTime}:R>`,
        };
      }

      case ErrorCode.VALIDATION_ERROR:
        return {
          content: result.error.message,
        };

      case ErrorCode.NOT_FOUND:
        return {
          content: result.error.message,
        };

      case ErrorCode.CONFLICT: {
        let message = result.error.message;

        if (result.error.details?.helpText) {
          message += `\n\n💡 ${String(result.error.details.helpText)}`;
        }

        if (result.error.details?.errorId) {
          message += `\n\nError ID: \`${String(result.error.details.errorId)}\``;
        }

        return {
          content: message,
        };
      }

      case ErrorCode.API_ERROR:
        if (result.error.message.includes('API may be down')) {
          const embed = new EmbedBuilder()
            .setColor(Colors.Red)
            .setTitle('Status Check Failed')
            .setDescription(result.error.message)
            .setTimestamp();
          return { embeds: [embed] };
        }
        return {
          content: result.error.message,
        };

      default:
        return {
          content: 'An unexpected error occurred. Please try again later.',
        };
    }
  }

  static getConfidenceEmoji(confidence: ScoreConfidence): string {
    switch (confidence) {
      case 'standard':
        return '⭐';
      case 'provisional':
        return '⚠️';
      case 'no_data':
        return '❓';
      default:
        return '❓';
    }
  }

  static getConfidenceLabel(confidence: ScoreConfidence): string {
    switch (confidence) {
      case 'standard':
        return 'Standard (5+ ratings)';
      case 'provisional':
        return 'Provisional (<5 ratings)';
      case 'no_data':
        return 'No data (0 ratings)';
      default:
        return 'Unknown';
    }
  }

  static getScoreColor(score: number): number {
    if (score >= 0.7) {return Colors.Green;}
    if (score >= 0.4) {return Colors.Yellow;}
    return Colors.Red;
  }

  static formatScore(score: number): string {
    return score.toFixed(3);
  }

  static formatNoteScore(scoreData: NoteScoreResponse): { embeds: EmbedBuilder[] } {
    const confidenceEmoji = this.getConfidenceEmoji(scoreData.confidence);
    const confidenceLabel = this.getConfidenceLabel(scoreData.confidence);
    const scoreColor = this.getScoreColor(scoreData.score);
    const formattedScore = this.formatScore(scoreData.score);

    const embed = new EmbedBuilder()
      .setColor(scoreColor)
      .setTitle(`Note Score: ${formattedScore}`)
      .setDescription(this.getScoreExplanation(scoreData))
      .addFields(
        { name: 'Note ID', value: String(scoreData.note_id), inline: true },
        { name: 'Score', value: `${formattedScore} (0.0-1.0)`, inline: true },
        { name: 'Confidence', value: `${confidenceEmoji} ${confidenceLabel}`, inline: true },
        { name: 'Rating Count', value: String(scoreData.rating_count), inline: true },
        { name: 'Algorithm', value: scoreData.algorithm, inline: true },
        { name: 'Tier', value: `Tier ${scoreData.tier}`, inline: true }
      );

    // Add footer with calculated_at timestamp if available
    if (scoreData.calculated_at) {
      embed.setFooter({ text: `Calculated at ${new Date(scoreData.calculated_at).toLocaleString()}` });
    }

    return { embeds: [embed] };
  }

  static formatTopNotes(response: TopNotesResponse, page: number = 1, pageSize: number = 10): { embeds: EmbedBuilder[] } {
    if (response.notes.length === 0) {
      const embed = new EmbedBuilder()
        .setColor(Colors.Blue)
        .setTitle('Top Scored Notes')
        .setDescription('No notes found matching the criteria.')
        .setTimestamp();
      return { embeds: [embed] };
    }

    const totalPages = Math.ceil(response.total_count / pageSize);
    const fields = response.notes.map((note, index) => {
      const rank = (page - 1) * pageSize + index + 1;
      const scoreColor = note.score >= 0.7 ? '🟢' : note.score >= 0.4 ? '🟡' : '🔴';
      const confidenceEmoji = this.getConfidenceEmoji(note.confidence);
      const formattedScore = this.formatScore(note.score);

      return {
        name: `${rank}. ${scoreColor} Note ${note.note_id} - Score: ${formattedScore}`,
        value: [
          `**Confidence:** ${confidenceEmoji} ${note.confidence}`,
          `**Ratings:** ${note.rating_count}`,
          `**Tier:** ${note.tier} | **Algorithm:** ${note.algorithm}`,
        ].join('\n'),
        inline: false,
      };
    });

    const embed = new EmbedBuilder()
      .setColor(Colors.Blue)
      .setTitle('Top Scored Notes')
      .addFields(fields.slice(0, DISCORD_LIMITS.MAX_EMBEDS_PER_MESSAGE))
      .setFooter({ text: `Page ${page} of ${totalPages} • Total: ${response.total_count} notes` })
      .setTimestamp();

    if (response.filters_applied) {
      const filters = [];
      if (String(response.filters_applied.min_confidence)) {
        filters.push(`Min Confidence: ${String(response.filters_applied.min_confidence)}`);
      }
      if (response.filters_applied.tier !== undefined) {
        filters.push(`Tier: ${String(response.filters_applied.tier)}`);
      }
      if (filters.length > 0) {
        embed.setDescription(`Filters: ${filters.join(' | ')}`);
      }
    }

    return { embeds: [embed] };
  }

  static formatTopNotesForQueue(
    response: TopNotesResponse,
    page: number = 1,
    pageSize: number = 10,
    userMember?: GuildMember | null
  ): {
    summary: QueueSummary;
    items: QueueItem[];
    pagination?: PaginationConfig;
  } {
    const totalPages = Math.ceil(response.total_count / pageSize);

    const summaryEmbed = new EmbedBuilder()
      .setColor(Colors.Blue)
      .setTitle('⭐ Top Scored Notes')
      .setFooter({ text: `Page ${page} of ${totalPages} • Total: ${response.total_count} notes` })
      .setTimestamp();

    if (response.notes.length === 0) {
      summaryEmbed.setDescription('No notes found matching the criteria.');
      return {
        summary: { embed: summaryEmbed },
        items: [],
      };
    }

    const filterDescription: string[] = [];
    if (response.filters_applied) {
      if (String(response.filters_applied.min_confidence)) {
        filterDescription.push(`Min Confidence: ${String(response.filters_applied.min_confidence)}`);
      }
      if (response.filters_applied.tier !== undefined) {
        filterDescription.push(`Tier: ${String(response.filters_applied.tier)}`);
      }
    }

    const descriptionParts = [
      `Showing notes ${(page - 1) * pageSize + 1}-${Math.min(page * pageSize, response.total_count)} of ${response.total_count}`,
    ];
    if (filterDescription.length > 0) {
      descriptionParts.push(`**Filters:** ${filterDescription.join(' | ')}`);
    }
    summaryEmbed.setDescription(descriptionParts.join('\n\n'));

    const items: QueueItem[] = response.notes.map((note, index) => {
      const rank = (page - 1) * pageSize + index + 1;
      const scoreColor = note.score >= 0.7 ? '🟢' : note.score >= 0.4 ? '🟡' : '🔴';
      const confidenceEmoji = this.getConfidenceEmoji(note.confidence);
      const formattedScore = this.formatScore(note.score);

      // Format message preview from content
      const contentPreview = this.formatMessagePreview(note.content);

      const descriptionFields = [
        `**Score:** ${formattedScore} (0.0-1.0)`,
        `**Confidence:** ${confidenceEmoji} ${this.getConfidenceLabel(note.confidence)}`,
        `**Ratings:** ${note.rating_count}`,
        `**Tier:** ${note.tier} | **Algorithm:** ${note.algorithm}`,
      ];

      // Add content preview if available
      if (contentPreview) {
        descriptionFields.push(`**Original message content:** ${contentPreview}`);
      }

      const embed = new EmbedBuilder()
        .setColor(this.getScoreColor(note.score))
        .setTitle(`${rank}. ${scoreColor} Note ${note.note_id}`)
        .setDescription(descriptionFields.join('\n'))
        .setTimestamp();

      // If content is an image URL, embed it directly
      if (note.content && this.isImageUrl(note.content)) {
        embed.setImage(note.content.trim());
      }

      // Add Force Publish button for admins
      const buttons: ActionRowBuilder<ButtonBuilder>[] = [];
      const isAdmin = userMember && hasManageGuildPermission(userMember);
      if (isAdmin) {
        const forcePublishButton = new ButtonBuilder()
          .setCustomId(`force_publish:${note.note_id}`)
          .setLabel('Force Publish')
          .setStyle(ButtonStyle.Danger);
        buttons.push(new ActionRowBuilder<ButtonBuilder>().addComponents(forcePublishButton));
      }

      return {
        id: String(note.note_id),
        embed,
        buttons,
      };
    });

    return {
      summary: { embed: summaryEmbed },
      items,
    };
  }

  static formatScoringStatus(status: ScoringStatusResponse): string {
    const tierInfo = status.active_tier;
    const nextTier = tierInfo.level < 5 ? tierInfo.level + 1 : null;
    const nextTierInfo = status.next_tier_upgrade;
    const progressToNext = nextTierInfo
      ? `\n**Progress to Tier ${nextTier}:** ${status.current_note_count}/${nextTierInfo.notes_needed} notes (${nextTierInfo.notes_to_upgrade} more needed)`
      : '\n**Status:** Maximum tier reached';

    return [
      `**Current Tier:** ${tierInfo.level} (${tierInfo.name})`,
      `**Note Count:** ${status.current_note_count}`,
      `**Data Confidence:** ${status.data_confidence}`,
      progressToNext,
    ].join('\n');
  }

  private static getScoreExplanation(scoreData: NoteScoreResponse): string {
    const isTier0 = scoreData.tier === 0;
    const explanations = [
      '**How scores work:**',
    ];

    if (isTier0) {
      explanations.push(
        '🌱 **Bootstrap Phase (Tier 0):** Scores use Bayesian Average to handle low data volumes.',
        'This provides stable estimates even with few ratings by blending actual ratings with a prior belief.',
        `The system needs ${scoreData.rating_count < 5 ? '5+ ratings' : 'more notes'} for higher confidence.`
      );
    } else {
      explanations.push(
        `⚙️ **Tier ${scoreData.tier}:** Using advanced ${scoreData.algorithm} for scoring.`,
        'This algorithm uses matrix factorization to detect patterns across notes and raters.',
        'Higher tiers provide more sophisticated analysis as data volume grows.'
      );
    }

    return explanations.join('\n');
  }

  static formatScoreInNoteEmbed(scoreData: NoteScoreResponse | null): { name: string; value: string; inline: boolean } | null {
    if (!scoreData) {
      return {
        name: 'Score',
        value: '❓ Not yet scored',
        inline: true,
      };
    }

    const confidenceEmoji = this.getConfidenceEmoji(scoreData.confidence);
    const formattedScore = this.formatScore(scoreData.score);
    const scoreColor = scoreData.score >= 0.7 ? '🟢' : scoreData.score >= 0.4 ? '🟡' : '🔴';

    return {
      name: 'Score',
      value: `${scoreColor} ${formattedScore} ${confidenceEmoji}`,
      inline: true,
    };
  }

  private static isImageUrl(content: string): boolean {
    const imageExtensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp'];
    const lowerContent = content.toLowerCase().trim();
    return imageExtensions.some(ext => lowerContent.endsWith(ext));
  }

  private static formatMessagePreview(content: string | null | undefined): string | null {
    if (!content) {
      return null;
    }

    const MAX_PREVIEW_LENGTH = 150;

    // Clean up whitespace and newlines
    const cleanedContent = content.trim().replace(/\s+/g, ' ');

    if (cleanedContent.length === 0) {
      return null;
    }

    // Truncate if needed
    if (cleanedContent.length > MAX_PREVIEW_LENGTH) {
      return `${cleanedContent.substring(0, MAX_PREVIEW_LENGTH)}...`;
    }

    return cleanedContent;
  }
}
