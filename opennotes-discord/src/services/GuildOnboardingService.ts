import { ApiClient } from '../lib/api-client.js';
import { logger } from '../logger.js';
import { Guild, User, EmbedBuilder } from 'discord.js';

export class GuildOnboardingService {
  constructor(private apiClient: ApiClient) {}

  async checkAndNotifyMissingOpenAIKey(guild: Guild): Promise<void> {
    try {
      logger.info('Checking OpenAI API key configuration for new guild', {
        guildId: guild.id,
        guildName: guild.name,
      });

      const hasOpenAIKey = await this.hasOpenAIApiKey(guild.id);

      if (!hasOpenAIKey) {
        logger.info('OpenAI API key not configured, notifying guild owner', {
          guildId: guild.id,
          ownerId: guild.ownerId,
        });

        await this.notifyOwnerAboutMissingApiKey(guild);
      } else {
        logger.info('OpenAI API key is configured, no notification needed', {
          guildId: guild.id,
        });
      }
    } catch (error) {
      logger.error('Failed to check OpenAI configuration or notify owner', {
        guildId: guild.id,
        error: error instanceof Error ? error.message : String(error),
        stack: error instanceof Error ? error.stack : undefined,
      });
    }
  }

  private async hasOpenAIApiKey(guildId: string): Promise<boolean> {
    try {
      const configs = await this.apiClient.listLLMConfigs(guildId);

      const openaiConfig = configs.find(config => config.provider === 'openai');

      return openaiConfig !== undefined && openaiConfig.enabled;
    } catch (error) {
      logger.warn('Failed to fetch LLM configs, assuming no OpenAI key', {
        guildId,
        error: error instanceof Error ? error.message : String(error),
      });

      return false;
    }
  }

  private async notifyOwnerAboutMissingApiKey(guild: Guild): Promise<void> {
    try {
      const owner = await this.fetchGuildOwner(guild);

      if (!owner) {
        logger.warn('Could not fetch guild owner', { guildId: guild.id });
        return;
      }

      const embed = this.createNotificationEmbed(guild);

      await owner.send({ embeds: [embed] });

      logger.info('Successfully sent OpenAI API key notification to owner', {
        guildId: guild.id,
        ownerId: owner.id,
      });
    } catch (error) {
      if (this.isDMsDisabledError(error)) {
        logger.info('Could not send DM to owner - DMs are disabled', {
          guildId: guild.id,
          ownerId: guild.ownerId,
        });
      } else {
        logger.warn('Failed to send notification to guild owner', {
          guildId: guild.id,
          error: error instanceof Error ? error.message : String(error),
          stack: error instanceof Error ? error.stack : undefined,
        });
      }
    }
  }

  private async fetchGuildOwner(guild: Guild): Promise<User | null> {
    try {
      return await guild.fetchOwner().then(member => member.user);
    } catch (error) {
      logger.warn('Failed to fetch guild owner', {
        guildId: guild.id,
        ownerId: guild.ownerId,
        error: error instanceof Error ? error.message : String(error),
      });
      return null;
    }
  }

  private createNotificationEmbed(guild: Guild): EmbedBuilder {
    return new EmbedBuilder()
      .setColor(0x5865F2)
      .setTitle('Welcome to OpenNotes!')
      .setDescription(
        `Thanks for adding Open Notes to **${guild.name}**!\n\n` +
        `To enable all features, you'll need to configure an OpenAI API key.`
      )
      .addFields(
        {
          name: 'Features that require OpenAI API',
          value:
            '• **Automatic fact-checking** - Similarity search against verified claims\n' +
            '• **AI-assisted note writing** - Smart suggestions when writing community notes\n' +
            '• **Embedding generation** - Semantic search for duplicate detection',
          inline: false,
        },
        {
          name: 'How to add your API key',
          value:
            '1. Get an API key from [OpenAI Platform](https://platform.openai.com/api-keys)\n' +
            '2. Use `/config-opennotes` in your server to configure settings\n' +
            '3. Select "OpenAI API Key" and paste your key\n\n' +
            '*Your API key is encrypted and never shared with other servers.*',
          inline: false,
        },
        {
          name: 'What works without an API key?',
          value:
            'You can still use these features:\n' +
            '• Request community notes on messages\n' +
            '• Write notes manually\n' +
            '• Rate notes for helpfulness\n' +
            '• View note scores and statistics',
          inline: false,
        }
      )
      .setFooter({
        text: 'You can disable this notification in server settings',
      })
      .setTimestamp();
  }

  private isDMsDisabledError(error: unknown): boolean {
    if (error && typeof error === 'object' && 'code' in error) {
      return error.code === 50007;
    }
    return false;
  }
}
