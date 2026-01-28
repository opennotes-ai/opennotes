import { ContainerBuilder, TextDisplayBuilder } from 'discord.js';
import { NoteStatus, NoteWithRatings, RatingThresholds } from './types.js';
import { MessageInfo } from './message-fetcher.js';
import { extractPlatformMessageId } from './discord-utils.js';
import {
  V2_COLORS,
  V2_ICONS,
  createContainer,
  createSmallSeparator,
  createDivider,
  formatProgressBar,
  calculateUrgency,
  sanitizeMarkdown as v2SanitizeMarkdown,
  truncate as v2Truncate,
} from '../utils/v2-components.js';

export class NotesFormatter {
  private static buildDiscordMessageUrl(
    guildId: string | null | undefined,
    channelId: string | null | undefined,
    messageId: string | null | undefined
  ): string | null {
    if (!guildId || !channelId || !messageId) {
      return null;
    }
    return `https://discord.com/channels/${guildId}/${channelId}/${messageId}`;
  }

  static formatStatus(status: NoteStatus): string {
    switch (status) {
      case 'NEEDS_MORE_RATINGS':
        return `${V2_ICONS.PENDING_TIME} Awaiting More Ratings`;
      case 'CURRENTLY_RATED_HELPFUL':
        return `${V2_ICONS.HELPFUL} Published`;
      case 'CURRENTLY_RATED_NOT_HELPFUL':
        return `${V2_ICONS.NOT_HELPFUL} Not Helpful`;
      default:
        return status;
    }
  }

  private static formatClassification(classification: string): string {
    return classification
      .split('_')
      .map(word => word.charAt(0) + word.slice(1).toLowerCase())
      .join(' ');
  }

  static formatNoteEmbedV2(
    note: NoteWithRatings,
    thresholds: RatingThresholds,
    originalMessage?: MessageInfo | null,
    guildId?: string
  ): ContainerBuilder {
    const urgency = calculateUrgency(note.ratings_count, thresholds.min_ratings_needed);
    const uniqueRaters = new Set(note.ratings.map(r => r.rater_id)).size;
    const createdTimestamp = Math.floor(new Date(note.created_at).getTime() / 1000);

    const isForcePublished = (note as { force_published?: boolean }).force_published === true;
    const forcePublishedAt = (note as { force_published?: boolean; force_published_at?: string }).force_published_at;
    const titlePrefix = isForcePublished ? `${V2_ICONS.HIGH} **Admin Published** - ` : `${urgency.urgencyEmoji} `;

    const container = createContainer(urgency.urgencyColor);

    container.addTextDisplayComponents(
      new TextDisplayBuilder().setContent(`${titlePrefix}**Note #${note.id}**`)
    );

    container.addSeparatorComponents(createSmallSeparator());

    container.addTextDisplayComponents(
      new TextDisplayBuilder().setContent(v2SanitizeMarkdown(v2Truncate(note.summary, 200)))
    );

    const platformMessageId = note.request
      ? extractPlatformMessageId(null, note.request.request_id)
      : null;
    const messageUrl = this.buildDiscordMessageUrl(guildId, note.channel_id, platformMessageId);

    if (note.request?.content) {
      let messageValue = `"${v2SanitizeMarkdown(v2Truncate(note.request.content, 200))}"`;
      if (messageUrl) {
        messageValue += `\n[View Original Message](${messageUrl})`;
      }
      container.addSeparatorComponents(createSmallSeparator());
      container.addTextDisplayComponents(
        new TextDisplayBuilder().setContent(`**Original Message**\n${messageValue}`)
      );
    } else if (originalMessage) {
      container.addSeparatorComponents(createSmallSeparator());
      container.addTextDisplayComponents(
        new TextDisplayBuilder().setContent(
          `**Original Message**\n"${v2SanitizeMarkdown(originalMessage.content)}"\n- @${v2SanitizeMarkdown(originalMessage.author)}\n[View Message](${originalMessage.url})`
        )
      );
    } else if (originalMessage === null && platformMessageId) {
      container.addSeparatorComponents(createSmallSeparator());
      container.addTextDisplayComponents(
        new TextDisplayBuilder().setContent(`**Original Message**\nMessage ID: ${platformMessageId} (unavailable)`)
      );
    }

    container.addSeparatorComponents(createDivider());

    const progressBar = formatProgressBar(note.ratings_count, thresholds.min_ratings_needed);
    const raterBar = formatProgressBar(uniqueRaters, thresholds.min_raters_per_note);

    container.addTextDisplayComponents(
      new TextDisplayBuilder().setContent(
        `**Progress**\n${progressBar} ${note.ratings_count}/${thresholds.min_ratings_needed} ratings\n${raterBar} ${uniqueRaters}/${thresholds.min_raters_per_note} raters`
      )
    );

    container.addSeparatorComponents(createSmallSeparator());

    const detailsLines = [
      `**Author:** \`${v2SanitizeMarkdown(v2Truncate(note.author_id, 30))}\``,
      `**Type:** ${this.formatClassification(note.classification)}`,
      `**Created:** <t:${createdTimestamp}:R>`,
    ];

    if (note.request?.request_id) {
      detailsLines.unshift(`**Request ID:** ${note.request.request_id}`);
    }

    if (isForcePublished && forcePublishedAt) {
      const forcePublishedTimestamp = Math.floor(new Date(forcePublishedAt).getTime() / 1000);
      detailsLines.push(`**Admin Published:** <t:${forcePublishedTimestamp}:F>`);
    }

    container.addTextDisplayComponents(
      new TextDisplayBuilder().setContent(detailsLines.join('\n'))
    );

    return container;
  }

