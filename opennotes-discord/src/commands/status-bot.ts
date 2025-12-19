import {
  SlashCommandBuilder,
  ChatInputCommandInteraction,
} from 'discord.js';
import { serviceProvider } from '../services/index.js';
import { DiscordFormatter } from '../services/DiscordFormatter.js';
import { logger } from '../logger.js';
import { generateErrorId, extractErrorDetails, formatErrorForUser, ApiError } from '../lib/errors.js';
import { v2MessageFlags } from '../utils/v2-components.js';

export const data = new SlashCommandBuilder()
  .setName('status-bot')
  .setDescription('Check bot and server status');

export async function execute(interaction: ChatInputCommandInteraction): Promise<void> {
  const errorId = generateErrorId();
  const userId = interaction.user.id;
  const guildId = interaction.guildId;

  try {
    logger.info('Executing status command', {
      error_id: errorId,
      command: 'status-bot',
      user_id: userId,
      guild_id: guildId,
    });

    await interaction.deferReply({ flags: v2MessageFlags({ ephemeral: true }) });

    const guilds = interaction.client.guilds.cache.size;
    const statusService = serviceProvider.getStatusService();
    const scoringService = serviceProvider.getScoringService();

    const result = await statusService.execute(guilds);

    if (!result.success) {
      const errorResponse = DiscordFormatter.formatErrorV2(result);
      await interaction.editReply({
        components: errorResponse.components,
        flags: errorResponse.flags,
      });
      return;
    }

    const scoringResult = await scoringService.getScoringStatus();

    const response = DiscordFormatter.formatStatusSuccessV2(result.data!);

    if (scoringResult.success && scoringResult.data) {
      const scoringV2 = DiscordFormatter.formatScoringStatusV2(scoringResult.data);
      response.container
        .addSeparatorComponents(scoringV2.separator)
        .addTextDisplayComponents(scoringV2.textDisplay);
    }

    await interaction.editReply({
      components: [response.container.toJSON()],
      flags: response.flags,
    });

    logger.info('Status command completed successfully', {
      error_id: errorId,
      command: 'status-bot',
      user_id: userId,
      guild_count: guilds,
    });
  } catch (error) {
    const errorDetails = extractErrorDetails(error);

    logger.error('Unexpected error in status command', {
      error_id: errorId,
      command: 'status-bot',
      user_id: userId,
      guild_id: guildId,
      error: errorDetails.message,
      error_type: errorDetails.type,
      stack: errorDetails.stack,
      ...(error instanceof ApiError && {
        endpoint: error.endpoint,
        status_code: error.statusCode,
        response_body: error.responseBody,
      }),
    });

    await interaction.editReply({
      content: formatErrorForUser(errorId, 'Failed to retrieve bot status.'),
    });
  }
}
