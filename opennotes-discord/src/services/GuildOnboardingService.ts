import { logger } from '../logger.js';
import { Collection, ComponentType, Message, MessageType, TextChannel, User } from 'discord.js';
import { v2MessageFlags } from '../utils/v2-components.js';
import { buildWelcomeContainer } from '../lib/welcome-content.js';
import { sendVibeCheckPrompt } from '../lib/vibecheck-prompt.js';
import { apiClient } from '../api-client.js';

export interface PostWelcomeOptions {
  admin?: User;
  skipVibeCheckPrompt?: boolean;
}

interface WelcomeMessageCheckResult {
  shouldPost: boolean;
  existingMessageId?: string;
}

export class GuildOnboardingService {
  async postWelcomeToChannel(channel: TextChannel, options?: PostWelcomeOptions): Promise<void> {
    const guildId = channel.guild.id;

    try {
      // Check if welcome message already exists (content-based idempotency)
      const checkResult = await this.checkWelcomeMessageState(channel);
      if (!checkResult.shouldPost) {
        return;
      }

      // Post the welcome message
      const container = buildWelcomeContainer();
      const message = await channel.send({
        components: [container],
        flags: v2MessageFlags(),
      });

      logger.info('Posted welcome message to bot channel', {
        channelId: channel.id,
        guildId,
        channelName: channel.name,
        messageId: message.id,
      });

      // Pin the welcome message
      await this.pinWelcomeMessage(message, guildId);

      // Update welcome_message_id in database
      await this.updateWelcomeMessageIdInDb(guildId, message.id);

      if (!options?.skipVibeCheckPrompt && options?.admin) {
        await this.maybeShowVibeCheckPrompt(channel, options.admin);
      }
    } catch (error) {
      logger.error('Failed to post welcome message to bot channel', {
        channelId: channel.id,
        guildId,
        channelName: channel.name,
        error: error instanceof Error ? error.message : String(error),
        stack: error instanceof Error ? error.stack : undefined,
      });
    }
  }

  /**
   * Check welcome message state using content-based idempotency.
   * 1. Fetch pinned messages from Discord (source of truth)
   * 2. Find welcome messages by bot author
   * 3. Clean up duplicates, keeping one
   * 4. Compare content - if same, no action needed
   * 5. If different content, delete old so caller can post new
   */
  private async checkWelcomeMessageState(channel: TextChannel): Promise<WelcomeMessageCheckResult> {
    const guildId = channel.guild.id;
    const botUserId = channel.client.user?.id;

    // Fetch pinned messages from Discord first (source of truth)
    let pinnedMessages: Collection<string, Message>;
    try {
      pinnedMessages = await channel.messages.fetchPinned();
    } catch (error) {
      logger.warn('Cannot verify welcome message state, skipping post to avoid duplicates', {
        guildId,
        channelId: channel.id,
        error: error instanceof Error ? error.message : String(error),
      });
      return { shouldPost: false };
    }

    // Find all welcome messages from the bot (by author ID and container component)
    const botWelcomeMessages = pinnedMessages.filter((msg) => {
      const isFromBot = msg.author?.id === botUserId;
      const hasContainer = msg.components?.some((c) => c.type === ComponentType.Container);
      return isFromBot && hasContainer;
    });

    // Get the current welcome content for comparison
    const currentWelcomeContent = this.getWelcomeContentSignature();

    // If we found bot welcome messages, handle them
    if (botWelcomeMessages.size > 0) {
      const messagesArray = Array.from(botWelcomeMessages.values());

      // Clean up duplicates - keep the first one, delete the rest
      if (messagesArray.length > 1) {
        await this.deleteDuplicateWelcomeMessages(messagesArray.slice(1), guildId);
      }

      const existingMessage = messagesArray[0];
      const existingContentSignature = this.getMessageContentSignature(existingMessage);

      // Compare content
      if (existingContentSignature === currentWelcomeContent) {
        logger.debug('Welcome message with same content already exists', {
          guildId,
          channelId: channel.id,
          messageId: existingMessage.id,
        });

        // Update DB if the stored ID is different/missing
        await this.syncWelcomeMessageIdIfNeeded(guildId, existingMessage.id);

        return { shouldPost: false, existingMessageId: existingMessage.id };
      } else {
        // Content differs - delete old message so we can post new
        logger.info('Welcome message content changed, replacing old message', {
          guildId,
          channelId: channel.id,
          oldMessageId: existingMessage.id,
        });
        await this.deleteMessage(existingMessage, guildId);
        return { shouldPost: true };
      }
    }

    // No bot welcome message found in Discord - we can post
    // Try to log if there was a stale DB record, but don't fail if API is down
    try {
      const communityServer = await apiClient.getCommunityServerByPlatformId(guildId);
      const storedMessageId = communityServer.data.attributes.welcome_message_id;

      if (storedMessageId) {
        logger.info('Stored welcome message not found in pins, posting new one', {
          guildId,
          channelId: channel.id,
          staleWelcomeMessageId: storedMessageId,
        });
      }
    } catch {
      // API failed but Discord (source of truth) shows no welcome message
      // Safe to proceed with posting since we checked the actual pins
      logger.debug('API unavailable, proceeding based on Discord state', {
        guildId,
        channelId: channel.id,
      });
    }

    return { shouldPost: true };
  }

  /**
   * Get a content signature for the current welcome message.
   * Compares the inner components of the container for stable comparison.
   */
  private getWelcomeContentSignature(): string {
    const container = buildWelcomeContainer();
    const components = container.data.components ?? [];
    return this.stableStringify(components);
  }

