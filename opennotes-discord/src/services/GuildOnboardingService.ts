import { logger } from '../logger.js';
import { TextChannel } from 'discord.js';
import { v2MessageFlags } from '../utils/v2-components.js';
import { buildWelcomeContainer } from '../lib/welcome-content.js';

export class GuildOnboardingService {
  async postWelcomeToChannel(channel: TextChannel): Promise<void> {
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
}
