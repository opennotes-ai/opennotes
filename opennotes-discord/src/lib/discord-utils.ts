import {
  ButtonBuilder,
  ButtonStyle,
  ActionRowBuilder,
  ContainerBuilder,
  TextDisplayBuilder,
} from 'discord.js';
import { logger } from '../logger.js';
import {
  V2_COLORS,
  createContainer,
  createSmallSeparator,
  createDivider,
  v2MessageFlags,
} from '../utils/v2-components.js';

export interface ForcePublishConfirmationResult {
  content: string;
  components: ActionRowBuilder<ButtonBuilder>[];
}

export interface ForcePublishConfirmationResultV2 {
  container: ContainerBuilder;
  flags: number;
}

export function createForcePublishConfirmationButtons(
  noteId: string,
  shortId: string
): ForcePublishConfirmationResult {
  const confirmButton = new ButtonBuilder()
    .setCustomId(`fp_confirm:${shortId}`)
    .setLabel('Confirm')
    .setStyle(ButtonStyle.Danger);

  const cancelButton = new ButtonBuilder()
    .setCustomId(`fp_cancel:${shortId}`)
    .setLabel('Cancel')
    .setStyle(ButtonStyle.Secondary);

  const row = new ActionRowBuilder<ButtonBuilder>().addComponents(
    confirmButton,
    cancelButton
  );

  const content = [
    '**Confirm Force Publish**',
    '',
    `Are you sure you want to force publish Note #${noteId}?`,
    '',
    'This will:',
    '- Bypass the normal rating threshold requirements',
    '- Mark the note as "Admin Published"',
    '- Immediately publish the note to the configured channel',
    '',
    'Click **Confirm** to proceed or **Cancel** to dismiss.',
  ].join('\n');

  return {
    content,
    components: [row],
  };
}

export function createDisabledForcePublishButtons(shortId: string): ActionRowBuilder<ButtonBuilder>[] {
  const disabledConfirmButton = new ButtonBuilder()
    .setCustomId(`fp_confirm:${shortId}`)
    .setLabel('Confirm')
    .setStyle(ButtonStyle.Danger)
    .setDisabled(true);

  const disabledCancelButton = new ButtonBuilder()
    .setCustomId(`fp_cancel:${shortId}`)
    .setLabel('Cancel')
    .setStyle(ButtonStyle.Secondary)
    .setDisabled(true);

  const row = new ActionRowBuilder<ButtonBuilder>().addComponents(
    disabledConfirmButton,
    disabledCancelButton
  );

  return [row];
}

export function suppressExpectedDiscordErrors(operation: string): (error: unknown) => void {
  return (error: unknown) => {
    logger.debug('Expected Discord API failure', {
      error: error instanceof Error ? error.message : String(error),
      operation,
    });
  };
}

/**
 * Extract platform message ID from various sources.
 *
 * This handles backward compatibility for requests that may have been created before
 * the platform_message_id field was populated or after a migration that didn't
 * preserve the original discord_message_id values.
 *
 * @param platformMessageId - The platform_message_id from the request response (may be null)
 * @param requestId - The request_id which may contain the message ID in format "discord-{messageId}-{timestamp}"
 * @returns The extracted message ID, or null if none could be determined
 */
export function extractPlatformMessageId(
  platformMessageId: string | null | undefined,
  requestId: string
): string | null {
  if (platformMessageId) {
    return platformMessageId;
  }

  if (requestId.startsWith('discord-')) {
    const parts = requestId.split('-');
    if (parts.length >= 2 && parts[1]) {
      logger.debug('Extracted platform_message_id from request_id', {
        request_id: requestId,
        extracted_message_id: parts[1],
      });
      return parts[1];
    }
  }

  return null;
}

export function createForcePublishConfirmationButtonsV2(
  noteId: string,
  shortId: string
): ForcePublishConfirmationResultV2 {
  const confirmButton = new ButtonBuilder()
    .setCustomId(`fp_confirm:${shortId}`)
    .setLabel('Confirm')
    .setStyle(ButtonStyle.Danger);

  const cancelButton = new ButtonBuilder()
    .setCustomId(`fp_cancel:${shortId}`)
    .setLabel('Cancel')
    .setStyle(ButtonStyle.Secondary);

  const row = new ActionRowBuilder<ButtonBuilder>().addComponents(
    confirmButton,
    cancelButton
  );

  const warningMessage = [
    `Are you sure you want to force publish Note #${noteId}?`,
    '',
    'This will:',
    '- Bypass the normal rating threshold requirements',
    '- Mark the note as "Admin Published"',
    '- Immediately publish the note to the configured channel',
  ].join('\n');

  const container = createContainer(V2_COLORS.CRITICAL)
    .addTextDisplayComponents(
      new TextDisplayBuilder().setContent('\u26A0\uFE0F **Confirm Force Publish**')
    )
    .addSeparatorComponents(createSmallSeparator())
    .addTextDisplayComponents(
      new TextDisplayBuilder().setContent(warningMessage)
    )
    .addSeparatorComponents(createDivider())
    .addActionRowComponents(row);

  return {
    container,
    flags: v2MessageFlags({ ephemeral: true }),
  };
}

export function createDisabledForcePublishButtonsV2(
  shortId: string
): ForcePublishConfirmationResultV2 {
  const disabledConfirmButton = new ButtonBuilder()
    .setCustomId(`fp_confirm:${shortId}`)
    .setLabel('Confirm')
    .setStyle(ButtonStyle.Danger)
    .setDisabled(true);

  const disabledCancelButton = new ButtonBuilder()
    .setCustomId(`fp_cancel:${shortId}`)
    .setLabel('Cancel')
    .setStyle(ButtonStyle.Secondary)
    .setDisabled(true);

  const row = new ActionRowBuilder<ButtonBuilder>().addComponents(
    disabledConfirmButton,
    disabledCancelButton
  );

  const container = createContainer(V2_COLORS.CRITICAL)
    .addTextDisplayComponents(
      new TextDisplayBuilder().setContent('\u26A0\uFE0F **Force Publish Confirmation**')
    )
    .addSeparatorComponents(createDivider())
    .addActionRowComponents(row);

  return {
    container,
    flags: v2MessageFlags({ ephemeral: true }),
  };
}
