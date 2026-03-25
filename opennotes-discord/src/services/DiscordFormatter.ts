import {
  Colors,
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
  ContainerBuilder,
  TextDisplayBuilder,
} from 'discord.js';
import { ServiceResult, WriteNoteResult, ViewNotesResult, RateNoteResult, StatusResult, ListRequestsResult, ErrorCode } from './types.js';
import type { RequestStatus } from '../lib/types.js';
import type {
  NoteScoreJSONAPIResponse,
  ScoringStatusJSONAPIResponse,
  ScoreConfidence,
  NoteScoreAttributes,
} from './ScoringService.js';
import { DISCORD_LIMITS } from '../lib/constants.js';
import { cache } from '../cache.js';
import { generateShortId } from '../lib/validation.js';
import { logger } from '../logger.js';
import { storeViewFullContent } from '../lib/view-full-cache.js';
import { extractPlatformMessageId } from '../lib/discord-utils.js';
import { formatIdDisplay } from '../lib/proquint.js';
import {
  V2_COLORS,
  createContainer,
  createSmallSeparator,
  createDivider,
  createTextWithButton,
  v2MessageFlags,
  formatStatusIndicator,
  createMediaGallery,
  isImageUrl as isImageUrlV2,
  truncateWithMeta,
  buildViewFullCustomId,
} from '../utils/v2-components.js';
import { buildContextualNav } from '../lib/navigation-components.js';

export class DiscordFormatter {
  private static readonly VIEW_FULL_TTL_SECONDS = 900;

  private static formatMessageIdLink(messageId: string, guildId?: string, channelId?: string): string {
    if (guildId && channelId) {
      return `[${messageId}](https://discord.com/channels/${guildId}/${channelId}/${messageId})`;
    }
    return messageId;
  }

  private static async addRequestPreviewComponent(
    container: ContainerBuilder,
    fieldLines: string[],
    request: ListRequestsResult['requests'][number]
  ): Promise<void> {
    const contentPreview = this.formatMessagePreview(request.content);
    if (!contentPreview) {
      container.addTextDisplayComponents(
        new TextDisplayBuilder().setContent(fieldLines.join('\n'))
      );
      return;
    }

    const previewPrefix = '**Original message content:** ';
    const maxPreviewLength = Math.max(
      100,
      DISCORD_LIMITS.MAX_TEXT_DISPLAY_LENGTH - `${fieldLines.join('\n')}\n${previewPrefix}`.length
    );
    const truncatedPreview = truncateWithMeta(contentPreview, maxPreviewLength);
    const renderedContent = [...fieldLines, `${previewPrefix}${truncatedPreview.text}`].join('\n');

    if (!truncatedPreview.isTruncated) {
      container.addTextDisplayComponents(
        new TextDisplayBuilder().setContent(renderedContent)
      );
      return;
    }

    const token = generateShortId();
    const customId = buildViewFullCustomId(token);

    try {
      const stored = await storeViewFullContent(
        customId,
        request.content ?? truncatedPreview.original,
        this.VIEW_FULL_TTL_SECONDS,
        { request_id: request.request_id },
        'Failed to store request preview view_full state in cache'
      );
      if (!stored) {
        container.addTextDisplayComponents(
          new TextDisplayBuilder().setContent(renderedContent)
        );
        return;
      }
      container.addSectionComponents(
        createTextWithButton(
          renderedContent,
          new ButtonBuilder()
            .setCustomId(customId)
            .setLabel('View Full')
            .setStyle(ButtonStyle.Secondary)
        )
      );
    } catch {
      container.addTextDisplayComponents(
        new TextDisplayBuilder().setContent(renderedContent)
      );
    }
  }

