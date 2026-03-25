import {
  TextChannel,
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
  User,
  Message as DiscordMessage,
} from 'discord.js';
import { logger } from '../logger.js';
import { generateErrorId } from './errors.js';
import { VIBE_CHECK_DAYS_OPTIONS } from '../types/bulk-scan.js';
import { setVibecheckPromptState } from '../handlers/vibecheck-prompt-handler.js';
import {
  createContainer,
  createTextSection,
  V2_COLORS,
  v2MessageFlags,
} from '../utils/v2-components.js';

export const VIBECHECK_PROMPT_CUSTOM_IDS = {
  DAYS_PREFIX: 'vibecheck_days:',
  START: 'vibecheck_prompt_start',
  NO_THANKS: 'vibecheck_prompt_no_thanks',
} as const;

export interface VibeCheckPromptOptions {
  botChannel: TextChannel;
  admin: User;
  guildId: string;
}

export function createDaysButtons(selectedDays: number | null = null): ActionRowBuilder<ButtonBuilder> {
  const row = new ActionRowBuilder<ButtonBuilder>();
  for (const option of VIBE_CHECK_DAYS_OPTIONS) {
    const isSelected = option.value === selectedDays;
    const button = new ButtonBuilder()
      .setCustomId(`${VIBECHECK_PROMPT_CUSTOM_IDS.DAYS_PREFIX}${option.value}`)
      .setLabel(option.name)
      .setStyle(isSelected ? ButtonStyle.Primary : ButtonStyle.Secondary);
    row.addComponents(button);
  }
  return row;
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

  const promptText = `<@${admin.id}> **Vibe Check Available**\n\nWould you like to scan your server for potential misinformation? This will check recent messages against known fact-checking databases.\n\nSelect how many days back you'd like to scan:`;

  const container = createContainer(V2_COLORS.INFO);
  container.addTextDisplayComponents(createTextSection(promptText));
  container.addActionRowComponents(createDaysButtons());
  container.addActionRowComponents(createPromptButtons(false));

  let message: DiscordMessage;
  try {
    message = await botChannel.send({
      components: [container.toJSON()],
      flags: v2MessageFlags(),
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

  try {
    await setVibecheckPromptState(message.id, {
      guildId,
      adminId: admin.id,
      botChannelId: botChannel.id,
      selectedDays: null,
    });

    logger.debug('Vibecheck prompt state stored in Redis', {
      error_id: errorId,
      message_id: message.id,
      guild_id: guildId,
      admin_id: admin.id,
    });
  } catch (cacheError) {
    logger.error('Failed to store vibecheck prompt state in Redis', {
      error_id: errorId,
      message_id: message.id,
      error: cacheError instanceof Error ? cacheError.message : String(cacheError),
    });

    try {
      const errorContainer = createContainer(V2_COLORS.CRITICAL);
      errorContainer.addTextDisplayComponents(
        createTextSection('Failed to set up vibe check prompt. Please use `/vibecheck` instead.')
      );
      await message.edit({
        components: [errorContainer.toJSON()],
        flags: v2MessageFlags(),
      });
    } catch (editError) {
      logger.debug('Failed to edit message after state storage failure', {
        error_id: errorId,
        message_id: message.id,
        error: editError instanceof Error ? editError.message : String(editError),
      });
    }
  }
}
