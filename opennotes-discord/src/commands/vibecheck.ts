import {
  SlashCommandBuilder,
  ChatInputCommandInteraction,
  MessageFlags,
  PermissionFlagsBits,
  GuildMember,
  TextChannel,
  ChannelType,
  Message,
  Collection,
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
  ComponentType,
  ButtonInteraction,
} from 'discord.js';
import { DiscordSnowflake } from '@sapphire/snowflake';
import { logger } from '../logger.js';
import { generateErrorId, extractErrorDetails, formatErrorForUser } from '../lib/errors.js';
import { hasManageGuildPermission } from '../lib/permissions.js';
import { natsPublisher } from '../events/NatsPublisher.js';
import { apiClient } from '../api-client.js';
import {
  VIBE_CHECK_DAYS_OPTIONS,
  BULK_SCAN_BATCH_SIZE,
  NATS_SUBJECTS,
  type BulkScanMessage,
  type BulkScanBatch,
  type ScanProgress,
  type FlaggedMessage,
} from '../types/bulk-scan.js';

export const data = new SlashCommandBuilder()
  .setName('vibecheck')
  .setDescription('Scan recent messages for potential misinformation (Admin only)')
  .addIntegerOption(option =>
    option
      .setName('days')
      .setDescription('Number of days to scan back')
      .setRequired(true)
      .addChoices(
        ...VIBE_CHECK_DAYS_OPTIONS.map(opt => ({
          name: opt.name,
          value: opt.value,
        }))
      )
  )
  .setDefaultMemberPermissions(PermissionFlagsBits.ManageGuild)
  .setDMPermission(false);

