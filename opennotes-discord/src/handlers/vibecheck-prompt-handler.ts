import {
  MessageComponentInteraction,
  ButtonInteraction,
  TextChannel,
  type APIContainerComponent,
} from 'discord.js';
import { cache } from '../cache.js';
import { logger } from '../logger.js';
import { generateErrorId, extractErrorDetails } from '../lib/errors.js';
import {
  VIBECHECK_PROMPT_CUSTOM_IDS,
  createDaysButtons,
  createPromptButtons,
} from '../lib/vibecheck-prompt.js';
import { executeBulkScan } from '../lib/bulk-scan-executor.js';
import { recordStalledScan } from '../lib/vibecheck-stalled-scan.js';
import { createStallWarningController } from '../lib/vibecheck-stall-warning.js';
import {
  createContainer,
  createTextSection,
  createDivider,
  V2_COLORS,
  V2_ICONS,
  v2MessageFlags,
} from '../utils/v2-components.js';
import { buildContextualNav } from '../lib/navigation-components.js';

const VIBECHECK_PROMPT_TTL_SECONDS = 900;

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
    customId.startsWith(VIBECHECK_PROMPT_CUSTOM_IDS.DAYS_PREFIX) ||
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

      const container = createContainer(V2_COLORS.INFO);
      container.addTextDisplayComponents(
        createTextSection('This vibe check prompt has expired. You can run `/vibecheck` anytime to scan your server.')
      );
      await interaction.update({
        components: [container],
        flags: v2MessageFlags(),
      });
      return;
    }

    if (interaction.user.id !== state.adminId) {
      const container = createContainer(V2_COLORS.CRITICAL);
      container.addTextDisplayComponents(
        createTextSection('Only the server admin who received this prompt can interact with it.')
      );
      await interaction.reply({
        components: [container],
        flags: v2MessageFlags({ ephemeral: true }),
      });
      return;
    }

    await cache.expire(getCacheKey(messageId), VIBECHECK_PROMPT_TTL_SECONDS);

    if (interaction.isButton()) {
      if (interaction.customId.startsWith(VIBECHECK_PROMPT_CUSTOM_IDS.DAYS_PREFIX)) {
        await handleDaysButton(interaction, state, messageId, errorId);
      } else if (interaction.customId === VIBECHECK_PROMPT_CUSTOM_IDS.NO_THANKS) {
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
      const errorContainer = createContainer(V2_COLORS.CRITICAL);
      errorContainer.addTextDisplayComponents(
        createTextSection('An error occurred. Please try using `/vibecheck` instead.')
      );
      if (interaction.deferred || interaction.replied) {
        await interaction.followUp({
          components: [errorContainer],
          flags: v2MessageFlags({ ephemeral: true }),
        });
      } else {
        await interaction.reply({
          components: [errorContainer],
          flags: v2MessageFlags({ ephemeral: true }),
        });
      }
    } catch {
      logger.debug('Failed to send error response for vibecheck prompt', {
        error_id: errorId,
      });
    }
  }
}

