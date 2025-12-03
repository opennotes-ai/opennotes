import type {
  ChatInputCommandInteraction,
  MessageContextMenuCommandInteraction,
  ModalSubmitInteraction,
} from 'discord.js';
import { logger } from '../logger.js';
import { generateErrorId, extractErrorDetails, formatErrorForUser, ApiError } from './errors.js';
import { handleEphemeralError } from './interaction-utils.js';
import type { ConfigKey } from './config-schema.js';

export interface CommandContext {
  command: string;
  userId: string;
  guildId: string | null;
  additionalContext?: Record<string, unknown>;
}

export interface CommandErrorHandlerOptions {
  errorMessagePrefix: string;
  ephemeralConfigKey: ConfigKey;
}

export async function withCommandErrorHandling<T>(
  interaction: ChatInputCommandInteraction | MessageContextMenuCommandInteraction | ModalSubmitInteraction,
  context: CommandContext,
  options: CommandErrorHandlerOptions,
  operation: (errorId: string) => Promise<T>
): Promise<T | undefined> {
  const errorId = generateErrorId();

  try {
    logger.info(`Executing ${context.command} command`, {
      error_id: errorId,
      command: context.command,
      user_id: context.userId,
      community_server_id: context.guildId,
      ...context.additionalContext,
    });

    const result = await operation(errorId);

    logger.info(`${context.command} completed successfully`, {
      error_id: errorId,
      command: context.command,
      user_id: context.userId,
      community_server_id: context.guildId,
      ...context.additionalContext,
    });

    return result;
  } catch (error) {
    const errorDetails = extractErrorDetails(error);

    logger.error(`Unexpected error in ${context.command} command`, {
      error_id: errorId,
      command: context.command,
      user_id: context.userId,
      community_server_id: context.guildId,
      ...context.additionalContext,
      error: errorDetails.message,
      error_type: errorDetails.type,
      stack: errorDetails.stack,
      ...(error instanceof ApiError && {
        endpoint: error.endpoint,
        status_code: error.statusCode,
        response_body: error.responseBody,
      }),
    });

    const errorMessage = {
      content: formatErrorForUser(errorId, options.errorMessagePrefix),
    };

    await handleEphemeralError(
      interaction,
      errorMessage,
      context.guildId,
      errorId,
      options.ephemeralConfigKey
    );

    return undefined;
  }
}

export async function withModalErrorHandling<T>(
  interaction: ModalSubmitInteraction,
  context: CommandContext,
  options: CommandErrorHandlerOptions,
  operation: (errorId: string) => Promise<T>
): Promise<T | undefined> {
  return withCommandErrorHandling(interaction, context, options, operation);
}

export async function withContextMenuErrorHandling<T>(
  interaction: MessageContextMenuCommandInteraction,
  context: CommandContext,
  options: CommandErrorHandlerOptions,
  operation: (errorId: string) => Promise<T>
): Promise<T | undefined> {
  return withCommandErrorHandling(interaction, context, options, operation);
}