  static formatStatusSuccessV2(result: StatusResult): {
    container: ContainerBuilder;
    components: ReturnType<ContainerBuilder['toJSON']>[];
    flags: number;
  } {
    const hours = Math.floor(result.bot.uptime / 3600);
    const minutes = Math.floor((result.bot.uptime % 3600) / 60);
    const seconds = Math.floor(result.bot.uptime % 60);

    const botInfo = [
      `**Uptime:** ${hours}h ${minutes}m ${seconds}s`,
      `**Cache Size:** ${result.bot.cacheSize} entries`,
    ];

    if (result.bot.guilds !== undefined) {
      botInfo.push(`**Guilds:** ${result.bot.guilds}`);
    }

    const isServerHealthy = result.server.status === 'healthy';
    const serverInfo = [
      formatStatusIndicator(isServerHealthy, `Status: ${result.server.status}`),
      `**Version:** ${result.server.version}`,
      `**Latency:** ${result.server.latency}ms`,
    ];

    const container = createContainer(V2_COLORS.INFO)
      .addTextDisplayComponents(
        new TextDisplayBuilder().setContent('## Bot Status')
      )
      .addSeparatorComponents(createSmallSeparator())
      .addTextDisplayComponents(
        new TextDisplayBuilder().setContent(`**Bot Info**\n${botInfo.join('\n')}`)
      )
      .addSeparatorComponents(createDivider())
      .addTextDisplayComponents(
        new TextDisplayBuilder().setContent(`**API Status**\n${serverInfo.join('\n')}`)
      );

    return {
      container,
      components: [container.toJSON()],
      flags: v2MessageFlags({ ephemeral: true }),
    };
  }

  static formatScoringStatusV2(response: ScoringStatusJSONAPIResponse): {
    textDisplay: TextDisplayBuilder;
    separator: ReturnType<typeof createDivider>;
  } {
    const status = response.data.attributes;
    const tierInfo = status.active_tier;
    const nextTier = tierInfo.level < 5 ? tierInfo.level + 1 : null;
    const nextTierInfo = status.next_tier_upgrade;

    const scoringLines = [
      `**Current Tier:** ${tierInfo.level} (${tierInfo.name})`,
      `**Note Count:** ${status.current_note_count}`,
      `**Data Confidence:** ${status.data_confidence}`,
    ];

    if (nextTierInfo && nextTier) {
      scoringLines.push(
        `**Progress to Tier ${nextTier}:** ${status.current_note_count}/${nextTierInfo.notes_needed} notes (${nextTierInfo.notes_to_upgrade} more needed)`
      );
    } else {
      scoringLines.push('**Status:** Maximum tier reached');
    }

    const textDisplay = new TextDisplayBuilder().setContent(
      `**Scoring System**\n${scoringLines.join('\n')}`
    );

    return {
      textDisplay,
      separator: createDivider(),
    };
  }

  static formatWriteNoteSuccessV2(
    result: WriteNoteResult,
    messageId: string,
    guildId?: string,
    channelId?: string,
    navContext?: string
  ): {
    container: ContainerBuilder;
    components: ReturnType<ContainerBuilder['toJSON']>[];
    flags: number;
  } {
    const messageIdDisplay = this.formatMessageIdLink(messageId, guildId, channelId);
    const noteId = result.note.data.id;
    const attrs = result.note.data.attributes;

    const metadataLines = [
      `**Message ID:** ${messageIdDisplay}`,
      `**Author:** <@${attrs.author_id}>`,
      `**Note ID:** ${formatIdDisplay(noteId)}`,
    ];

    const container = createContainer(V2_COLORS.HELPFUL)
      .addTextDisplayComponents(
        new TextDisplayBuilder().setContent('## Community Note Created')
      )
      .addSeparatorComponents(createSmallSeparator())
      .addTextDisplayComponents(
        new TextDisplayBuilder().setContent(attrs.summary)
      )
      .addSeparatorComponents(createDivider())
      .addTextDisplayComponents(
        new TextDisplayBuilder().setContent(metadataLines.join('\n'))
      );

    if (navContext) {
      container.addActionRowComponents(buildContextualNav(navContext));
    }

    return {
      container,
      components: [container.toJSON()],
      flags: v2MessageFlags(),
    };
  }

