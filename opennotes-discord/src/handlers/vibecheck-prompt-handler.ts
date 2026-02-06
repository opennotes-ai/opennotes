import {
  MessageComponentInteraction,
  StringSelectMenuInteraction,
  ButtonInteraction,
  TextChannel,
  ActionRowBuilder,
  StringSelectMenuBuilder,
} from 'discord.js';
import { cache } from '../cache.js';
import { logger } from '../logger.js';
import { generateErrorId, extractErrorDetails } from '../lib/errors.js';
import {
  VIBECHECK_PROMPT_CUSTOM_IDS,
  createDaysSelectMenu,
  createPromptButtons,
} from '../lib/vibecheck-prompt.js';
import { executeBulkScan } from '../lib/bulk-scan-executor.js';

const VIBECHECK_PROMPT_TTL_SECONDS = 300;

export interface VibecheckPromptState {
  guildId: string;
  adminId: string;
  botChannelId: string;
  selectedDays: number | null;
}

function getCacheKey(messageId: string): string {
  return `vibecheck_prompt_state:${messageId}`;
}

export async function getVibecheckPromptState(
  messageId: string
): Promise<VibecheckPromptState | null> {
  return cache.get<VibecheckPromptState>(getCacheKey(messageId));
}

export async function setVibecheckPromptState(
  messageId: string,
  state: VibecheckPromptState
): Promise<void> {
  await cache.set(getCacheKey(messageId), state, VIBECHECK_PROMPT_TTL_SECONDS);
}

export async function deleteVibecheckPromptState(messageId: string): Promise<void> {
  await cache.delete(getCacheKey(messageId));
}

export function isVibecheckPromptInteraction(customId: string): boolean {
  return (
    customId === VIBECHECK_PROMPT_CUSTOM_IDS.DAYS_SELECT ||
    customId === VIBECHECK_PROMPT_CUSTOM_IDS.START ||
    customId === VIBECHECK_PROMPT_CUSTOM_IDS.NO_THANKS
  );
}

export async function handleVibecheckPromptInteraction(
  interaction: MessageComponentInteraction
): Promise<void> {
  const errorId = generateErrorId();
  const messageId = interaction.message.id;

  try {
    const state = await getVibecheckPromptState(messageId);

    if (!state) {
      logger.debug('Vibecheck prompt state not found - prompt may have expired', {
        error_id: errorId,
        message_id: messageId,
        user_id: interaction.user.id,
      });

      await interaction.update({
        content: 'This vibe check prompt has expired. You can run `/vibecheck` anytime to scan your server.',
        components: [],
      });
      return;
    }

    if (interaction.user.id !== state.adminId) {
      await interaction.reply({
        content: 'Only the server admin who received this prompt can interact with it.',
        ephemeral: true,
      });
      return;
    }

    if (interaction.isStringSelectMenu()) {
      await handleDaysSelect(interaction, state, messageId, errorId);
    } else if (interaction.isButton()) {
      if (interaction.customId === VIBECHECK_PROMPT_CUSTOM_IDS.NO_THANKS) {
        await handleNoThanks(interaction, messageId, errorId);
      } else if (interaction.customId === VIBECHECK_PROMPT_CUSTOM_IDS.START) {
        await handleStart(interaction, state, messageId, errorId);
      }
    }
  } catch (error) {
    const errorDetails = extractErrorDetails(error);
    logger.error('Error handling vibecheck prompt interaction', {
      error_id: errorId,
      message_id: messageId,
      custom_id: interaction.customId,
      error: errorDetails.message,
      error_type: errorDetails.type,
      stack: errorDetails.stack,
    });

    try {
      if (interaction.deferred || interaction.replied) {
        await interaction.followUp({
          content: 'An error occurred. Please try using `/vibecheck` instead.',
          ephemeral: true,
        });
      } else {
        await interaction.reply({
          content: 'An error occurred. Please try using `/vibecheck` instead.',
          ephemeral: true,
        });
      }
    } catch {
      logger.debug('Failed to send error response for vibecheck prompt', {
        error_id: errorId,
      });
    }
  }
}

