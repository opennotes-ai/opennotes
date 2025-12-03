import type { EmbedBuilder, InteractionReplyOptions } from 'discord.js';
import { EmbedBuilder as DiscordEmbedBuilder } from 'discord.js';

/**
 * Adds a deprecation warning embed to an interaction response.
 *
 * The warning is displayed as an orange embed at the top of the response,
 * informing users that the command they used is deprecated and will be
 * removed on January 26, 2026.
 *
 * @param response - The original interaction reply options
 * @param oldCommand - The deprecated command name (without slash)
 * @param newCommand - The new standardized command name (without slash)
 * @returns Modified interaction reply options with deprecation warning
 */
export function addDeprecationWarning(
  response: InteractionReplyOptions,
  oldCommand: string,
  newCommand: string,
): InteractionReplyOptions {
  const warning = new DiscordEmbedBuilder()
    .setColor(0xffa500) // Orange
    .setTitle('⚠️ Command Deprecated')
    .setDescription(
      `The \`/${oldCommand}\` command is deprecated and will be removed on **January 26, 2026**.\n\n` +
        `Please use \`/${newCommand}\` instead. [Learn more](https://github.com/yourusername/opennotes-discord/blob/main/docs/COMMAND_MIGRATION_GUIDE.md)`,
    )
    .setTimestamp();

  // Prepend the warning embed to any existing embeds
  const existingEmbeds = response.embeds || [];
  const newEmbeds = [warning, ...existingEmbeds];

  return {
    ...response,
    embeds: newEmbeds as EmbedBuilder[],
  };
}

/**
 * Options for executing a command with deprecation support.
 */
export interface DeprecationOptions {
  /** Whether this command execution is from a deprecated alias */
  deprecated?: boolean;
  /** The old deprecated command name (without slash) */
  oldName?: string;
  /** The new standardized command name (without slash) */
  newName?: string;
}