  /**
   * Get a content signature from an existing message.
   * Extracts the inner components from the container for apples-to-apples comparison.
   */
  private getMessageContentSignature(message: Message): string {
    const container = message.components?.find((c) => c.type === ComponentType.Container);
    const components = container?.components?.map((c) => c.toJSON()) ?? [];
    return this.stableStringify(components);
  }

  /**
   * Stable JSON serialization with sorted keys to ensure consistent comparison.
   */
  private stableStringify(obj: unknown): string {
    return JSON.stringify(obj, (_, value) => {
      if (value && typeof value === 'object' && !Array.isArray(value)) {
        return Object.keys(value)
          .sort()
          .reduce(
            (sorted, key) => {
              sorted[key] = value[key];
              return sorted;
            },
            {} as Record<string, unknown>
          );
      }
      return value;
    });
  }

  /**
   * Delete duplicate welcome messages
   */
  private async deleteDuplicateWelcomeMessages(duplicates: Message[], guildId: string): Promise<void> {
    for (const msg of duplicates) {
      await this.deleteMessage(msg, guildId);
    }
    logger.info('Cleaned up duplicate welcome messages', {
      guildId,
      deletedCount: duplicates.length,
    });
  }

  /**
   * Delete a single message with error handling
   */
  private async deleteMessage(message: Message, guildId: string): Promise<void> {
    try {
      await message.delete();
      logger.debug('Deleted welcome message', {
        guildId,
        messageId: message.id,
      });
    } catch (error) {
      logger.warn('Failed to delete welcome message', {
        guildId,
        messageId: message.id,
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }

  /**
   * Sync the welcome_message_id in DB if it's different from what we found
   */
  private async syncWelcomeMessageIdIfNeeded(guildId: string, foundMessageId: string): Promise<void> {
    try {
      const communityServer = await apiClient.getCommunityServerByPlatformId(guildId);
      const storedMessageId = communityServer.data.attributes.welcome_message_id;

      if (storedMessageId !== foundMessageId) {
        await this.updateWelcomeMessageIdInDb(guildId, foundMessageId);
        logger.debug('Synced stale welcome_message_id in database', {
          guildId,
          oldMessageId: storedMessageId,
          newMessageId: foundMessageId,
        });
      }
    } catch {
      // Best effort - don't fail if we can't sync
    }
  }

  private async pinWelcomeMessage(message: Message, guildId: string): Promise<void> {
    try {
      if (message.pinned) {
        logger.debug('Message already pinned, skipping', {
          guildId,
          messageId: message.id,
        });
        return;
      }

      await message.pin();
      logger.debug('Pinned welcome message', {
        guildId,
        messageId: message.id,
      });

      await this.deletePinNotification(message);
    } catch (error) {
      logger.warn('Failed to pin welcome message', {
        guildId,
        messageId: message.id,
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }

  private async deletePinNotification(pinnedMessage: Message): Promise<void> {
    try {
      const channel = pinnedMessage.channel as TextChannel;
      const messages = await channel.messages.fetch({ limit: 5, after: pinnedMessage.id });

      const pinNotifications = messages.filter(
        (msg) => msg.type === MessageType.ChannelPinnedMessage
      );

      for (const [, notification] of pinNotifications) {
        await notification.delete();
      }
    } catch (error) {
      logger.debug('Could not delete pin notification', {
        messageId: pinnedMessage.id,
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }

  private async updateWelcomeMessageIdInDb(guildId: string, messageId: string): Promise<void> {
    try {
      await apiClient.updateWelcomeMessageId(guildId, messageId);
      logger.debug('Updated welcome_message_id in database', {
        guildId,
        messageId,
      });
    } catch (error) {
      logger.warn('Failed to update welcome_message_id in database', {
        guildId,
        messageId,
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }

  private async maybeShowVibeCheckPrompt(channel: TextChannel, admin: User): Promise<void> {
    const guildId = channel.guild.id;

    try {
      let communityServerId: string;
      try {
        const communityServer = await apiClient.getCommunityServerByPlatformId(guildId);
        communityServerId = communityServer.data.id;
      } catch (lookupError) {
        logger.debug('Community server not found, skipping vibe check prompt', {
          guildId,
          error: lookupError instanceof Error ? lookupError.message : String(lookupError),
        });
        return;
      }

      let hasRecentScan = false;
      try {
        const recentScanResponse = await apiClient.checkRecentScan(communityServerId);
        hasRecentScan = recentScanResponse.data.attributes.has_recent_scan;
      } catch (checkError) {
        logger.debug('Failed to check recent scan, will show prompt anyway', {
          guildId,
          communityServerId,
          error: checkError instanceof Error ? checkError.message : String(checkError),
        });
      }

      if (hasRecentScan) {
        logger.debug('Community has recent scan, skipping vibe check prompt', {
          guildId,
          communityServerId,
        });
        return;
      }

      await sendVibeCheckPrompt({
        botChannel: channel,
        admin,
        guildId,
      });

      logger.info('Sent vibe check prompt to admin in bot channel', {
        channelId: channel.id,
        guildId,
        adminId: admin.id,
      });
    } catch (error) {
      logger.error('Failed to send vibe check prompt', {
        channelId: channel.id,
        guildId,
        adminId: admin.id,
        error: error instanceof Error ? error.message : String(error),
        stack: error instanceof Error ? error.stack : undefined,
      });
    }
  }
}
