import { ActionRowBuilder, ButtonBuilder, ButtonStyle } from 'discord.js';
import type { NoteJSONAPIResponse } from './api-client.js';
import { generateShortId } from './validation.js';
import { storeViewFullContent } from './view-full-cache.js';
import { buildViewFullCustomId, truncateWithMeta } from '../utils/v2-components.js';
import { formatIdDisplay } from './proquint.js';
import { buildContextualNav } from './navigation-components.js';

const VIEW_FULL_TTL_SECONDS = 900;
const SUMMARY_PREVIEW_LENGTH = 200;

export async function buildForcePublishSuccessReply(
  noteId: string,
  note: NoteJSONAPIResponse,
  surface: string
): Promise<{
  content: string;
  components: ActionRowBuilder<ButtonBuilder>[];
}> {
  const attrs = note.data.attributes;
  const summaryPreview = truncateWithMeta(attrs.summary ?? '', SUMMARY_PREVIEW_LENGTH);

  const components: ActionRowBuilder<ButtonBuilder>[] = [];
  if (summaryPreview.isTruncated) {
    const token = generateShortId();
    const customId = buildViewFullCustomId(token);
    const stored = await storeViewFullContent(
      customId,
      summaryPreview.original,
      VIEW_FULL_TTL_SECONDS,
      { note_id: noteId, surface },
      'Failed to store force-publish view_full state in cache'
    );
    if (stored) {
      components.push(
        new ActionRowBuilder<ButtonBuilder>().addComponents(
          new ButtonBuilder()
            .setCustomId(customId)
            .setLabel('View Full')
            .setStyle(ButtonStyle.Secondary)
        ),
      );
    }
  }

  components.push(buildContextualNav('note:write'));

  const publishedAt = Math.floor(
    new Date(
      attrs.force_published_at ?? attrs.updated_at ?? attrs.created_at ?? new Date().toISOString()
    ).getTime() / 1000
  );

  return {
    content:
      `✅ **Note #${formatIdDisplay(noteId)} has been force-published**\n\n` +
      '⚠️ This note was manually published by an admin and will be marked as "Admin Published" when displayed.\n\n' +
      `**Note Summary:** ${summaryPreview.text}\n` +
      `**Status:** ${attrs.status}\n` +
      `**Published At:** <t:${publishedAt}:F>`,
    components,
  };
}