  static formatViewNotesSuccessV2(
    result: ViewNotesResult,
    scoresMap?: Map<string, NoteScoreAttributes>,
    navContext?: string
  ): {
    container: ContainerBuilder;
    components: ReturnType<ContainerBuilder['toJSON']>[];
    flags: number;
  } {
    const container = createContainer(V2_COLORS.INFO);

    if (result.notes.data.length === 0) {
      container.addTextDisplayComponents(
        new TextDisplayBuilder().setContent('## Community Notes\n\nNo notes found for this message.')
      );

      if (navContext) {
        container.addActionRowComponents(buildContextualNav(navContext));
      }

      return {
        container,
        components: [container.toJSON()],
        flags: v2MessageFlags(),
      };
    }

    container.addTextDisplayComponents(
      new TextDisplayBuilder().setContent('## Community Notes')
    );

    for (const note of result.notes.data.slice(0, DISCORD_LIMITS.MAX_EMBEDS_PER_MESSAGE)) {
      container.addSeparatorComponents(createSmallSeparator());

      const noteLines = [
        `**Note #${formatIdDisplay(note.id)}**`,
        note.attributes.summary,
        '',
        `**Author:** <@${note.attributes.author_id}>`,
        `**Ratings:** \u{1F44D} ${note.attributes.ratings_count}`,
      ];

      const scoreData = scoresMap?.get(note.id);
      if (scoreData) {
        const scoreColor = scoreData.score >= 0.7 ? '\u{1F7E2}' : scoreData.score >= 0.4 ? '\u{1F7E1}' : '\u{1F534}';
        const formattedScore = this.formatScore(scoreData.score);
        noteLines.push(`**Score:** ${scoreColor} ${formattedScore}`);
      }

      container.addTextDisplayComponents(
        new TextDisplayBuilder().setContent(noteLines.join('\n'))
      );

      if (note.attributes.summary && isImageUrlV2(note.attributes.summary)) {
        const gallery = createMediaGallery([note.attributes.summary]);
        if (gallery) {
          container.addMediaGalleryComponents(gallery);
        }
      }
    }

    if (navContext) {
      container.addActionRowComponents(buildContextualNav(navContext));
    }

    return {
      container,
      components: [container.toJSON()],
      flags: v2MessageFlags(),
    };
  }

  static formatErrorV2<T>(result: ServiceResult<T>): {
    container: ContainerBuilder;
    components: ReturnType<ContainerBuilder['toJSON']>[];
    flags: number;
  } {
    const container = createContainer(V2_COLORS.CRITICAL);

    if (!result.error) {
      container.addTextDisplayComponents(
        new TextDisplayBuilder().setContent('## Error\n\nAn unknown error occurred.')
      );
      return {
        container,
        components: [container.toJSON()],
        flags: v2MessageFlags({ ephemeral: true }),
      };
    }

    const errorLines: string[] = ['## Error'];

    switch (result.error.code as ErrorCode) {
      case ErrorCode.RATE_LIMIT_EXCEEDED: {
        const resetAt = result.error.details?.resetAt;
        const resetTime = typeof resetAt === 'number' ? Math.floor(resetAt / 1000) : 0;
        errorLines.push(`Rate limit exceeded. Try again <t:${resetTime}:R>`);
        break;
      }

      case ErrorCode.CONFLICT: {
        errorLines.push(result.error.message);
        if (result.error.details?.helpText) {
          errorLines.push('', `\u{1F4A1} ${String(result.error.details.helpText)}`);
        }
        if (result.error.details?.errorId) {
          errorLines.push('', `**Error ID:** \`${String(result.error.details.errorId)}\``);
        }
        break;
      }

      default:
        errorLines.push(result.error.message || 'An unexpected error occurred.');
    }

    container.addTextDisplayComponents(
      new TextDisplayBuilder().setContent(errorLines.join('\n'))
    );

    return {
      container,
      components: [container.toJSON()],
      flags: v2MessageFlags({ ephemeral: true }),
    };
  }

