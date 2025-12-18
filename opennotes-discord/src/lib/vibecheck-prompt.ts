import {
  TextChannel,
  StringSelectMenuBuilder,
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
  ButtonInteraction,
  MessageComponentInteraction,
  ChannelType,
  Collection,
  Message as DiscordMessage,
} from 'discord.js';
import type { TextChannel as GuildTextChannel } from 'discord.js';
import { logger } from '../logger.js';
import { apiClient } from '../api-client.js';
import { natsPublisher } from '../events/NatsPublisher.js';
import { generateErrorId, extractErrorDetails } from './errors.js';
import {
  VIBE_CHECK_DAYS_OPTIONS,
  BULK_SCAN_BATCH_SIZE,
  NATS_SUBJECTS,
  type BulkScanMessage,
  type BulkScanBatch,
} from '../types/bulk-scan.js';
import { DiscordSnowflake } from '@sapphire/snowflake';

export const VIBECHECK_PROMPT_CUSTOM_IDS = {
  DAYS_SELECT: 'vibecheck_prompt_days',
  START: 'vibecheck_prompt_start',
  NO_THANKS: 'vibecheck_prompt_no_thanks',
} as const;

const COLLECTOR_TIMEOUT_MS = 300000;
const POLL_INTERVAL_MS = 2000;
const POLL_TIMEOUT_MS = 60000;

export interface VibeCheckPromptOptions {
  channel: TextChannel;
  adminId: string;
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
  const { channel, adminId, guildId } = options;
  const errorId = generateErrorId();

  logger.info('Sending vibe check prompt to admin', {
    error_id: errorId,
    channel_id: channel.id,
    admin_id: adminId,
    guild_id: guildId,
  });

  const content = `**Vibe Check Available**

Would you like to scan your server for potential misinformation? This will check recent messages against known fact-checking databases.

Select how many days back you'd like to scan:`;

  const selectRow = new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(
    createDaysSelectMenu()
  );
  const buttonRow = createPromptButtons(false);

  const message = await channel.send({
    content,
    components: [selectRow, buttonRow],
  });

  let selectedDays: number | null = null;

