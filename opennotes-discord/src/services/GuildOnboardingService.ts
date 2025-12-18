import { logger } from '../logger.js';
import { TextChannel } from 'discord.js';
import { v2MessageFlags } from '../utils/v2-components.js';
import { buildWelcomeContainer } from '../lib/welcome-content.js';
import { sendVibeCheckPrompt } from '../lib/vibecheck-prompt.js';
import { apiClient } from '../api-client.js';

export interface PostWelcomeOptions {
  adminId?: string;
  skipVibeCheckPrompt?: boolean;
}

export class GuildOnboardingService {
  async postWelcomeToChannel(channel: TextChannel, options?: PostWelcomeOptions): Promise<void> {
    try {
      const container = buildWelcomeContainer();

      await channel.send({
        components: [container],
        flags: v2MessageFlags(),
      });

      logger.info('Posted welcome message to bot channel', {
        channelId: channel.id,
        guildId: channel.guild.id,
        channelName: channel.name,
      });

      if (!options?.skipVibeCheckPrompt && options?.adminId) {
        await this.maybeShowVibeCheckPrompt(channel, options.adminId);
      }
    } catch (error) {
      logger.error('Failed to post welcome message to bot channel', {
        channelId: channel.id,
        guildId: channel.guild.id,
        channelName: channel.name,
        error: error instanceof Error ? error.message : String(error),
        stack: error instanceof Error ? error.stack : undefined,
      });
    }
  }

  private async maybeShowVibeCheckPrompt(channel: TextChannel, adminId: string): Promise<void> {
    const guildId = channel.guild.id;

    try {
      let communityServerId: string;
      try {
        const communityServer = await apiClient.getCommunityServerByPlatformId(guildId);
        communityServerId = communityServer.id;
      } catch (lookupError) {
        logger.debug('Community server not found, skipping vibe check prompt', {
          guildId,
          error: lookupError instanceof Error ? lookupError.message : String(lookupError),
        });
        return;
      }

      let hasRecentScan = false;
      try {
        hasRecentScan = await apiClient.checkRecentScan(communityServerId);
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
        channel,
        adminId,
        guildId,
      });

      logger.info('Sent vibe check prompt to admin', {
        channelId: channel.id,
        guildId,
        adminId,
      });
    } catch (error) {
      logger.error('Failed to send vibe check prompt', {
        channelId: channel.id,
        guildId,
        adminId,
        error: error instanceof Error ? error.message : String(error),
        stack: error instanceof Error ? error.stack : undefined,
      });
    }
  }
}