export async function execute(interaction: ChatInputCommandInteraction): Promise<void> {
  const errorId = generateErrorId();
  const userId = interaction.user.id;
  const guildId = interaction.guildId;
  const guild = interaction.guild;

  if (!guildId || !guild) {
    await interaction.reply({
      content: 'This command can only be used in a server.',
      flags: MessageFlags.Ephemeral,
    });
    return;
  }

  const member = interaction.member as GuildMember | null;
  if (!hasManageGuildPermission(member)) {
    await interaction.reply({
      content: 'You need the "Manage Server" permission to use this command.',
      flags: MessageFlags.Ephemeral,
    });
    return;
  }

  const days = interaction.options.getInteger('days', true);

  logger.info('Starting vibecheck scan', {
    error_id: errorId,
    command: 'vibecheck',
    user_id: userId,
    guild_id: guildId,
    guild_name: guild.name,
    days,
  });

  await interaction.deferReply({
    flags: MessageFlags.Ephemeral,
  });

  try {
    const cutoffTimestamp = Date.now() - days * 24 * 60 * 60 * 1000;
    const cutoffSnowflake = DiscordSnowflake.generate({ timestamp: BigInt(cutoffTimestamp) });

    const textChannels = guild.channels.cache.filter(
      (channel): channel is TextChannel =>
        channel.type === ChannelType.GuildText && channel.viewable
    );

    const totalChannels = textChannels.size;

    if (totalChannels === 0) {
      await interaction.editReply({
        content: 'No accessible text channels found to scan.',
      });
      return;
    }

    const scanResponse = await apiClient.initiateBulkScan(guildId, days);
    const scanId = scanResponse.scan_id;

    logger.info('Initiated bulk scan on server', {
      error_id: errorId,
      scan_id: scanId,
      guild_id: guildId,
      days,
    });

    let messagesProcessed = 0;
    let channelsProcessed = 0;
    let batchIndex = 0;
    let currentBatch: BulkScanMessage[] = [];

    const updateProgress = async (progress: ScanProgress): Promise<void> => {
      const percent = totalChannels > 0
        ? Math.round((progress.channelsProcessed / progress.totalChannels) * 100)
        : 0;

      await interaction.editReply({
        content: `Scanning... ${percent}% complete\n` +
          `Channels: ${progress.channelsProcessed}/${progress.totalChannels}\n` +
          `Messages processed: ${progress.messagesProcessed}\n` +
          (progress.currentChannel ? `Current channel: #${progress.currentChannel}` : ''),
      });
    };

    const publishBatch = async (): Promise<void> => {
      if (currentBatch.length === 0) {
        return;
      }

      const batch: BulkScanBatch = {
        scanId,
        guildId,
        initiatedBy: userId,
        batchIndex,
        totalBatches: -1,
        messages: currentBatch,
        cutoffTimestamp: new Date(cutoffTimestamp).toISOString(),
      };

      try {
        await natsPublisher.publishBulkScanBatch(NATS_SUBJECTS.BULK_SCAN_BATCH, batch);
        logger.debug('Published batch', {
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

    for (const [, channel] of textChannels) {
      try {
        await updateProgress({
          channelsProcessed,
          totalChannels,
          messagesProcessed,
          currentChannel: channel.name,
        });

        let lastMessageId: string | undefined;
        let reachedCutoff = false;

        while (!reachedCutoff) {
          const fetchOptions: { limit: number; before?: string } = { limit: 100 };
          if (lastMessageId) {
            fetchOptions.before = lastMessageId;
          }

          let messages: Collection<string, Message>;
          try {
            messages = await channel.messages.fetch(fetchOptions);
          } catch (fetchError) {
            logger.warn('Failed to fetch messages from channel', {
              error_id: errorId,
              channel_id: channel.id,
              channel_name: channel.name,
              error: fetchError instanceof Error ? fetchError.message : String(fetchError),
            });
            break;
          }

          if (messages.size === 0) {
            break;
          }

          for (const [messageId, message] of messages) {
            if (BigInt(messageId) < cutoffSnowflake) {
              reachedCutoff = true;
              break;
            }

            if (message.author.bot) {
              continue;
            }

            if (!message.content && message.attachments.size === 0 && message.embeds.length === 0) {
              continue;
            }

            const scanMessage: BulkScanMessage = {
              messageId: message.id,
              channelId: channel.id,
              guildId,
              content: message.content,
              authorId: message.author.id,
              authorUsername: message.author.username,
              timestamp: message.createdAt.toISOString(),
              attachmentUrls: message.attachments.size > 0
                ? Array.from(message.attachments.values()).map(a => a.url)
                : undefined,
              embedContent: message.embeds.length > 0
                ? message.embeds.map(e => e.description || e.title || '').filter(Boolean).join('\n')
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

        channelsProcessed++;
      } catch (channelError) {
        logger.error('Error processing channel', {
          error_id: errorId,
          channel_id: channel.id,
          channel_name: channel.name,
          error: channelError instanceof Error ? channelError.message : String(channelError),
        });
        channelsProcessed++;
      }
    }

    if (currentBatch.length > 0) {
      await publishBatch();
    }

    const totalBatches = batchIndex;

    logger.info('Vibecheck Discord scan complete, polling for results', {
      error_id: errorId,
      scan_id: scanId,
      guild_id: guildId,
      days,
      channels_scanned: channelsProcessed,
      messages_processed: messagesProcessed,
      batches_published: totalBatches,
    });

    await interaction.editReply({
      content: `Scan complete! Analyzing ${messagesProcessed} messages for potential misinformation...\n\n` +
        `**Scan ID:** \`${scanId}\``,
    });

    const results = await pollForResults(scanId, errorId);

    if (!results || results.status === 'failed') {
      await interaction.editReply({
        content: `Scan analysis failed. Please try again later.\n\n` +
          `**Scan ID:** \`${scanId}\``,
      });
      return;
    }

    if (results.flagged_messages.length === 0) {
      await interaction.editReply({
        content: `Scan complete! No flagged content found.\n\n` +
          `**Scan ID:** \`${scanId}\`\n` +
          `**Messages scanned:** ${results.messages_scanned}\n` +
          `**Period:** Last ${days} day${days !== 1 ? 's' : ''}\n\n` +
          `No potential misinformation was detected.`,
      });
      return;
    }

    await displayFlaggedResults(
      interaction,
      scanId,
      guildId,
      days,
      results.messages_scanned,
      results.flagged_messages
    );
  } catch (error) {
    const errorDetails = extractErrorDetails(error);

    logger.error('Vibecheck scan failed', {
      error_id: errorId,
      command: 'vibecheck',
      user_id: userId,
      guild_id: guildId,
      error: errorDetails.message,
      error_type: errorDetails.type,
      stack: errorDetails.stack,
    });

    await interaction.editReply({
      content: formatErrorForUser(errorId, 'The scan encountered an error. Please try again later.'),
    });
  }
}

const POLL_INTERVAL_MS = 2000;
const POLL_TIMEOUT_MS = 60000;

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

      await new Promise(resolve => setTimeout(resolve, POLL_INTERVAL_MS));
    } catch (error) {
      logger.warn('Error polling for scan results', {
        error_id: errorId,
        scan_id: scanId,
        error: error instanceof Error ? error.message : String(error),
      });
      await new Promise(resolve => setTimeout(resolve, POLL_INTERVAL_MS));
    }
  }

  logger.warn('Scan polling timed out', {
    error_id: errorId,
    scan_id: scanId,
    timeout_ms: POLL_TIMEOUT_MS,
  });

  return null;
}

function formatMatchScore(score: number): string {
  return `${Math.round(score * 100)}%`;
}

function formatMessageLink(guildId: string, channelId: string, messageId: string): string {
  return `https://discord.com/channels/${guildId}/${channelId}/${messageId}`;
}

function truncateContent(content: string, maxLength: number = 100): string {
  if (content.length <= maxLength) {
    return content;
  }
  return content.slice(0, maxLength - 3) + '...';
}

async function displayFlaggedResults(
  interaction: ChatInputCommandInteraction,
  scanId: string,
  guildId: string,
  days: number,
  messagesScanned: number,
  flaggedMessages: FlaggedMessage[]
): Promise<void> {
  const resultsContent = flaggedMessages.slice(0, 10).map((msg, index) => {
    const messageLink = formatMessageLink(guildId, msg.channel_id, msg.message_id);
    const confidence = formatMatchScore(msg.match_score);
    const preview = truncateContent(msg.content);

    return `**${index + 1}.** [Message](${messageLink})\n` +
      `   Confidence: **${confidence}**\n` +
      `   Matched: "${msg.matched_claim}"\n` +
      `   Preview: "${preview}"`;
  }).join('\n\n');

  const moreCount = flaggedMessages.length > 10 ? flaggedMessages.length - 10 : 0;
  const moreText = moreCount > 0 ? `\n\n_...and ${moreCount} more flagged messages_` : '';

  const createButton = new ButtonBuilder()
    .setCustomId(`vibecheck_create:${scanId}`)
    .setLabel('Create Note Requests')
    .setStyle(ButtonStyle.Primary);

  const dismissButton = new ButtonBuilder()
    .setCustomId(`vibecheck_dismiss:${scanId}`)
    .setLabel('Dismiss')
    .setStyle(ButtonStyle.Secondary);

  const row = new ActionRowBuilder<ButtonBuilder>().addComponents(createButton, dismissButton);

  await interaction.editReply({
    content: `**Scan Results**\n\n` +
      `**Scan ID:** \`${scanId}\`\n` +
      `**Period:** Last ${days} day${days !== 1 ? 's' : ''}\n` +
      `**Messages scanned:** ${messagesScanned}\n` +
      `**Flagged:** ${flaggedMessages.length}\n\n` +
      `${resultsContent}${moreText}`,
    components: [row],
  });

  const reply = await interaction.fetchReply();
  const collector = reply.createMessageComponentCollector({
    componentType: ComponentType.Button,
    time: 300000,
  });

  collector.on('collect', (buttonInteraction: ButtonInteraction) => {
    const [action, buttonScanId] = buttonInteraction.customId.split(':');

    if (buttonScanId !== scanId) {
      return;
    }

    if (action === 'vibecheck_dismiss') {
      void buttonInteraction.update({
        content: 'Results dismissed.',
        components: [],
      }).then(() => {
        collector.stop();
      });
      return;
    }

    if (action === 'vibecheck_create') {
      void showAiGenerationPrompt(buttonInteraction, scanId, flaggedMessages);
    }
  });

  collector.on('end', (_collected, reason) => {
    if (reason === 'time') {
      interaction.editReply({
        content: `Session expired. Please run /vibecheck again if needed.\n\n` +
          `**Scan ID:** \`${scanId}\``,
        components: [],
      }).catch(() => {
        /* Silently ignore - interaction may have expired */
      });
    }
  });
}

async function showAiGenerationPrompt(
  buttonInteraction: ButtonInteraction,
  scanId: string,
  flaggedMessages: FlaggedMessage[]
): Promise<void> {
  const yesAiButton = new ButtonBuilder()
    .setCustomId(`vibecheck_ai_yes:${scanId}`)
    .setLabel('Yes, generate AI notes')
    .setStyle(ButtonStyle.Primary);

  const noAiButton = new ButtonBuilder()
    .setCustomId(`vibecheck_ai_no:${scanId}`)
    .setLabel('No, just create requests')
    .setStyle(ButtonStyle.Secondary);

  const row = new ActionRowBuilder<ButtonBuilder>().addComponents(yesAiButton, noAiButton);

  await buttonInteraction.update({
    content: `Creating note requests for ${flaggedMessages.length} flagged messages.\n\n` +
      `Would you like AI to generate initial note drafts for these messages?`,
    components: [row],
  });

  const message = buttonInteraction.message;
  const aiCollector = message.createMessageComponentCollector({
    componentType: ComponentType.Button,
    time: 60000,
    filter: (i) => i.customId.startsWith('vibecheck_ai_'),
  });

  aiCollector.on('collect', (aiButtonInteraction: ButtonInteraction) => {
    const [, aiAction] = aiButtonInteraction.customId.split('_ai_');
    const generateAiNotes = aiAction.startsWith('yes');

    const messageIds = flaggedMessages.map(msg => msg.message_id);

    void (async () => {
      try {
        const result = await apiClient.createNoteRequestsFromScan(
          scanId,
          messageIds,
          generateAiNotes
        );

        await aiButtonInteraction.update({
          content: `Created ${result.created_count} note request${result.created_count !== 1 ? 's' : ''}` +
            (generateAiNotes ? ' with AI-generated drafts.' : '.') +
            `\n\nUse \`/list requests\` to view and manage them.`,
          components: [],
        });
      } catch (error) {
        logger.error('Failed to create note requests', {
          scan_id: scanId,
          error: error instanceof Error ? error.message : String(error),
        });

        await aiButtonInteraction.update({
          content: 'Failed to create note requests. Please try again later.',
          components: [],
        });
      }

      aiCollector.stop();
    })();
  });

  aiCollector.on('end', (_collected, reason) => {
    if (reason === 'time') {
      buttonInteraction.editReply({
        content: 'Selection timed out. Please run /vibecheck again if needed.',
        components: [],
      }).catch(() => {
        /* Silently ignore - interaction may have expired */
      });
    }
  });
}