  const collector = message.createMessageComponentCollector({
    filter: (interaction: MessageComponentInteraction) => interaction.user.id === adminId,
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
            channel,
            message,
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
  channel: TextChannel;
  message: DiscordMessage;
  errorId: string;
}

async function runVibeCheckScan(options: RunVibeCheckScanOptions): Promise<void> {
  const { interaction, guildId, days, channel, message, errorId } = options;

  const guild = channel.guild;
  if (!guild) {
    await message.edit({
      content: 'Unable to access server information. Please try `/vibecheck` instead.',
    });
    return;
  }

  try {
    const cutoffTimestamp = Date.now() - days * 24 * 60 * 60 * 1000;
    const cutoffSnowflake = DiscordSnowflake.generate({ timestamp: BigInt(cutoffTimestamp) });

    const textChannels = guild.channels.cache.filter(
      (ch): ch is GuildTextChannel =>
        ch.type === ChannelType.GuildText && ch.viewable === true
    );

    const totalChannels = textChannels.size;

    if (totalChannels === 0) {
      await message.edit({
        content: 'No accessible text channels found to scan.',
      });
      return;
    }

    const scanResponse = await apiClient.initiateBulkScan(guildId, days);
    const scanId = scanResponse.scan_id;

    logger.info('Initiated bulk scan from prompt', {
      error_id: errorId,
      scan_id: scanId,
      guild_id: guildId,
      days,
    });

    let messagesProcessed = 0;
    let batchIndex = 0;
    let currentBatch: BulkScanMessage[] = [];

    const publishBatch = async (): Promise<void> => {
      if (currentBatch.length === 0) {
        return;
      }

      const batch: BulkScanBatch = {
        scanId,
        guildId,
        initiatedBy: interaction.user.id,
        batchIndex,
        totalBatches: -1,
        messages: currentBatch,
        cutoffTimestamp: new Date(cutoffTimestamp).toISOString(),
      };

      try {
        await natsPublisher.publishBulkScanBatch(NATS_SUBJECTS.BULK_SCAN_BATCH, batch);
        logger.debug('Published batch from prompt', {
          scanId,
          batchIndex,
          messageCount: currentBatch.length,
        });
      } catch (error) {
        logger.warn('Failed to publish batch to NATS, continuing scan', {
          error: error instanceof Error ? error.message : String(error),
          scanId,
          batchIndex,
        });
      }

      batchIndex++;
      currentBatch = [];
    };

    for (const [, ch] of textChannels) {
      try {
        let lastMessageId: string | undefined;
        let reachedCutoff = false;

        while (!reachedCutoff) {
          const fetchOptions: { limit: number; before?: string } = { limit: 100 };
          if (lastMessageId) {
            fetchOptions.before = lastMessageId;
          }

          let messages: Collection<string, DiscordMessage>;
          try {
            messages = await ch.messages.fetch(fetchOptions);
          } catch {
            break;
          }

          if (messages.size === 0) {
            break;
          }

          for (const [messageId, msg] of messages) {
            if (BigInt(messageId) < cutoffSnowflake) {
              reachedCutoff = true;
              break;
            }

            if (msg.author.bot) {
              continue;
            }

            if (!msg.content && msg.attachments.size === 0 && msg.embeds.length === 0) {
              continue;
            }

            const scanMessage: BulkScanMessage = {
              messageId: msg.id,
              channelId: ch.id,
              guildId,
              content: msg.content,
              authorId: msg.author.id,
              authorUsername: msg.author.username,
              timestamp: msg.createdAt.toISOString(),
              attachmentUrls: msg.attachments.size > 0
                ? Array.from(msg.attachments.values()).map((a) => a.url)
                : undefined,
              embedContent: msg.embeds.length > 0
                ? msg.embeds.map((e) => e.description || e.title || '').filter(Boolean).join('\n')
                : undefined,
            };

            currentBatch.push(scanMessage);
            messagesProcessed++;

            if (currentBatch.length >= BULK_SCAN_BATCH_SIZE) {
              await publishBatch();
            }

            lastMessageId = messageId;
          }

          if (messages.size < 100) {
            break;
          }

          lastMessageId = messages.last()?.id;
          if (!lastMessageId) {
            break;
          }
        }
      } catch (channelError) {
        logger.debug('Error processing channel in vibe check', {
          error_id: errorId,
          channel_id: ch.id,
          error: channelError instanceof Error ? channelError.message : String(channelError),
        });
      }
    }

    if (currentBatch.length > 0) {
      await publishBatch();
    }

    await message.edit({
      content: `Scan complete! Analyzing ${messagesProcessed} messages for potential misinformation...\n\n**Scan ID:** \`${scanId}\``,
    });

    const results = await pollForResults(scanId, errorId);

    if (!results || results.status === 'failed') {
      await message.edit({
        content: `Scan analysis failed. Please try again later.\n\n**Scan ID:** \`${scanId}\``,
      });
      return;
    }

    if (results.flagged_messages.length === 0) {
      await message.edit({
        content: `**Scan Complete**\n\n**Scan ID:** \`${scanId}\`\n**Messages scanned:** ${results.messages_scanned}\n**Period:** Last ${days} day${days !== 1 ? 's' : ''}\n\nNo potential misinformation was detected. Your community looks healthy!`,
      });
    } else {
      await message.edit({
        content: `**Scan Complete**\n\n**Scan ID:** \`${scanId}\`\n**Messages scanned:** ${results.messages_scanned}\n**Flagged:** ${results.flagged_messages.length}\n\nUse \`/vibecheck ${days}\` for detailed results and to create note requests.`,
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

    await message.edit({
      content: 'The scan encountered an error. Please try using `/vibecheck` instead.',
    });
  }
}

async function pollForResults(
  scanId: string,
  errorId: string
): Promise<Awaited<ReturnType<typeof apiClient.getBulkScanResults>> | null> {
  const startTime = Date.now();

  while (Date.now() - startTime < POLL_TIMEOUT_MS) {
    try {
      const results = await apiClient.getBulkScanResults(scanId);

      if (results.status === 'completed' || results.status === 'failed') {
        return results;
      }

      await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
    } catch (error) {
      logger.warn('Error polling for scan results', {
        error_id: errorId,
        scan_id: scanId,
        error: error instanceof Error ? error.message : String(error),
      });
      await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
    }
  }

  logger.warn('Scan polling timed out', {
    error_id: errorId,
    scan_id: scanId,
    timeout_ms: POLL_TIMEOUT_MS,
  });

  return null;
}
