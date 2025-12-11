import {
  EmbedBuilder,
  ActionRowBuilder,
  ButtonBuilder,
  ThreadChannel,
  Message,
  MessageCreateOptions,
  MessageEditOptions,
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
 * Represents a single item in a queue (e.g., a note, request, etc.)
 *
 * @deprecated This v1 type uses EmbedBuilder. Use QueueItemV2 instead for new code.
 * Still used by: /list requests, /list top-notes
 * Migration tracked in: docs/components-v2-design.md
 */
export interface QueueItem {
  id: string;
  embed: EmbedBuilder;
  buttons: ActionRowBuilder<ButtonBuilder>[];
}

/**
 * Configuration for the queue summary message
 *
 * @deprecated This v1 type uses EmbedBuilder. Use QueueSummaryV2 instead for new code.
 * Still used by: /list requests, /list top-notes
 * Migration tracked in: docs/components-v2-design.md
 */
export interface QueueSummary {
  embed: EmbedBuilder;
  buttons?: ActionRowBuilder<ButtonBuilder>[];
}

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
 * Result of rendering a queue with multiple messages
 */
export interface QueueRenderResult {
  summaryMessage: Message;
  itemMessages: Map<string, Message>; // Maps item ID to its message
  paginationMessage: Message | null;
}

/**
 * Multi-message queue renderer for Discord threads
 *
 * Renders queue items as separate messages to avoid Discord's action row limitations.
 * Each item gets its own message with an embed and buttons, allowing unlimited items per page.
 *
 * Message structure:
 * 1. Summary message (page info, totals, filters)
 * 2. One message per item (embed + action buttons)
 * 3. Pagination message (Previous/Next buttons) - only if multiple pages exist
 *
 * Benefits:
 * - No action row limits (each message can have up to 5 action rows)
 * - Better UX: buttons directly below each item
 * - Reusable for any queue type (notes, requests, etc.)
 * - Each message can have independent collectors
 *
 * @deprecated This v1 renderer uses EmbedBuilder. Use QueueRendererV2 instead for new code.
 * Still used by: /list requests, /list top-notes
 * Migration tracked in: docs/components-v2-design.md
 */
export class QueueRenderer {
  /**
   * Renders a queue as multiple messages in a thread
   *
   * @param thread - The Discord thread to send messages to
   * @param summary - Configuration for the summary message
   * @param items - Array of queue items to render
   * @param pagination - Optional pagination configuration
   * @returns Object containing all rendered messages
   */
  static async render(
    thread: ThreadChannel,
    summary: QueueSummary,
    items: QueueItem[],
    pagination?: PaginationConfig
  ): Promise<QueueRenderResult> {
    // 1. Send summary message
    const summaryPayload: MessageCreateOptions = { embeds: [summary.embed] };
    if (summary.buttons && summary.buttons.length > 0) {
      summaryPayload.components = summary.buttons;
    }

    const summaryMessage = await thread.send(summaryPayload);

    // 2. Send one message per item
    const itemMessages = new Map<string, Message>();

    for (const item of items) {
      const itemPayload: MessageCreateOptions = { embeds: [item.embed] };
      if (item.buttons.length > 0) {
        itemPayload.components = item.buttons;
      }

      const message = await thread.send(itemPayload);
      itemMessages.set(item.id, message);
    }

    // 3. Send pagination message if needed
    let paginationMessage: Message | null = null;

    if (pagination && pagination.totalPages > 1) {
      const paginationRow = this.createPaginationRow(pagination);
      paginationMessage = await thread.send({
        content: `Page ${pagination.currentPage} of ${pagination.totalPages}`,
        components: [paginationRow],
      });
    }

    return {
      summaryMessage,
      itemMessages,
      paginationMessage,
    };
  }

  /**
   * Updates an existing queue with new data
   *
   * This method efficiently updates the queue by:
   * - Updating the summary message
   * - Deleting old item messages
   * - Creating new item messages
   * - Updating the pagination message
   *
   * @param result - The previous render result to update
   * @param summary - New summary configuration
   * @param items - New array of queue items
   * @param pagination - New pagination configuration
   * @returns Updated render result
   */
  static async update(
    result: QueueRenderResult,
    summary: QueueSummary,
    items: QueueItem[],
    pagination?: PaginationConfig
  ): Promise<QueueRenderResult> {
    // 1. Update summary message
    const summaryPayload: MessageEditOptions = { embeds: [summary.embed] };
    if (summary.buttons && summary.buttons.length > 0) {
      summaryPayload.components = summary.buttons;
    }
    await result.summaryMessage.edit(summaryPayload);

    // 2. Delete old item messages
    const deletePromises: Promise<unknown>[] = [];
    for (const message of result.itemMessages.values()) {
      deletePromises.push(
        message.delete().catch((err: unknown) => {
          const errMessage = err instanceof Error ? err.message : String(err);
          logger.warn('Failed to delete item message', { error: errMessage });
        })
      );
    }
    await Promise.all(deletePromises);

    // 3. Create new item messages
    const itemMessages = new Map<string, Message>();
    const thread = result.summaryMessage.channel as ThreadChannel;

    for (const item of items) {
      const itemPayload: MessageCreateOptions = { embeds: [item.embed] };
      if (item.buttons.length > 0) {
        itemPayload.components = item.buttons;
      }

      const message = await thread.send(itemPayload);
      itemMessages.set(item.id, message);
    }

    // 4. Update pagination message
    let paginationMessage: Message | null = null;

    if (pagination && pagination.totalPages > 1) {
      const paginationRow = this.createPaginationRow(pagination);
      const paginationContent = `Page ${pagination.currentPage} of ${pagination.totalPages}`;

      if (result.paginationMessage) {
        // Update existing pagination message
        await result.paginationMessage.edit({
          content: paginationContent,
          components: [paginationRow],
        });
        paginationMessage = result.paginationMessage;
      } else {
        // Create new pagination message
        paginationMessage = await thread.send({
          content: paginationContent,
          components: [paginationRow],
        });
      }
    } else if (result.paginationMessage) {
      // Delete pagination message if no longer needed
      await result.paginationMessage.delete().catch((err: unknown) => {
        const errMessage = err instanceof Error ? err.message : String(err);
        logger.warn('Failed to delete pagination message', { error: errMessage });
      });
    }

    return {
      summaryMessage: result.summaryMessage,
      itemMessages,
      paginationMessage,
    };
  }

  /**
   * Creates a pagination button row
   */
  private static createPaginationRow(
    config: PaginationConfig
  ): ActionRowBuilder<ButtonBuilder> {
    const previousButton = new ButtonBuilder()
      .setCustomId(config.previousButtonId)
      .setLabel(config.previousLabel || '◀ Previous')
      .setStyle(2) // Secondary
      .setDisabled(config.currentPage <= 1);

    const nextButton = new ButtonBuilder()
      .setCustomId(config.nextButtonId)
      .setLabel(config.nextLabel || 'Next ▶')
      .setStyle(2) // Secondary
      .setDisabled(config.currentPage >= config.totalPages);

    return new ActionRowBuilder<ButtonBuilder>().addComponents(
      previousButton,
      nextButton
    );
  }

  /**
   * Collects all messages from a render result for easy cleanup
   */
  static getAllMessages(result: QueueRenderResult): Message[] {
    const messages: Message[] = [result.summaryMessage];

    for (const message of result.itemMessages.values()) {
      messages.push(message);
    }

    if (result.paginationMessage) {
      messages.push(result.paginationMessage);
    }

    return messages;
  }

  /**
   * Deletes all messages from a render result
   */
  static async cleanup(result: QueueRenderResult): Promise<void> {
    const messages = this.getAllMessages(result);
    const deletePromises = messages.map((msg) =>
      msg.delete().catch((err: unknown) => {
        const errMessage = err instanceof Error ? err.message : String(err);
        logger.warn('Failed to delete message during cleanup', { error: errMessage });
      })
    );

    await Promise.all(deletePromises);
  }
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
