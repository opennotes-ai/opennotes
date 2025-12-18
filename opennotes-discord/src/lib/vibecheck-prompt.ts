import {
  TextChannel,
  StringSelectMenuBuilder,
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
  ButtonInteraction,
  MessageComponentInteraction,
  User,
  Message as DiscordMessage,
} from 'discord.js';
import { logger } from '../logger.js';
import { generateErrorId, extractErrorDetails } from './errors.js';
import { VIBE_CHECK_DAYS_OPTIONS } from '../types/bulk-scan.js';
import { executeBulkScan } from './bulk-scan-executor.js';

export const VIBECHECK_PROMPT_CUSTOM_IDS = {
  DAYS_SELECT: 'vibecheck_prompt_days',
  START: 'vibecheck_prompt_start',
  NO_THANKS: 'vibecheck_prompt_no_thanks',
} as const;

const COLLECTOR_TIMEOUT_MS = 300000;

export interface VibeCheckPromptOptions {
  botChannel: TextChannel;
  admin: User;
  guildId: string;
}

export function createDaysSelectMenu(): StringSelectMenuBuilder {
  return new StringSelectMenuBuilder()
    .setCustomId(VIBECHECK_PROMPT_CUSTOM_IDS.DAYS_SELECT)
    .setPlaceholder('Select number of days to scan')
    .addOptions(
      VIBE_CHECK_DAYS_OPTIONS.map((option) => ({
        label: option.name,
        value: option.value.toString(),
        description: `Scan messages from the last ${option.value} day${option.value === 1 ? '' : 's'}`,
      }))
    );
}

export function createPromptButtons(startEnabled = false): ActionRowBuilder<ButtonBuilder> {
  const startButton = new ButtonBuilder()
    .setCustomId(VIBECHECK_PROMPT_CUSTOM_IDS.START)
    .setLabel('Start Vibe Check')
    .setStyle(ButtonStyle.Primary)
    .setDisabled(!startEnabled);

  const noThanksButton = new ButtonBuilder()
    .setCustomId(VIBECHECK_PROMPT_CUSTOM_IDS.NO_THANKS)
    .setLabel('No Thanks')
    .setStyle(ButtonStyle.Secondary);

  return new ActionRowBuilder<ButtonBuilder>().addComponents(startButton, noThanksButton);
}

export async function sendVibeCheckPrompt(options: VibeCheckPromptOptions): Promise<void> {
  const { botChannel, admin, guildId } = options;
  const errorId = generateErrorId();

  logger.info('Sending vibe check prompt to admin in bot channel', {
    error_id: errorId,
    bot_channel_id: botChannel.id,
    admin_id: admin.id,
    guild_id: guildId,
  });

  const content = `<@${admin.id}> **Vibe Check Available**

Would you like to scan your server for potential misinformation? This will check recent messages against known fact-checking databases.

Select how many days back you'd like to scan:`;

  const selectRow = new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(
    createDaysSelectMenu()
  );
  const buttonRow = createPromptButtons(false);

  let message: DiscordMessage;
  try {
    message = await botChannel.send({
      content,
      components: [selectRow, buttonRow],
    });
  } catch (sendError) {
    logger.warn('Failed to send vibe check prompt in bot channel', {
      error_id: errorId,
      admin_id: admin.id,
      guild_id: guildId,
      bot_channel_id: botChannel.id,
      error: sendError instanceof Error ? sendError.message : String(sendError),
    });
    return;
  }

  let selectedDays: number | null = null;

  const collector = message.createMessageComponentCollector({
    filter: (interaction: MessageComponentInteraction) => interaction.user.id === admin.id,
    time: COLLECTOR_TIMEOUT_MS,
  });

  collector.on('collect', (interaction: MessageComponentInteraction) => {
    void (async (): Promise<void> => { try {
      if (interaction.isStringSelectMenu() && interaction.customId === VIBECHECK_PROMPT_CUSTOM_IDS.DAYS_SELECT) {
        selectedDays = parseInt(interaction.values[0], 10);

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
      } else if (interaction.isButton()) {
        if (interaction.customId === VIBECHECK_PROMPT_CUSTOM_IDS.NO_THANKS) {
          await interaction.update({
            content: 'Vibe check prompt dismissed. You can run `/vibecheck` anytime to scan your server.',
            components: [],
          });
          collector.stop('dismissed');
        } else if (interaction.customId === VIBECHECK_PROMPT_CUSTOM_IDS.START && selectedDays !== null) {
          await interaction.update({
            content: `Starting vibe check scan for the last ${selectedDays} day${selectedDays === 1 ? '' : 's'}...`,
            components: [],
          });

          await runVibeCheckScan({
            interaction,
            guildId,
            days: selectedDays,
            botChannel,
            promptMessage: message,
            errorId,
          });

          collector.stop('started');
        }
      }
    } catch (error) {
      const errorDetails = extractErrorDetails(error);
      logger.error('Error handling vibe check prompt interaction', {
        error_id: errorId,
        error: errorDetails.message,
        error_type: errorDetails.type,
        stack: errorDetails.stack,
      });
    }
    })();
  });

  collector.on('end', (_collected, reason) => {
    void (async (): Promise<void> => {
    if (reason === 'time') {
      try {
        await message.edit({
          content: 'Vibe check prompt expired. You can run `/vibecheck` anytime to scan your server.',
          components: [],
        });
      } catch (error) {
        logger.debug('Failed to edit expired vibe check prompt', {
          error_id: errorId,
          error: error instanceof Error ? error.message : String(error),
        });
      }
    }
    })();
  });
}