  static formatNoteScoreV2(response: NoteScoreJSONAPIResponse, navContext?: string): {
    container: ContainerBuilder;
    components: ReturnType<ContainerBuilder['toJSON']>[];
    flags: number;
  } {
    const scoreData = response.data.attributes;
    const noteId = response.data.id;
    const scoreColor = this.getScoreColor(scoreData.score);
    const formattedScore = this.formatScore(scoreData.score);
    const confidenceLabel = this.getConfidenceLabel(scoreData.confidence as ScoreConfidence);
    const confidenceEmoji = this.getConfidenceEmoji(scoreData.confidence as ScoreConfidence);

    const container = createContainer(scoreColor)
      .addTextDisplayComponents(
        new TextDisplayBuilder().setContent(`## Note Score: ${formattedScore}`)
      )
      .addSeparatorComponents(createSmallSeparator())
      .addTextDisplayComponents(
        new TextDisplayBuilder().setContent(this.getScoreExplanation(scoreData))
      )
      .addSeparatorComponents(createDivider())
      .addTextDisplayComponents(
        new TextDisplayBuilder().setContent([
          `**Note ID:** ${formatIdDisplay(noteId)}`,
          `**Score:** ${formattedScore} (0.0-1.0)`,
          `**Confidence:** ${confidenceEmoji} ${confidenceLabel}`,
          `**Rating Count:** ${scoreData.rating_count}`,
          `**Algorithm:** ${scoreData.algorithm}`,
          `**Tier:** Tier ${scoreData.tier}`,
        ].join('\n'))
      );

    if (navContext) {
      container.addActionRowComponents(buildContextualNav(navContext));
    }

    return {
      container,
      components: [container.toJSON()],
      flags: v2MessageFlags(),
    };
  }

  static formatRateNoteSuccessV2(
    result: RateNoteResult,
    noteId: string,
    helpful: boolean,
    navContext?: string
  ): {
    container: ContainerBuilder;
    components: ReturnType<ContainerBuilder['toJSON']>[];
    flags: number;
  } {
    const color = helpful ? V2_COLORS.HELPFUL : V2_COLORS.NOT_HELPFUL;
    const ratingText = helpful ? 'Helpful' : 'Not Helpful';

    const container = createContainer(color)
      .addTextDisplayComponents(
        new TextDisplayBuilder().setContent('## Rating Submitted')
      )
      .addSeparatorComponents(createSmallSeparator())
      .addTextDisplayComponents(
        new TextDisplayBuilder().setContent(`You rated this note as **${ratingText}**`)
      )
      .addSeparatorComponents(createDivider())
      .addTextDisplayComponents(
        new TextDisplayBuilder().setContent([
          `**Note ID:** ${formatIdDisplay(noteId)}`,
          `**Rated by:** <@${result.rating.data.attributes.rater_id}>`,
        ].join('\n'))
      );

    if (navContext) {
      container.addActionRowComponents(buildContextualNav(navContext));
    }

    return {
      container,
      components: [container.toJSON()],
      flags: v2MessageFlags(),
    };
  }

  static formatRequestNoteSuccessV2(
    messageId: string,
    userId: string,
    reason?: string,
    guildId?: string,
    channelId?: string,
    navContext?: string
  ): {
    container: ContainerBuilder;
    components: ReturnType<ContainerBuilder['toJSON']>[];
    flags: number;
  } {
    const messageIdDisplay = this.formatMessageIdLink(messageId, guildId, channelId);

    const metadataLines = [
      `**Message ID:** ${messageIdDisplay}`,
      `**Requested by:** <@${userId}>`,
    ];

    if (reason) {
      metadataLines.push(`**Reason:** ${reason}`);
    }

    const container = createContainer(V2_COLORS.HELPFUL)
      .addTextDisplayComponents(
        new TextDisplayBuilder().setContent('## Note Request Submitted')
      )
      .addSeparatorComponents(createSmallSeparator())
      .addTextDisplayComponents(
        new TextDisplayBuilder().setContent('Your request for a community note has been recorded.')
      )
      .addSeparatorComponents(createDivider())
      .addTextDisplayComponents(
        new TextDisplayBuilder().setContent(metadataLines.join('\n'))
      );

    if (navContext) {
      container.addActionRowComponents(buildContextualNav(navContext));
    }

    return {
      container,
      components: [container.toJSON()],
      flags: v2MessageFlags(),
    };
  }

