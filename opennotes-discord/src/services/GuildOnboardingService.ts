import { logger } from '../logger.js';
import { Message, TextChannel, User } from 'discord.js';
import { v2MessageFlags } from '../utils/v2-components.js';
import { buildWelcomeContainer } from '../lib/welcome-content.js';
import { sendVibeCheckPrompt } from '../lib/vibecheck-prompt.js';
import { apiClient } from '../api-client.js';

export interface PostWelcomeOptions {
  admin?: User;
  skipVibeCheckPrompt?: boolean;
}

export class GuildOnboardingService {
  async postWelcomeToChannel(channel: TextChannel, options?: PostWelcomeOptions): Promise<void> {
    const guildId = channel.guild.id;

    try {
      // Check if welcome message already exists
      const shouldPost = await this.shouldPostWelcomeMessage(channel);
      if (!shouldPost) {
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

  private async shouldPostWelcomeMessage(channel: TextChannel): Promise<boolean> {
    const guildId = channel.guild.id;

    try {
      // Get community server to check for existing welcome_message_id
      const communityServer = await apiClient.getCommunityServerByPlatformId(guildId);
      const welcomeMessageId = communityServer.data.attributes.welcome_message_id;

      if (!welcomeMessageId) {
        // No welcome message stored, should post
        return true;
      }

      // Check if the stored welcome message exists in channel pins
      const pinnedMessages = await channel.messages.fetchPinned();
      const messageExists = pinnedMessages.has(welcomeMessageId);

      if (messageExists) {
        logger.debug('Welcome message already exists in channel pins', {
          guildId,
          channelId: channel.id,
          welcomeMessageId,
        });
        return false;
      }

      // Stored message not found in pins, need to post new one
      logger.info('Stored welcome message not found in pins, posting new one', {
        guildId,
        channelId: channel.id,
        staleWelcomeMessageId: welcomeMessageId,
      });
      return true;
    } catch (error) {
      // If we can't check, assume we should post
      logger.debug('Failed to check for existing welcome message, will post', {
        guildId,
        channelId: channel.id,
        error: error instanceof Error ? error.message : String(error),
      });
      return true;
    }
  }

  private async pinWelcomeMessage(message: Message, guildId: string): Promise<void> {
    try {
      await message.pin();
      logger.debug('Pinned welcome message', {
        guildId,
        messageId: message.id,
      });
    } catch (error) {
      logger.warn('Failed to pin welcome message', {
        guildId,
        messageId: message.id,
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
