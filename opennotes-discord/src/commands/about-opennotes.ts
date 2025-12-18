import {
  SlashCommandBuilder,
  ChatInputCommandInteraction,
} from 'discord.js';
import { logger } from '../logger.js';
import { generateErrorId, extractErrorDetails, formatErrorForUser } from '../lib/errors.js';
import { v2MessageFlags } from '../utils/v2-components.js';
import { buildWelcomeContainer } from '../lib/welcome-content.js';

export const data = new SlashCommandBuilder()
  .setName('about-opennotes')
  .setDescription('Learn about Open Notes and how it works');

export async function execute(interaction: ChatInputCommandInteraction): Promise<void> {
  const errorId = generateErrorId();
  const userId = interaction.user.id;
  const guildId = interaction.guildId;

  try {
    logger.info('Executing about-opennotes command', {
      error_id: errorId,
      command: 'about-opennotes',
      user_id: userId,
      community_server_id: guildId,
    });

    await interaction.deferReply({ flags: v2MessageFlags({ ephemeral: true }) });

    const container = buildWelcomeContainer();

    await interaction.editReply({
      components: [container],
      flags: v2MessageFlags({ ephemeral: true }),
    });

    logger.info('About command completed successfully', {
      error_id: errorId,
      command: 'about-opennotes',
      user_id: userId,
    });
  } catch (error) {
    const errorDetails = extractErrorDetails(error);

    logger.error('Unexpected error in about-opennotes command', {
      error_id: errorId,
      command: 'about-opennotes',
      user_id: userId,
      community_server_id: guildId,
      error: errorDetails.message,
      error_type: errorDetails.type,
      stack: errorDetails.stack,
    });

    await interaction.editReply({
      content: formatErrorForUser(errorId, 'Failed to display information about OpenNotes.'),
    });
  }
}
