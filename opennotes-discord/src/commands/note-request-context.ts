import {
  ContextMenuCommandBuilder,
  ApplicationCommandType,
  MessageContextMenuCommandInteraction,
  InteractionContextType,
} from 'discord.js';
import { serviceProvider } from '../services/index.js';
import { ConfigKey } from '../lib/config-schema.js';
import { logger } from '../logger.js';
import { generateErrorId, extractErrorDetails, formatErrorForUser, ApiError } from '../lib/errors.js';
import { createNoteRequest } from './note.js';
import { handleEphemeralError } from '../lib/interaction-utils.js';
import { v2MessageFlags } from '../utils/v2-components.js';

export const data = new ContextMenuCommandBuilder()
  .setName('Request Note')
  .setType(ApplicationCommandType.Message)
  .setContexts(InteractionContextType.Guild);

export async function execute(interaction: MessageContextMenuCommandInteraction): Promise<void> {
  const errorId = generateErrorId();
  const targetMessage = interaction.targetMessage;
  const messageId = targetMessage.id;
  const userId = interaction.user.id;
  const guildId = interaction.guildId;

  try {
    logger.info('Executing request-note-context command', {
      error_id: errorId,
      command: 'note-request-context',
      user_id: userId,
      community_server_id: guildId,
      message_id: messageId,
      has_content: !!targetMessage.content,
      has_embeds: targetMessage.embeds.length > 0,
      has_attachments: targetMessage.attachments.size > 0,
    });

    let ephemeral = false;
    if (guildId) {
      const configService = serviceProvider.getGuildConfigService();
      ephemeral = await configService.get(guildId, ConfigKey.REQUEST_NOTE_EPHEMERAL) as boolean;
    }

    await interaction.deferReply({ flags: v2MessageFlags({ ephemeral }) });

    // Validate that guildId exists (required for all requests)
    if (!guildId) {
      logger.error('Missing guild ID for context menu request', { error_id: errorId, user_id: userId });
      await interaction.editReply({
        content: '❌ This command can only be used in a server, not in DMs.',
      });
      return;
    }

    const result = await createNoteRequest({
      messageId,
      message: targetMessage,
      reason: undefined, // Context menu doesn't have reason field
      userId,
      community_server_id: guildId, // Required: Discord guild/server ID
      channel: interaction.channel,
      errorId,
      user: interaction.user,
    });

    if (!result.success) {
      if (ephemeral) {
        await interaction.editReply(result.response);
      } else {
        await interaction.followUp(result.response);
        await interaction.deleteReply();
      }
      return;
    }

    await interaction.editReply(result.response);

    logger.info('Request-note-context completed successfully', {
      error_id: errorId,
      command: 'note-request-context',
      user_id: userId,
      message_id: messageId,
    });
  } catch (error) {
    const errorDetails = extractErrorDetails(error);

    logger.error('Unexpected error in request-note-context command', {
      error_id: errorId,
      command: 'note-request-context',
      user_id: userId,
      community_server_id: guildId,
      message_id: messageId,
      error: errorDetails.message,
      error_type: errorDetails.type,
      stack: errorDetails.stack,
      ...(error instanceof ApiError && {
        endpoint: error.endpoint,
        status_code: error.statusCode,
        response_body: error.responseBody,
      }),
    });

    const errorMessage = { content: formatErrorForUser(errorId, 'Failed to create note request.') };

    await handleEphemeralError(interaction, errorMessage, guildId, errorId, ConfigKey.REQUEST_NOTE_EPHEMERAL);
  }
}