  static async formatListRequestsSuccessV2(
    result: ListRequestsResult,
    options?: { status?: string; myRequestsOnly?: boolean; communityServerId?: string; guildId?: string; isAdmin?: boolean },
    navContext?: string
  ): Promise<{
    container: ContainerBuilder;
    components: ReturnType<ContainerBuilder['toJSON']>[];
    flags: number;
    actionRows: ActionRowBuilder<ButtonBuilder>[];
    stateId?: string;
  }> {
    const totalPages = Math.ceil(result.total / result.size);

    const container = createContainer(V2_COLORS.INFO);

    if (result.requests.length === 0) {
      container.addTextDisplayComponents(
        new TextDisplayBuilder().setContent('## Note Requests\n\nNo requests found.')
      );
      if (navContext) {
        container.addActionRowComponents(buildContextualNav(navContext));
      }
      return {
        container,
        components: [container.toJSON()],
        flags: v2MessageFlags(),
        actionRows: [],
      };
    }

    container.addTextDisplayComponents(
      new TextDisplayBuilder().setContent('## Note Requests')
    );

    container.addSeparatorComponents(createSmallSeparator());

    container.addTextDisplayComponents(
      new TextDisplayBuilder().setContent(
        `Showing requests ${(result.page - 1) * result.size + 1}-${Math.min(result.page * result.size, result.total)} of ${result.total}\n\nEach pending request has action buttons directly below it.`
      )
    );

    for (const request of result.requests.slice(0, 5)) {
      const statusEmojiMap: Record<RequestStatus, string> = {
        PENDING: '\u{23F3}',
        IN_PROGRESS: '\u{1F504}',
        COMPLETED: '\u{2705}',
        FAILED: '\u{274C}',
      };
      const statusEmoji = statusEmojiMap[request.status] || '\u{2753}';

      const timestamp = Math.floor(new Date(request.requested_at).getTime() / 1000);
      const requestedBy = `<@${request.requested_by}>`;
      const noteInfo = request.note_id ? `Note: ${formatIdDisplay(request.note_id)}` : 'No note yet';
      const effectiveMessageId = extractPlatformMessageId(request.platform_message_id ?? null, request.request_id);

      container.addSeparatorComponents(createDivider());

      const fieldLines = [
        `${statusEmoji} **Request #${formatIdDisplay(request.id)}**`,
      ];

      if (effectiveMessageId && request.platform_channel_id && options?.guildId) {
        const jumpUrl = `https://discord.com/channels/${options.guildId}/${request.platform_channel_id}/${effectiveMessageId}`;
        fieldLines.push(`[View Original Message](${jumpUrl})`);
      }

      fieldLines.push(
        `**Status:** ${request.status}`,
      );
      if (options?.isAdmin) {
        fieldLines.push(`**Requester (only visible to admins):** ${requestedBy}`);
      }
      fieldLines.push(
        `**Requested:** <t:${timestamp}:R>`,
        `**${noteInfo}**`,
      );

      await this.addRequestPreviewComponent(container, fieldLines, request);

      if (request.content && isImageUrlV2(request.content)) {
        const gallery = createMediaGallery([request.content]);
        if (gallery) {
          container.addMediaGalleryComponents(gallery);
        }
      }

      if (effectiveMessageId && request.status === 'PENDING') {
        const writeNoteNotMisleadingShortId = generateShortId();
        const writeNoteMisinformedShortId = generateShortId();
        const aiWriteNoteShortId = generateShortId();

        const writeNoteNotMisleadingCacheKey = `write_note_state:${writeNoteNotMisleadingShortId}`;
        const writeNoteMisinformedCacheKey = `write_note_state:${writeNoteMisinformedShortId}`;
        const aiWriteNoteCacheKey = `write_note_state:${aiWriteNoteShortId}`;
        const ttl = 900;

        try {
          await cache.set(writeNoteNotMisleadingCacheKey, request.id, ttl);
          await cache.set(writeNoteMisinformedCacheKey, request.id, ttl);
          await cache.set(aiWriteNoteCacheKey, request.id, ttl);
        } catch (error) {
          logger.error('Failed to store write note button state in cache', {
            error: error instanceof Error ? error.message : String(error),
            request_id: request.id,
          });
        }

        container.addTextDisplayComponents(
          new TextDisplayBuilder().setContent('**Write a note yourself.** The original message is:')
        );
        container.addActionRowComponents(
          new ActionRowBuilder<ButtonBuilder>().addComponents(
            new ButtonBuilder()
              .setCustomId(`write_note:NOT_MISLEADING:${writeNoteNotMisleadingShortId}`)
              .setLabel('Not Misleading')
              .setStyle(ButtonStyle.Success),
            new ButtonBuilder()
              .setCustomId(`write_note:MISINFORMED_OR_POTENTIALLY_MISLEADING:${writeNoteMisinformedShortId}`)
              .setLabel('Misinformed or Misleading')
              .setStyle(ButtonStyle.Danger),
          )
        );
        container.addTextDisplayComponents(
          new TextDisplayBuilder().setContent('Let AI write the note:')
        );
        container.addActionRowComponents(
          new ActionRowBuilder<ButtonBuilder>().addComponents(
            new ButtonBuilder()
              .setCustomId(`ai_write_note:${aiWriteNoteShortId}`)
              .setLabel('AI')
              .setEmoji({ name: '✨' })
              .setStyle(ButtonStyle.Primary),
          )
        );
      } else if (request.status === 'COMPLETED') {
        container.addTextDisplayComponents(
          new TextDisplayBuilder().setContent('*Notes have been written for this request.*')
        );
      } else if (request.status === 'IN_PROGRESS') {
        container.addTextDisplayComponents(
          new TextDisplayBuilder().setContent('*A note is being written for this request.*')
        );
      }
    }

    container.addSeparatorComponents(createDivider());
    container.addTextDisplayComponents(
      new TextDisplayBuilder().setContent(`*Page ${result.page} of ${totalPages} | Total: ${result.total} requests*`)
    );

    let stateId: string | undefined;
    if (totalPages > 1) {
      stateId = generateShortId();
      const filterState = {
        status: options?.status,
        myRequestsOnly: options?.myRequestsOnly,
        communityServerId: options?.communityServerId,
      };

      const cacheKey = `pagination:${stateId}`;
      const ttl = 900;

      try {
        await cache.set(cacheKey, filterState, ttl);
      } catch (error) {
        logger.error('Failed to store pagination state in cache', {
          error: error instanceof Error ? error.message : String(error),
          stateId,
        });
      }

      const paginationRow = new ActionRowBuilder<ButtonBuilder>().addComponents(
        new ButtonBuilder()
          .setCustomId(`request_queue_page:${result.page - 1}:${stateId}`)
          .setLabel('\u25C0')
          .setStyle(ButtonStyle.Secondary)
          .setDisabled(result.page <= 1),
        new ButtonBuilder()
          .setCustomId('page:current')
          .setLabel(`${result.page}/${totalPages}`)
          .setStyle(ButtonStyle.Secondary)
          .setDisabled(true),
        new ButtonBuilder()
          .setCustomId(`request_queue_page:${result.page + 1}:${stateId}`)
          .setLabel('\u25B6')
          .setStyle(ButtonStyle.Secondary)
          .setDisabled(result.page >= totalPages)
      );
      container.addActionRowComponents(paginationRow);
    }

    if (navContext) {
      container.addActionRowComponents(buildContextualNav(navContext));
    }

    return {
      container,
      components: [container.toJSON()],
      flags: v2MessageFlags(),
      actionRows: [],
      stateId,
    };
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

  private static getScoreExplanation(scoreData: NoteScoreAttributes): string {
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

  private static formatMessagePreview(content: string | null | undefined): string | null {
    if (!content) {
      return null;
    }

    // Clean up whitespace and newlines
    const cleanedContent = content.trim().replace(/\s+/g, ' ');

    if (cleanedContent.length === 0) {
      return null;
    }

    return cleanedContent;
  }
}
