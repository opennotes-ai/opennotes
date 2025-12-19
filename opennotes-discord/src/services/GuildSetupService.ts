import { ChannelType, Guild, TextChannel } from 'discord.js';
import { apiClient } from '../api-client.js';
import { logger } from '../logger.js';
import type { MonitoredChannelCreate } from '../lib/api-client.js';
import { config } from '../config.js';
import { resolveCommunityServerId } from '../lib/community-server-resolver.js';

export class GuildSetupService {
  async autoRegisterChannels(guild: Guild): Promise<void> {
    try {
      logger.info('Starting auto-registration of channels', {
        guildId: guild.id,
        guildName: guild.name,
      });

      const communityServerId = await resolveCommunityServerId(guild.id);

      const textChannels = await this.getTextChannels(guild);

      if (textChannels.length === 0) {
        logger.info('No text channels found to register', {
          guildId: guild.id,
        });
        return;
      }

      logger.debug('Found text channels', {
        guildId: guild.id,
        count: textChannels.length,
      });

      const results = await this.registerChannels(communityServerId, textChannels, guild.id);

      logger.info('Channel auto-registration completed', {
        guildId: guild.id,
        totalChannels: textChannels.length,
        registered: results.registered,
        alreadyMonitored: results.alreadyMonitored,
        failed: results.failed,
      });
    } catch (error) {
      logger.error('Failed to auto-register channels', {
        guildId: guild.id,
        error: error instanceof Error ? error.message : String(error),
        stack: error instanceof Error ? error.stack : undefined,
      });
      throw error;
    }
  }

  private async getTextChannels(guild: Guild): Promise<TextChannel[]> {
    try {
      const channels = await guild.channels.fetch();

      const textChannels = channels
        .filter((channel): channel is TextChannel =>
          channel !== null && channel.type === ChannelType.GuildText
        )
        .map(channel => channel);

      return textChannels;
    } catch (error) {
      logger.error('Failed to fetch guild channels', {
        guildId: guild.id,
        error: error instanceof Error ? error.message : String(error),
      });
      throw error;
    }
  }

  private async registerChannels(
    communityServerId: string,
    channels: TextChannel[],
    guildId: string
  ): Promise<{ registered: number; alreadyMonitored: number; failed: number }> {
    let registered = 0;
    let alreadyMonitored = 0;
    let failed = 0;

    const registrationPromises = channels.map(async (channel) => {
      try {
        const request: MonitoredChannelCreate = {
          community_server_id: communityServerId,
          channel_id: channel.id,
          enabled: true,
          similarity_threshold: config.similaritySearchDefaultThreshold,
          dataset_tags: ['snopes'],
          updated_by: null,
        };

        const result = await apiClient.createMonitoredChannel(request);

        if (result === null) {
          alreadyMonitored++;
          logger.debug('Channel already monitored, skipping', {
            channelId: channel.id,
            channelName: channel.name,
            guildId,
          });
        } else {
          registered++;
          logger.debug('Channel registered for monitoring', {
            channelId: channel.id,
            channelName: channel.name,
            guildId,
          });
        }
      } catch (error) {
        failed++;
        logger.error('Failed to register channel', {
          channelId: channel.id,
          channelName: channel.name,
          guildId,
          error: error instanceof Error ? error.message : String(error),
        });
      }
    });

    await Promise.allSettled(registrationPromises);

    return { registered, alreadyMonitored, failed };
  }
}