async function handleDaysSelect(
  interaction: StringSelectMenuInteraction,
  state: VibecheckPromptState,
  messageId: string,
  errorId: string
): Promise<void> {
  const selectedDays = parseInt(interaction.values[0], 10);

  if (isNaN(selectedDays) || selectedDays <= 0) {
    logger.warn('Invalid days selection in vibecheck prompt', {
      error_id: errorId,
      message_id: messageId,
      raw_value: interaction.values[0],
    });
    await interaction.reply({
      content: 'Invalid selection. Please try again.',
      ephemeral: true,
    });
    return;
  }

  const updatedState: VibecheckPromptState = {
    ...state,
    selectedDays,
  };
  await setVibecheckPromptState(messageId, updatedState);

  const updatedSelectRow = new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(
    createDaysSelectMenu()
  );
  const updatedButtonRow = createPromptButtons(true);

  await interaction.update({
    content: `**Vibe Check Available**

Would you like to scan your server for potential misinformation? This will check recent messages against known fact-checking databases.

Selected: **${selectedDays} day${selectedDays === 1 ? '' : 's'}**`,
    components: [updatedSelectRow, updatedButtonRow],
  });

  logger.debug('Vibecheck prompt days selected', {
    error_id: errorId,
    message_id: messageId,
    selected_days: selectedDays,
  });
}

async function handleNoThanks(
  interaction: ButtonInteraction,
  messageId: string,
  errorId: string
): Promise<void> {
  await deleteVibecheckPromptState(messageId);

  await interaction.update({
    content: 'Vibe check prompt dismissed. You can run `/vibecheck` anytime to scan your server.',
    components: [],
  });

  logger.debug('Vibecheck prompt dismissed', {
    error_id: errorId,
    message_id: messageId,
  });
}

async function handleStart(
  interaction: ButtonInteraction,
  state: VibecheckPromptState,
  messageId: string,
  errorId: string
): Promise<void> {
  if (state.selectedDays === null) {
    await interaction.reply({
      content: 'Please select the number of days to scan first.',
      ephemeral: true,
    });
    return;
  }

  await deleteVibecheckPromptState(messageId);

  await interaction.update({
    content: `Starting vibe check scan for the last ${state.selectedDays} day${state.selectedDays === 1 ? '' : 's'}...`,
    components: [],
  });

  const channel = interaction.channel;
  if (!channel || !(channel instanceof TextChannel)) {
    await interaction.message.edit({
      content: 'Unable to access channel information. Please try `/vibecheck` instead.',
    });
    return;
  }

  const guild = channel.guild;
  if (!guild) {
    await interaction.message.edit({
      content: 'Unable to access server information. Please try `/vibecheck` instead.',
    });
    return;
  }

  try {
    const result = await executeBulkScan({
      guild,
      days: state.selectedDays,
      initiatorId: interaction.user.id,
      errorId,
    });

    if (result.channelsScanned === 0) {
      await interaction.message.edit({
        content: 'No accessible text channels found to scan.',
      });
      return;
    }

    await interaction.message.edit({
      content: `Scan complete! Analyzing ${result.messagesScanned} messages for potential misinformation...\n\n**Scan ID:** \`${result.scanId}\``,
    });

    if (result.status === 'failed' || result.status === 'timeout') {
      await interaction.message.edit({
        content: `Scan analysis failed. Please try again later.\n\n**Scan ID:** \`${result.scanId}\``,
      });
      return;
    }

    const warningText = result.warningMessage ? `\n\n**Warning:** ${result.warningMessage}` : '';

    if (result.flaggedMessages.length === 0) {
      await interaction.message.edit({
        content: `**Scan Complete**\n\n**Scan ID:** \`${result.scanId}\`\n**Messages scanned:** ${result.messagesScanned}\n**Period:** Last ${state.selectedDays} day${state.selectedDays !== 1 ? 's' : ''}\n\nNo flashpoints or potential misinformation were detected. Your community looks healthy!${warningText}`,
      });
    } else {
      await interaction.message.edit({
        content: `**Scan Complete**\n\n**Scan ID:** \`${result.scanId}\`\n**Messages scanned:** ${result.messagesScanned}\n**Flagged:** ${result.flaggedMessages.length}\n\nUse \`/vibecheck ${state.selectedDays}\` for detailed results and to create note requests.${warningText}`,
      });
    }
  } catch (error) {
    const errorDetails = extractErrorDetails(error);
    logger.error('Vibe check scan from prompt failed', {
      error_id: errorId,
      guild_id: state.guildId,
      error: errorDetails.message,
      error_type: errorDetails.type,
      stack: errorDetails.stack,
    });

    await interaction.message.edit({
      content: 'The scan encountered an error. Please try using `/vibecheck` instead.',
    });
  }
}