  static formatQueueEmbedV2(
    notes: NoteWithRatings[],
    thresholds: RatingThresholds,
    currentPage: number,
    totalNotes: number,
    notesPerPage: number,
    messageInfoMap?: Map<string, MessageInfo | null>
  ): ContainerBuilder {
    const totalPages = Math.ceil(totalNotes / notesPerPage);
    const startIndex = (currentPage - 1) * notesPerPage;

    if (notes.length === 0) {
      const container = createContainer(V2_COLORS.HELPFUL);
      container.addTextDisplayComponents(
        new TextDisplayBuilder().setContent(`${V2_ICONS.HELPFUL} **Notes Queue**`)
      );
      container.addSeparatorComponents(createSmallSeparator());
      container.addTextDisplayComponents(
        new TextDisplayBuilder().setContent(`${V2_ICONS.HELPFUL} No notes need rating right now! Check back later.`)
      );
      container.addSeparatorComponents(createSmallSeparator());
      container.addTextDisplayComponents(
        new TextDisplayBuilder().setContent('*All caught up!*')
      );
      return container;
    }

    const container = createContainer(V2_COLORS.PRIMARY);

    container.addTextDisplayComponents(
      new TextDisplayBuilder().setContent(`${V2_ICONS.PENDING} **Notes Awaiting Your Rating**`)
    );

    container.addSeparatorComponents(createSmallSeparator());

    container.addTextDisplayComponents(
      new TextDisplayBuilder().setContent(
        `Showing notes ${startIndex + 1}-${Math.min(startIndex + notes.length, totalNotes)} of ${totalNotes}`
      )
    );

    notes.forEach((note, index) => {
      const urgency = calculateUrgency(note.ratings_count, thresholds.min_ratings_needed);
      const uniqueRaters = new Set(note.ratings.map(r => r.rater_id)).size;
      const createdTimestamp = Math.floor(new Date(note.created_at).getTime() / 1000);
      const noteNumber = startIndex + index + 1;

      const isForcePublished = (note as { force_published?: boolean }).force_published === true;
      const noteTitle = isForcePublished
        ? `${V2_ICONS.HIGH} **Admin Published**`
        : `${urgency.urgencyEmoji} **Note ${noteNumber}**`;

      container.addSeparatorComponents(createDivider());

      const lines: string[] = [noteTitle];

      if (note.request?.content) {
        lines.push(`_"${v2SanitizeMarkdown(v2Truncate(note.request.content, 80))}"_`);
      } else {
        const messageInfo = messageInfoMap?.get(note.id);
        if (messageInfo) {
          lines.push(`_"${v2SanitizeMarkdown(v2Truncate(messageInfo.content, 80))}"_ - @${v2SanitizeMarkdown(messageInfo.author)}`);
        } else if (messageInfo === null) {
          lines.push(`_Message unavailable_`);
        }
      }

      lines.push(`**Note:** ${v2SanitizeMarkdown(v2Truncate(note.summary, 100))}`);

      const progressBar = formatProgressBar(note.ratings_count, thresholds.min_ratings_needed, 8);
      lines.push(`**ID:** ${note.id} | ${progressBar} ${note.ratings_count}/${thresholds.min_ratings_needed} ratings | ${uniqueRaters}/${thresholds.min_raters_per_note} raters`);
      lines.push(`**Created:** <t:${createdTimestamp}:R> | **Type:** ${this.formatClassification(note.classification)}`);

      container.addTextDisplayComponents(
        new TextDisplayBuilder().setContent(lines.join('\n'))
      );
    });

    container.addSeparatorComponents(createSmallSeparator());
    container.addTextDisplayComponents(
      new TextDisplayBuilder().setContent(`*Page ${currentPage} of ${totalPages}*`)
    );

    return container;
  }