async function handleDaysButton(
  interaction: ButtonInteraction,
  state: VibecheckPromptState,
  messageId: string,
  errorId: string
): Promise<void> {
  const dayStr = interaction.customId.slice(VIBECHECK_PROMPT_CUSTOM_IDS.DAYS_PREFIX.length);
  const selectedDays = parseInt(dayStr, 10);

  if (isNaN(selectedDays) || selectedDays <= 0) {
    logger.warn('Invalid days selection in vibecheck prompt', {
      error_id: errorId,
      message_id: messageId,
      raw_value: dayStr,
    });
    const container = createContainer(V2_COLORS.CRITICAL);
    container.addTextDisplayComponents(
      createTextSection('Invalid selection. Please try again.')
    );
    await interaction.reply({
      components: [container],
      flags: v2MessageFlags({ ephemeral: true }),
    });
    return;
  }

  const updatedState: VibecheckPromptState = {
    ...state,
    selectedDays,
  };
  await setVibecheckPromptState(messageId, updatedState);

  const container = createContainer(V2_COLORS.INFO);
  container.addTextDisplayComponents(
    createTextSection(`**Vibe Check Available**\n\nWould you like to scan your server for potential misinformation? This will check recent messages against known fact-checking databases.\n\nSelected: **${selectedDays} day${selectedDays === 1 ? '' : 's'}**`)
  );
  container.addActionRowComponents(createDaysButtons(selectedDays));
  container.addActionRowComponents(createPromptButtons(true));

  await interaction.update({
    components: [container],
    flags: v2MessageFlags(),
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

  const container = createContainer(V2_COLORS.INFO);
  container.addTextDisplayComponents(
    createTextSection('Vibe check prompt dismissed. You can run `/vibecheck` anytime to scan your server.')
  );

  await interaction.update({
    components: [container],
    flags: v2MessageFlags(),
  });

  logger.debug('Vibecheck prompt dismissed', {
    error_id: errorId,
    message_id: messageId,
  });
}

function buildMessageContainer(text: string, color: number = V2_COLORS.INFO): { components: APIContainerComponent[]; flags: number } {
  const container = createContainer(color);
  container.addTextDisplayComponents(createTextSection(text));
  return {
    components: [container.toJSON()],
    flags: v2MessageFlags(),
  };
}

function buildTerminalContainer(text: string, color: number = V2_COLORS.COMPLETE): { components: APIContainerComponent[]; flags: number } {
  const container = createContainer(color);
  container.addTextDisplayComponents(createTextSection(text));
  container.addSeparatorComponents(createDivider());
  container.addActionRowComponents(buildContextualNav('vibecheck:scan'));
  return {
    components: [container.toJSON()],
    flags: v2MessageFlags(),
  };
}

async function handleStart(
  interaction: ButtonInteraction,
  state: VibecheckPromptState,
  messageId: string,
  errorId: string
): Promise<void> {
  if (state.selectedDays === null) {
    const container = createContainer(V2_COLORS.HIGH);
    container.addTextDisplayComponents(
      createTextSection('Please select the number of days to scan first.')
    );
    await interaction.reply({
      components: [container],
      flags: v2MessageFlags({ ephemeral: true }),
    });
    return;
  }

  const selectedDays = state.selectedDays;

  await deleteVibecheckPromptState(messageId);

  const startContainer = createContainer(V2_COLORS.INFO);
  startContainer.addTextDisplayComponents(
    createTextSection(`${V2_ICONS.PENDING} Starting vibe check scan for the last ${state.selectedDays} day${state.selectedDays === 1 ? '' : 's'}...`)
  );
  await interaction.update({
    components: [startContainer],
    flags: v2MessageFlags(),
  });

  const channel = interaction.channel;
  if (!channel || !(channel instanceof TextChannel)) {
    await interaction.message.edit(
      buildMessageContainer('Unable to access channel information. Please try `/vibecheck` instead.', V2_COLORS.CRITICAL)
    );
    return;
  }

  const guild = channel.guild;
  if (!guild) {
    await interaction.message.edit(
      buildMessageContainer('Unable to access server information. Please try `/vibecheck` instead.', V2_COLORS.CRITICAL)
    );
    return;
  }

  try {
    const stallWarningController = createStallWarningController(async (scanId) => {
      await recordStalledScan({
        scanId,
        initiatorId: interaction.user.id,
        guildId: state.guildId,
        days: selectedDays,
        source: 'prompt',
      });
      await interaction.message.edit(
        buildMessageContainer(
          `${V2_ICONS.WARNING} Scan is taking longer than we can keep updated.\n\nUse \`/vibecheck status scan_id:${scanId}\` to check later.\n\n**Scan ID:** \`${scanId}\``,
          V2_COLORS.HIGH
        )
      );
    });
    const result = await executeBulkScan({
      guild,
      days: selectedDays,
      initiatorId: interaction.user.id,
      errorId,
      stallWarningCallback: async (scanId) => {
        await stallWarningController.onStallWarning(scanId);
      },
    });

    if (result.channelsScanned === 0) {
      await interaction.message.edit(
        buildMessageContainer('No accessible text channels found to scan.', V2_COLORS.HIGH)
      );
      return;
    }

    if (await stallWarningController.shouldSuppressUpdates()) {
      return;
    }

    await interaction.message.edit(
      buildMessageContainer(
        `${V2_ICONS.PENDING} Scan complete! Analyzing ${result.messagesScanned} messages for potential misinformation...\n\n**Scan ID:** \`${result.scanId}\``,
        V2_COLORS.INFO
      )
    );

    if (result.status === 'timeout') {
      await interaction.message.edit(
        buildTerminalContainer(
          `${V2_ICONS.WARNING} Scan analysis is taking longer than expected and may still be running.\n\nUse \`/vibecheck status\` to check completion.\n\n**Scan ID:** \`${result.scanId}\``,
          V2_COLORS.HIGH
        )
      );
      return;
    }

    if (result.status === 'failed') {
      await interaction.message.edit(
        buildTerminalContainer(
          `${V2_ICONS.NOT_HELPFUL} Scan analysis failed. Please try again later.\n\n**Scan ID:** \`${result.scanId}\``,
          V2_COLORS.CRITICAL
        )
      );
      return;
    }

    const warningText = result.warningMessage ? `\n\n**Warning:** ${result.warningMessage}` : '';

    if (result.flaggedMessages.length === 0) {
      await interaction.message.edit(
        buildTerminalContainer(
          `${V2_ICONS.HELPFUL} **Scan Complete**\n\n**Scan ID:** \`${result.scanId}\`\n**Messages scanned:** ${result.messagesScanned}\n**Period:** Last ${selectedDays} day${selectedDays !== 1 ? 's' : ''}\n\nNo flashpoints or potential misinformation were detected. Your community looks healthy!${warningText}`,
          V2_COLORS.COMPLETE
        )
      );
    } else {
      await interaction.message.edit(
        buildTerminalContainer(
          `${V2_ICONS.WARNING} **Scan Complete**\n\n**Scan ID:** \`${result.scanId}\`\n**Messages scanned:** ${result.messagesScanned}\n**Flagged:** ${result.flaggedMessages.length}\n\nUse \`/vibecheck ${selectedDays}\` for detailed results and to create note requests.${warningText}`,
          V2_COLORS.HIGH
        )
      );
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

    await interaction.message.edit(
      buildMessageContainer('The scan encountered an error. Please try using `/vibecheck` instead.', V2_COLORS.CRITICAL)
    );
  }
}
