import {
  SlashCommandBuilder,
  ChatInputCommandInteraction,
} from 'discord.js';
import { logger } from '../logger.js';
import { generateErrorId, extractErrorDetails, formatErrorForUser } from '../lib/errors.js';
import { v2MessageFlags, createContainer, createTextSection, createDivider, V2_COLORS } from '../utils/v2-components.js';
import { buildNavHub } from '../lib/navigation-components.js';

export const data = new SlashCommandBuilder()
  .setName('open-notes')
  .setDescription('Open the navigation hub - browse all available actions');

export async function execute(interaction: ChatInputCommandInteraction): Promise<void> {
  const errorId = generateErrorId();
  const userId = interaction.user.id;
  const guildId = interaction.guildId;

  try {
    logger.info('Executing open-notes command', {
      error_id: errorId,
      command: 'open-notes',
      user_id: userId,
      guild_id: guildId,
    });

    const container = createContainer(V2_COLORS.PRIMARY);

    container.addTextDisplayComponents(
      createTextSection('## OpenNotes Navigation')
    );
    container.addTextDisplayComponents(
      createTextSection('Browse all available actions and navigate between features.')
    );
    container.addSeparatorComponents(createDivider());

    const hubRows = buildNavHub();
    for (const row of hubRows) {
      container.addActionRowComponents(row);
    }

    await interaction.reply({
      components: [container],
      flags: v2MessageFlags({ ephemeral: true }),
    });

    logger.info('Open-notes command completed successfully', {
      error_id: errorId,
      command: 'open-notes',
      user_id: userId,
    });
  } catch (error) {
    const errorDetails = extractErrorDetails(error);

    logger.error('Unexpected error in open-notes command', {
      error_id: errorId,
      command: 'open-notes',
      user_id: userId,
      guild_id: guildId,
      error: errorDetails.message,
      error_type: errorDetails.type,
      stack: errorDetails.stack,
    });

    try {
      if (interaction.replied || interaction.deferred) {
        await interaction.followUp({
          content: formatErrorForUser(errorId, 'Failed to open navigation hub.'),
          flags: v2MessageFlags({ ephemeral: true }),
        });
      } else {
        await interaction.reply({
          content: formatErrorForUser(errorId, 'Failed to open navigation hub.'),
          flags: v2MessageFlags({ ephemeral: true }),
        });
      }
    } catch {
      // ignore follow-up failures
    }
  }
}
