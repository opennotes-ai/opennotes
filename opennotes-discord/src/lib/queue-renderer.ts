import {
  ActionRowBuilder,
  ButtonBuilder,
  ThreadChannel,
  Message,
  ContainerBuilder,
  TextDisplayBuilder,
  ButtonStyle,
} from 'discord.js';
import { logger } from '../logger.js';
import {
  V2_COLORS,
  V2_ICONS,
  v2MessageFlags,
  createDivider,
  createSmallSeparator,
  V2_LIMITS,
} from '../utils/v2-components.js';

/**
 * Configuration for pagination controls
 */
export interface PaginationConfig {
  currentPage: number;
  totalPages: number;
  previousButtonId: string;
  nextButtonId: string;
  previousLabel?: string;
  nextLabel?: string;
}

/**
 * Represents a single item in a v2 queue using Components v2
 */
export interface QueueItemV2 {
  id: string;
  title: string;
  summary: string;
  urgencyEmoji: string;
  ratingButtons: ActionRowBuilder<ButtonBuilder>;
  mediaUrls?: string[];
}

/**
 * Configuration for the v2 queue summary
 */
export interface QueueSummaryV2 {
  title: string;
  subtitle: string;
  stats: string;
}

/**
 * Result of rendering a v2 queue - simplified structure
 */
export interface QueueRenderResultV2 {
  messages: Message[];
  totalItems: number;
}

/**
 * Components v2 queue renderer for Discord threads
 *
 * Renders queue items in a single ContainerBuilder message (or minimal messages
 * when batching is needed). This provides a cleaner UI and simpler state management
 * compared to the multi-message v1 approach.
 *
 * Structure per container:
 * 1. Header (title, subtitle, stats)
 * 2. For each item: SectionBuilder + ActionRowBuilder (rating buttons)
 * 3. Pagination ActionRowBuilder (if multiple pages)
 *
 * Constraints:
 * - Max 4 notes per container (4 rating rows + 1 pagination row = 5 action rows)
 * - Uses emoji in text for per-note urgency (single container = single accent color)
 */
export class QueueRendererV2 {
  /**
   * Renders a v2 queue as single or minimal messages
   *
   * @param thread - The Discord thread to send messages to
   * @param summary - Configuration for the summary header
   * @param items - Array of queue items to render
   * @param pagination - Optional pagination configuration
   * @returns Object containing rendered messages and item count
   */
  static async render(
    thread: ThreadChannel,
    summary: QueueSummaryV2,
    items: QueueItemV2[],
    pagination?: PaginationConfig
  ): Promise<QueueRenderResultV2> {
    const batches = this.batchItems(items, pagination);
    const messages: Message[] = [];

    for (let i = 0; i < batches.length; i++) {
      const batch = batches[i];
      const isFirstBatch = i === 0;
      const isLastBatch = i === batches.length - 1;

      const container = this.buildContainer(
        isFirstBatch ? summary : undefined,
        batch,
        isLastBatch ? pagination : undefined
      );

      const message = await thread.send({
        components: [container],
        flags: v2MessageFlags(),
      });

      messages.push(message);
    }

    return {
      messages,
      totalItems: items.length,
    };
  }

  /**
   * Updates an existing v2 queue with new data
   *
   * @param result - The previous render result to update
   * @param summary - New summary configuration
   * @param items - New array of queue items
   * @param pagination - New pagination configuration
   * @returns Updated render result
   */
  static async update(
    result: QueueRenderResultV2,
    summary: QueueSummaryV2,
    items: QueueItemV2[],
    pagination?: PaginationConfig
  ): Promise<QueueRenderResultV2> {
    const batches = this.batchItems(items, pagination);
    const existingMessages = result.messages;
    const newMessages: Message[] = [];

    for (let i = 0; i < batches.length; i++) {
      const batch = batches[i];
      const isFirstBatch = i === 0;
      const isLastBatch = i === batches.length - 1;

      const container = this.buildContainer(
        isFirstBatch ? summary : undefined,
        batch,
        isLastBatch ? pagination : undefined
      );

      if (i < existingMessages.length) {
        await existingMessages[i].edit({
          components: [container],
          flags: v2MessageFlags(),
        });
        newMessages.push(existingMessages[i]);
      } else {
        const thread = existingMessages[0].channel as ThreadChannel;
        const message = await thread.send({
          components: [container],
          flags: v2MessageFlags(),
        });
        newMessages.push(message);
      }
    }

    for (let i = batches.length; i < existingMessages.length; i++) {
      await existingMessages[i].delete().catch((err: unknown) => {
        const errMessage = err instanceof Error ? err.message : String(err);
        logger.warn('Failed to delete excess message during update', { error: errMessage });
      });
    }

    return {
      messages: newMessages,
      totalItems: items.length,
    };
  }