  static formatRatedNoteEmbedV2(
    note: NoteWithRatings,
    userRating: boolean,
    thresholds: RatingThresholds
  ): ContainerBuilder {
    const uniqueRaters = new Set(note.ratings.map(r => r.rater_id)).size;
    const createdTimestamp = Math.floor(new Date(note.created_at).getTime() / 1000);
    const ratingIndicator = userRating ? '\u{1F44D} Helpful' : '\u{1F44E} Not Helpful';

    const container = createContainer(V2_COLORS.RATED);

    container.addTextDisplayComponents(
      new TextDisplayBuilder().setContent(`${V2_ICONS.RATED} **Note #${note.id}**`)
    );

    container.addSeparatorComponents(createSmallSeparator());

    container.addTextDisplayComponents(
      new TextDisplayBuilder().setContent(v2SanitizeMarkdown(v2Truncate(note.summary, 200)))
    );

    container.addSeparatorComponents(createDivider());

    container.addTextDisplayComponents(
      new TextDisplayBuilder().setContent(`**Your Rating:** ${ratingIndicator}`)
    );

    container.addTextDisplayComponents(
      new TextDisplayBuilder().setContent(`**Current Status:** ${this.formatStatus(note.status)}`)
    );

    container.addSeparatorComponents(createSmallSeparator());

    const progressBar = formatProgressBar(note.ratings_count, thresholds.min_ratings_needed);
    const raterBar = formatProgressBar(uniqueRaters, thresholds.min_raters_per_note);

    container.addTextDisplayComponents(
      new TextDisplayBuilder().setContent(
        `**Rating Progress**\n${progressBar} ${note.ratings_count}/${thresholds.min_ratings_needed} ratings\n${raterBar} ${uniqueRaters}/${thresholds.min_raters_per_note} raters`
      )
    );

    container.addSeparatorComponents(createSmallSeparator());

    const detailsLines = [
      `**Author:** \`${v2SanitizeMarkdown(v2Truncate(note.author_id, 30))}\``,
      `**Type:** ${this.formatClassification(note.classification)}`,
      `**Created:** <t:${createdTimestamp}:R>`,
    ];

    if (note.request?.request_id) {
      detailsLines.unshift(`**Request ID:** ${note.request.request_id}`);
    }

    container.addTextDisplayComponents(
      new TextDisplayBuilder().setContent(detailsLines.join('\n'))
    );

    return container;
  }
}
