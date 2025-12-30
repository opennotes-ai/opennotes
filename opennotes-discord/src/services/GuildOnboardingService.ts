import { logger } from '../logger.js';
import { Collection, ComponentType, Message, MessageType, TextChannel, User } from 'discord.js';
import { v2MessageFlags } from '../utils/v2-components.js';
import { buildWelcomeContainer, WELCOME_MESSAGE_REVISION, extractRevisionFromMessage } from '../lib/welcome-content.js';
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

/** Number of recent messages to scan for stale pin notifications */
const PIN_NOTIFICATION_CLEANUP_LIMIT = 50;

export class GuildOnboardingService {
  async postWelcomeToChannel(channel: TextChannel, options?: PostWelcomeOptions): Promise<void> {
    const guildId = channel.guild.id;

    try {
      // Ensure community server exists in database (auto-creates for service accounts)
      // This must happen before any community-server-dependent API calls
      try {
        await apiClient.getCommunityServerByPlatformId(guildId);
      } catch (error) {
        logger.warn('Failed to ensure community server exists', {
          guildId,
          channelId: channel.id,
          error: error instanceof Error ? error.message : String(error),
        });
        // Continue anyway - the server may exist, we just couldn't verify
      }

      // Clean up any stale pin notifications from channel history
      await this.cleanupPinNotifications(channel);

      // Check if welcome message already exists (revision-based idempotency)
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
   * Check welcome message state using revision-based comparison.
   * 1. Fetch pinned messages from Discord (source of truth)
   * 2. Find welcome messages by bot author
   * 3. Sort by timestamp, delete duplicates keeping most recent
   * 4. Extract revision from most recent, compare with current code revision
   * 5. If same revision, no action needed
   * 6. If different revision, delete old so caller can post new
   */
  private async checkWelcomeMessageState(channel: TextChannel): Promise<WelcomeMessageCheckResult> {
    const guildId = channel.guild.id;
    const botUserId = channel.client.user?.id;

    // Fetch pinned messages from Discord (source of truth)
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

    if (botWelcomeMessages.size > 0) {
      // Sort by timestamp (most recent first) and convert to array
      const messagesArray = Array.from(botWelcomeMessages.values()).sort(
        (a, b) => b.createdTimestamp - a.createdTimestamp
      );

      // Delete duplicates - keep the most recent, delete the rest
      if (messagesArray.length > 1) {
        await this.deleteDuplicateWelcomeMessages(messagesArray.slice(1), guildId);
      }

      const mostRecentMessage = messagesArray[0];
      const existingRevision = extractRevisionFromMessage(mostRecentMessage);

      // Compare revisions
      if (existingRevision === WELCOME_MESSAGE_REVISION) {
        logger.debug('Welcome message with same revision already exists', {
          guildId,
          channelId: channel.id,
          messageId: mostRecentMessage.id,
          revision: existingRevision,
        });

        // Update DB if the stored ID is different/missing
        await this.syncWelcomeMessageIdIfNeeded(guildId, mostRecentMessage.id);

        return { shouldPost: false, existingMessageId: mostRecentMessage.id };
      } else {
        // Revision differs - delete old message so we can post new
        logger.info('Welcome message revision changed, replacing old message', {
          guildId,
          channelId: channel.id,
          oldMessageId: mostRecentMessage.id,
          oldRevision: existingRevision,
          newRevision: WELCOME_MESSAGE_REVISION,
        });
        await this.deleteMessage(mostRecentMessage, guildId);
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

  private async cleanupPinNotifications(channel: TextChannel): Promise<void> {
    try {
      const messages = await channel.messages.fetch({ limit: PIN_NOTIFICATION_CLEANUP_LIMIT });
      const pinNotifications = messages.filter(
        (msg) => msg.type === MessageType.ChannelPinnedMessage
      );

      if (pinNotifications.size === 0) {
        return;
      }

      let deletedCount = 0;
      for (const [, notification] of pinNotifications) {
        try {
          await notification.delete();
          deletedCount++;
        } catch (error) {
          logger.debug('Failed to delete individual pin notification', {
            channelId: channel.id,
            guildId: channel.guild.id,
            notificationId: notification.id,
            error: error instanceof Error ? error.message : String(error),
          });
        }
      }

      if (deletedCount > 0) {
        logger.debug('Cleaned up pin notifications', {
          channelId: channel.id,
          guildId: channel.guild.id,
          deletedCount,
        });
      }
    } catch (error) {
      logger.debug('Could not cleanup pin notifications', {
        channelId: channel.id,
        guildId: channel.guild.id,
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
