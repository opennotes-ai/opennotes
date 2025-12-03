import {
  EmbedBuilder,
  ActionRowBuilder,
  ButtonBuilder,
  ThreadChannel,
  Message,
  MessageCreateOptions,
  MessageEditOptions,
} from 'discord.js';
import { logger } from '../logger.js';

/**
 * Represents a single item in a queue (e.g., a note, request, etc.)
 */
export interface QueueItem {
  id: string;
  embed: EmbedBuilder;
  buttons: ActionRowBuilder<ButtonBuilder>[];
}

/**
 * Configuration for the queue summary message
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
