import { EmbedBuilder, Colors } from 'discord.js';
import { NoteStatus, NoteWithRatings, RatingThresholds } from './types.js';
import { MessageInfo } from './message-fetcher.js';
import { extractPlatformMessageId } from './discord-utils.js';

const PURPLE_COLOR = 0x9b59b6;

export interface NoteProgress {
  ratingProgress: string;
  raterProgress: string;
  urgencyLevel: 'critical' | 'high' | 'medium';
  urgencyColor: number;
  urgencyEmoji: string;
}

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

  static calculateProgress(
    note: NoteWithRatings,
    thresholds: RatingThresholds
  ): NoteProgress {
    const ratingCount = note.ratings_count;
    const uniqueRaters = new Set(note.ratings.map(r => r.rater_participant_id)).size;

    let urgencyLevel: 'critical' | 'high' | 'medium';
    let urgencyColor: number;
    let urgencyEmoji: string;

    if (ratingCount === 0) {
      urgencyLevel = 'critical';
      urgencyColor = Colors.Red;
      urgencyEmoji = '🔴';
    } else if (ratingCount < Math.floor(thresholds.min_ratings_needed / 2)) {
      urgencyLevel = 'high';
      urgencyColor = Colors.Orange;
      urgencyEmoji = '🟡';
    } else {
      urgencyLevel = 'medium';
      urgencyColor = Colors.Yellow;
      urgencyEmoji = '🟡';
    }

    return {
      ratingProgress: `${ratingCount}/${thresholds.min_ratings_needed}`,
      raterProgress: `${uniqueRaters}/${thresholds.min_raters_per_note}`,
      urgencyLevel,
      urgencyColor,
      urgencyEmoji,
    };
  }

  static formatNoteEmbed(
    note: NoteWithRatings,
    thresholds: RatingThresholds,
    originalMessage?: MessageInfo | null,
    guildId?: string
  ): EmbedBuilder {
    const progress = this.calculateProgress(note, thresholds);
    const createdTimestamp = Math.floor(new Date(note.created_at).getTime() / 1000);

    const isForcePublished = (note as { force_published?: boolean }).force_published === true;
    const titlePrefix = isForcePublished ? '⚠️ Admin Published • ' : `${progress.urgencyEmoji} `;

    const embed = new EmbedBuilder()
      .setColor(progress.urgencyColor)
      .setTitle(`${titlePrefix}Note #${note.id}`)
      .setDescription(this.sanitizeMarkdown(this.truncate(note.summary, 200)));

    // Extract platform message ID from request if available
    const platformMessageId = note.request
      ? extractPlatformMessageId(null, note.request.request_id)
      : null;
    const messageUrl = this.buildDiscordMessageUrl(guildId, note.channel_id, platformMessageId);

    if (note.request?.content) {
      // Original message content from linked request
      let messageValue = `"${this.sanitizeMarkdown(this.truncate(note.request.content, 200))}"`;
      if (messageUrl) {
        messageValue += `\n[View Original Message](${messageUrl})`;
      }
      embed.addFields({
        name: '💬 Original Message',
        value: messageValue,
        inline: false,
      });
    } else if (originalMessage) {
      // Fallback: fetched from Discord
      embed.addFields({
        name: '💬 Original Message',
        value: `"${this.sanitizeMarkdown(originalMessage.content)}"\n— @${this.sanitizeMarkdown(originalMessage.author)}\n[View Message](${originalMessage.url})`,
        inline: false,
      });
    } else if (originalMessage === null && platformMessageId) {
      embed.addFields({
        name: '💬 Original Message',
        value: `Message ID: ${platformMessageId} (unavailable)`,
        inline: false,
      });
    }

    const detailsLines = [
      `**Author:** \`${this.sanitizeMarkdown(this.truncate(note.author_participant_id, 30))}\``,
      `**Type:** ${this.formatClassification(note.classification)}`,
      `**Created:** <t:${createdTimestamp}:R>`,
    ];

    // Add request ID if available
    if (note.request?.request_id) {
      detailsLines.unshift(`**Request ID:** ${note.request.request_id}`);
    }

    // Add force published timestamp if applicable
    if (isForcePublished && (note as { force_published?: boolean; force_published_at?: string }).force_published_at) {
      const forcePublishedTimestamp = Math.floor(new Date((note as { force_published?: boolean; force_published_at?: string }).force_published_at!).getTime() / 1000);
      detailsLines.push(`**Admin Published:** <t:${forcePublishedTimestamp}:F>`);
    }

    embed.addFields(
      {
        name: 'Progress',
        value: `**Ratings:** ${progress.ratingProgress} • **Raters:** ${progress.raterProgress}`,
        inline: false,
      },
      {
        name: 'Details',
        value: detailsLines.join('\n'),
        inline: false,
      }
    );

    return embed;
  }

  static formatQueueEmbed(
    notes: NoteWithRatings[],
    thresholds: RatingThresholds,
    currentPage: number,
    totalNotes: number,
    notesPerPage: number,
    messageInfoMap?: Map<string, MessageInfo | null>
  ): EmbedBuilder {
    const totalPages = Math.ceil(totalNotes / notesPerPage);
    const startIndex = (currentPage - 1) * notesPerPage;

    if (notes.length === 0) {
      return new EmbedBuilder()
        .setColor(Colors.Green)
        .setTitle('📋 Notes Queue')
        .setDescription('✅ No notes need rating right now! Check back later.')
        .setFooter({ text: 'All caught up!' })
        .setTimestamp();
    }

    const embed = new EmbedBuilder()
      .setColor(Colors.Blue)
      .setTitle('📋 Notes Awaiting Your Rating')
      .setDescription(
        `Showing notes ${startIndex + 1}-${Math.min(startIndex + notes.length, totalNotes)} of ${totalNotes}`
      )
      .setFooter({
        text: `Page ${currentPage} of ${totalPages}`,
      })
      .setTimestamp();

    notes.forEach((note, index) => {
      const progress = this.calculateProgress(note, thresholds);
      const createdTimestamp = Math.floor(new Date(note.created_at).getTime() / 1000);
      const noteNumber = startIndex + index + 1;

      const isForcePublished = (note as { force_published?: boolean }).force_published === true;
      const noteTitle = isForcePublished ? '⚠️ Admin Published' : `${progress.urgencyEmoji} Note ${noteNumber}`;

      const lines: string[] = [];

      // Original message if available - from linked request or fetched from Discord
      if (note.request?.content) {
        lines.push(`💬 _"${this.sanitizeMarkdown(this.truncate(note.request.content, 80))}"_`);
      } else {
        // Fallback: try to fetch from Discord
        const messageInfo = messageInfoMap?.get(note.id);
        if (messageInfo) {
          lines.push(`💬 _"${this.sanitizeMarkdown(this.truncate(messageInfo.content, 80))}"_ — @${this.sanitizeMarkdown(messageInfo.author)}`);
        } else if (messageInfo === null) {
          lines.push(`💬 _Message unavailable_`);
        }
      }

      // Note summary
      lines.push(`**Note:** ${this.sanitizeMarkdown(this.truncate(note.summary, 100))}`);

      // Progress and metadata
      lines.push(`**ID:** ${note.id} • **Progress:** ${progress.ratingProgress} ratings • ${progress.raterProgress} raters`);
      lines.push(`**Created:** <t:${createdTimestamp}:R> • **Type:** ${this.formatClassification(note.classification)}`);

      embed.addFields({
        name: noteTitle,
        value: lines.join('\n'),
        inline: false,
      });
    });

    return embed;
  }

  static formatStatus(status: NoteStatus): string {
    switch (status) {
      case 'NEEDS_MORE_RATINGS':
        return '⏳ Awaiting More Ratings';
      case 'CURRENTLY_RATED_HELPFUL':
        return '✅ Published';
      case 'CURRENTLY_RATED_NOT_HELPFUL':
        return '❌ Not Helpful';
      default:
        return status;
    }
  }

  static formatRatedNoteEmbed(
    note: NoteWithRatings,
    userRating: boolean,
    thresholds: RatingThresholds
  ): EmbedBuilder {
    const progress = this.calculateProgress(note, thresholds);
    const createdTimestamp = Math.floor(new Date(note.created_at).getTime() / 1000);
    const ratingIndicator = userRating ? '👍 Helpful' : '👎 Not Helpful';

    const embed = new EmbedBuilder()
      .setColor(PURPLE_COLOR)
      .setTitle(`📝 Note #${note.id}`)
      .setDescription(this.sanitizeMarkdown(this.truncate(note.summary, 200)));

    embed.addFields(
      {
        name: 'Your Rating',
        value: ratingIndicator,
        inline: true,
      },
      {
        name: 'Current Status',
        value: this.formatStatus(note.status),
        inline: true,
      },
      {
        name: 'Rating Progress',
        value: `**Ratings:** ${progress.ratingProgress} • **Raters:** ${progress.raterProgress}`,
        inline: false,
      },
      {
        name: 'Details',
        value: [
          note.request?.request_id ? `**Request ID:** ${note.request.request_id}` : null,
          `**Author:** \`${this.sanitizeMarkdown(this.truncate(note.author_participant_id, 30))}\``,
          `**Type:** ${this.formatClassification(note.classification)}`,
          `**Created:** <t:${createdTimestamp}:R>`,
        ].filter(Boolean).join('\n'),
        inline: false,
      }
    );

    return embed;
  }

  private static sanitizeMarkdown(text: string): string {
    return text.replace(/([*_`~|>\\])/g, '\\$1');
  }

  private static truncate(text: string, maxLength: number): string {
    if (text.length <= maxLength) {return text;}
    return text.substring(0, maxLength - 3) + '...';
  }

  private static formatClassification(classification: string): string {
    return classification
      .split('_')
      .map(word => word.charAt(0) + word.slice(1).toLowerCase())
      .join(' ');
  }
}
