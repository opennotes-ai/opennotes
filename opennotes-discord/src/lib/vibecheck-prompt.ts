import {
  TextChannel,
  StringSelectMenuBuilder,
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

export const VIBECHECK_PROMPT_CUSTOM_IDS = {
  DAYS_SELECT: 'vibecheck_prompt_days',
  START: 'vibecheck_prompt_start',
  NO_THANKS: 'vibecheck_prompt_no_thanks',
} as const;

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
  }
}
