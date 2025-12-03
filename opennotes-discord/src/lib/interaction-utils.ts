import {
  ChatInputCommandInteraction,
  MessageContextMenuCommandInteraction,
  ModalSubmitInteraction,
  MessageFlags,
} from 'discord.js';
import { logger } from '../logger.js';
import { serviceProvider } from '../services/index.js';
import { ConfigKey } from './config-schema.js';
import { suppressExpectedDiscordErrors } from './discord-utils.js';

export async function handleEphemeralError(
  interaction: ChatInputCommandInteraction | MessageContextMenuCommandInteraction | ModalSubmitInteraction,
  errorMessage: { content: string },
  guildId: string | null,
  errorId: string,
  configKey: ConfigKey
): Promise<void> {
  let ephemeral = false;
  if (guildId) {
    try {
      const configService = serviceProvider.getGuildConfigService();
      ephemeral = await configService.get(guildId, configKey) as boolean;
    } catch (configError) {
      logger.warn('Failed to fetch ephemeral config, defaulting to false', {
        error_id: errorId,
        community_server_id: guildId,
      });
    }
  }

  if (ephemeral) {
    await interaction.editReply(errorMessage).catch(suppressExpectedDiscordErrors('edit_ephemeral_error'));
  } else {
    await interaction.followUp({ ...errorMessage, flags: MessageFlags.Ephemeral }).catch(suppressExpectedDiscordErrors('followup_error'));
    await interaction.deleteReply().catch(suppressExpectedDiscordErrors('delete_original_reply'));
  }
}