  /**
   * Collects all messages from a v2 render result
   */
  static getAllMessages(result: QueueRenderResultV2): Message[] {
    return result.messages;
  }

  /**
   * Deletes all messages from a v2 render result
   */
  static async cleanup(result: QueueRenderResultV2): Promise<void> {
    const deletePromises = result.messages.map((msg) =>
      msg.delete().catch((err: unknown) => {
        const errMessage = err instanceof Error ? err.message : String(err);
        logger.warn('Failed to delete message during cleanup', { error: errMessage });
      })
    );

    await Promise.all(deletePromises);
  }

  /**
   * Batches items to fit within Discord's 5 action row limit per container.
   * Each item uses 1 action row (rating buttons).
   * Pagination uses 1 action row if present.
   * We consistently use 4 items max to leave room for pagination.
   */
  private static batchItems(
    items: QueueItemV2[],
    _pagination?: PaginationConfig
  ): QueueItemV2[][] {
    const maxItemsPerBatch = V2_LIMITS.MAX_NOTES_PER_QUEUE_PAGE;

    if (items.length === 0) {
      return [[]];
    }

    const batches: QueueItemV2[][] = [];
    for (let i = 0; i < items.length; i += maxItemsPerBatch) {
      batches.push(items.slice(i, i + maxItemsPerBatch));
    }

    return batches;
  }

  /**
   * Builds a ContainerBuilder for a batch of items
   */
  private static buildContainer(
    summary: QueueSummaryV2 | undefined,
    items: QueueItemV2[],
    pagination?: PaginationConfig
  ): ContainerBuilder {
    const container = new ContainerBuilder().setAccentColor(V2_COLORS.PRIMARY);

    if (summary) {
      container.addTextDisplayComponents(
        new TextDisplayBuilder().setContent(`## ${summary.title}`),
        new TextDisplayBuilder().setContent(`**${summary.subtitle}**`),
        new TextDisplayBuilder().setContent(summary.stats)
      );
      container.addSeparatorComponents(createDivider());
    }

    for (let i = 0; i < items.length; i++) {
      const item = items[i];

      container.addTextDisplayComponents(
        new TextDisplayBuilder().setContent(
          `${item.urgencyEmoji} **${item.title}**\n${item.summary}`
        )
      );

      container.addActionRowComponents(item.ratingButtons);

      if (i < items.length - 1) {
        container.addSeparatorComponents(createSmallSeparator());
      }
    }

    if (pagination && pagination.totalPages > 1) {
      container.addSeparatorComponents(createDivider());
      container.addActionRowComponents(this.createPaginationRow(pagination));
    }

    return container;
  }

  /**
   * Creates a pagination button row for v2 containers
   */
  private static createPaginationRow(
    config: PaginationConfig
  ): ActionRowBuilder<ButtonBuilder> {
    const previousButton = new ButtonBuilder()
      .setCustomId(config.previousButtonId)
      .setLabel(config.previousLabel || V2_ICONS.NAV_PREVIOUS)
      .setStyle(ButtonStyle.Secondary)
      .setDisabled(config.currentPage <= 1);

    const pageIndicator = new ButtonBuilder()
      .setCustomId('page:current')
      .setLabel(`${config.currentPage}/${config.totalPages}`)
      .setStyle(ButtonStyle.Secondary)
      .setDisabled(true);

    const nextButton = new ButtonBuilder()
      .setCustomId(config.nextButtonId)
      .setLabel(config.nextLabel || V2_ICONS.NAV_NEXT)
      .setStyle(ButtonStyle.Secondary)
      .setDisabled(config.currentPage >= config.totalPages);

    return new ActionRowBuilder<ButtonBuilder>().addComponents(
      previousButton,
      pageIndicator,
      nextButton
    );
  }
}