interface RunVibeCheckScanOptions {
  interaction: ButtonInteraction;
  guildId: string;
  days: number;
  botChannel: TextChannel;
  promptMessage: DiscordMessage;
  errorId: string;
}

async function runVibeCheckScan(options: RunVibeCheckScanOptions): Promise<void> {
  const { interaction, guildId, days, botChannel, promptMessage, errorId } = options;

  const guild = botChannel.guild;
  if (!guild) {
    await promptMessage.edit({
      content: 'Unable to access server information. Please try `/vibecheck` instead.',
    });
    return;
  }

  try {
    const result = await executeBulkScan({
      guild,
      days,
      initiatorId: interaction.user.id,
      errorId,
    });

    if (result.channelsScanned === 0) {
      await promptMessage.edit({
        content: 'No accessible text channels found to scan.',
      });
      return;
    }

    await promptMessage.edit({
      content: `Scan complete! Analyzing ${result.messagesScanned} messages for potential misinformation...\n\n**Scan ID:** \`${result.scanId}\``,
    });

    if (result.status === 'failed' || result.status === 'timeout') {
      await promptMessage.edit({
        content: `Scan analysis failed. Please try again later.\n\n**Scan ID:** \`${result.scanId}\``,
      });
      return;
    }

    const warningText = result.warningMessage
      ? `\n\n**Warning:** ${result.warningMessage}`
      : '';

    if (result.flaggedMessages.length === 0) {
      await promptMessage.edit({
        content: `**Scan Complete**\n\n**Scan ID:** \`${result.scanId}\`\n**Messages scanned:** ${result.messagesScanned}\n**Period:** Last ${days} day${days !== 1 ? 's' : ''}\n\nNo potential misinformation was detected. Your community looks healthy!${warningText}`,
      });
    } else {
      await promptMessage.edit({
        content: `**Scan Complete**\n\n**Scan ID:** \`${result.scanId}\`\n**Messages scanned:** ${result.messagesScanned}\n**Flagged:** ${result.flaggedMessages.length}\n\nUse \`/vibecheck ${days}\` for detailed results and to create note requests.${warningText}`,
      });
    }
  } catch (error) {
    const errorDetails = extractErrorDetails(error);
    logger.error('Vibe check scan from prompt failed', {
      error_id: errorId,
      guild_id: guildId,
      error: errorDetails.message,
      error_type: errorDetails.type,
      stack: errorDetails.stack,
    });

    await promptMessage.edit({
      content: 'The scan encountered an error. Please try using `/vibecheck` instead.',
    });
  }
}
