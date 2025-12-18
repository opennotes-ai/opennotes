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
} from 'discord.js';
import { DiscordSnowflake } from '@sapphire/snowflake';
import { nanoid } from 'nanoid';
import { logger } from '../logger.js';
import { generateErrorId, extractErrorDetails, formatErrorForUser } from '../lib/errors.js';
import { hasManageGuildPermission } from '../lib/permissions.js';
import { natsPublisher } from '../events/NatsPublisher.js';
import {
  VIBE_CHECK_DAYS_OPTIONS,
  BULK_SCAN_BATCH_SIZE,
  NATS_SUBJECTS,
  type BulkScanMessage,
  type BulkScanBatch,
  type ScanProgress,
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
    const scanId = nanoid();
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

    logger.info('Vibecheck scan complete', {
      error_id: errorId,
      scan_id: scanId,
      guild_id: guildId,
      days,
      channels_scanned: channelsProcessed,
      messages_processed: messagesProcessed,
      batches_published: totalBatches,
    });

    await interaction.editReply({
      content: `Scan complete!\n\n` +
        `**Scan ID:** \`${scanId}\`\n` +
        `**Period:** Last ${days} day${days !== 1 ? 's' : ''}\n` +
        `**Channels scanned:** ${channelsProcessed}\n` +
        `**Messages processed:** ${messagesProcessed}\n` +
        `**Batches sent for analysis:** ${totalBatches}\n\n` +
        `Results will be processed by the server. Use \`/list requests\` to see flagged content once analysis is complete.`,
    });
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
