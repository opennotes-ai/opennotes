import {
  SlashCommandBuilder,
  ChatInputCommandInteraction,
  MessageFlags,
  PermissionFlagsBits,
  GuildMember,
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
  ComponentType,
  ButtonInteraction,
} from 'discord.js';
import { logger } from '../logger.js';
import { cache } from '../cache.js';
import { generateErrorId, extractErrorDetails, formatErrorForUser } from '../lib/errors.js';
import { hasManageGuildPermission } from '../lib/permissions.js';
import { apiClient } from '../api-client.js';
import {
  VIBE_CHECK_DAYS_OPTIONS,
  type FlaggedMessage,
} from '../types/bulk-scan.js';
import {
  executeBulkScan,
  formatMatchScore,
  formatMessageLink,
  truncateContent,
} from '../lib/bulk-scan-executor.js';
import { BotChannelService } from '../services/BotChannelService.js';
import { serviceProvider } from '../services/index.js';
import { ConfigKey } from '../lib/config-schema.js';

export const VIBECHECK_COOLDOWN_MS = 5 * 60 * 1000;

export function getVibecheckCooldownKey(guildId: string): string {
  return `vibecheck:cooldown:${guildId}`;
}

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

  const cooldownKey = getVibecheckCooldownKey(guildId);
  const lastScanTime = await cache.get<number>(cooldownKey);

  if (lastScanTime !== null) {
    const elapsed = Date.now() - lastScanTime;
    if (elapsed < VIBECHECK_COOLDOWN_MS) {
      const remainingMs = VIBECHECK_COOLDOWN_MS - elapsed;
      const remainingMinutes = Math.ceil(remainingMs / 60000);
      await interaction.reply({
        content: `This server is on cooldown. Please wait ${remainingMinutes} minute${remainingMinutes !== 1 ? 's' : ''} before running another vibecheck.`,
        flags: MessageFlags.Ephemeral,
      });
      return;
    }
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

  await cache.set(cooldownKey, Date.now(), VIBECHECK_COOLDOWN_MS / 1000);

  try {
    const botChannelService = new BotChannelService();
    const guildConfigService = serviceProvider.getGuildConfigService();
    const botChannelName = await guildConfigService.get(guildId, ConfigKey.BOT_CHANNEL_NAME) as string;
    const botChannel = botChannelService.findChannel(guild, botChannelName);

    const excludeChannelIds: string[] = [];
    if (botChannel) {
      excludeChannelIds.push(botChannel.id);
      logger.debug('Excluding bot channel from vibecheck scan', {
        error_id: errorId,
        guild_id: guildId,
        bot_channel_id: botChannel.id,
        bot_channel_name: botChannel.name,
      });
    }

    const result = await executeBulkScan({
      guild,
      days,
      initiatorId: userId,
      errorId,
      excludeChannelIds,
      progressCallback: async (progress) => {
        const percent = progress.totalChannels > 0
          ? Math.round((progress.channelsProcessed / progress.totalChannels) * 100)
          : 0;

        await interaction.editReply({
          content: `Scanning... ${percent}% complete\n` +
            `Channels: ${progress.channelsProcessed}/${progress.totalChannels}\n` +
            `Messages processed: ${progress.messagesProcessed}\n` +
            (progress.currentChannel ? `Current channel: #${progress.currentChannel}` : ''),
        });
      },
    });

    if (result.channelsScanned === 0) {
      await interaction.editReply({
        content: 'No accessible text channels found to scan.',
      });
      return;
    }

    await interaction.editReply({
      content: `Scan complete! Analyzing ${result.messagesScanned} messages for potential misinformation...\n\n` +
        `**Scan ID:** \`${result.scanId}\``,
    });

    if (result.status === 'failed' || result.status === 'timeout') {
      await interaction.editReply({
        content: `Scan analysis failed. Please try again later.\n\n` +
          `**Scan ID:** \`${result.scanId}\``,
      });
      return;
    }

    const warningText = result.warningMessage
      ? `\n\n**Warning:** ${result.warningMessage}`
      : '';

    if (result.flaggedMessages.length === 0) {
      await interaction.editReply({
        content: `Scan complete! No flagged content found.\n\n` +
          `**Scan ID:** \`${result.scanId}\`\n` +
          `**Messages scanned:** ${result.messagesScanned}\n` +
          `**Period:** Last ${days} day${days !== 1 ? 's' : ''}\n\n` +
          `No potential misinformation was detected.${warningText}`,
      });
      return;
    }

    await displayFlaggedResults(
      interaction,
      result.scanId,
      guildId,
      days,
      result.messagesScanned,
      result.flaggedMessages,
      result.warningMessage
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

async function displayFlaggedResults(
  interaction: ChatInputCommandInteraction,
  scanId: string,
  guildId: string,
  days: number,
  messagesScanned: number,
  flaggedMessages: FlaggedMessage[],
  warningMessage?: string
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

  const warningText = warningMessage
    ? `\n\n**Warning:** ${warningMessage}`
    : '';

  await interaction.editReply({
    content: `**Scan Results**\n\n` +
      `**Scan ID:** \`${scanId}\`\n` +
      `**Period:** Last ${days} day${days !== 1 ? 's' : ''}\n` +
      `**Messages scanned:** ${messagesScanned}\n` +
      `**Flagged:** ${flaggedMessages.length}\n\n` +
      `${resultsContent}${moreText}${warningText}`,
    components: [row],
  });

  const reply = await interaction.fetchReply();
  const originalUserId = interaction.user.id;
  const collector = reply.createMessageComponentCollector({
    componentType: ComponentType.Button,
    time: 300000,
    filter: (i) => i.user.id === originalUserId,
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
      void showAiGenerationPrompt(buttonInteraction, scanId, flaggedMessages, originalUserId);
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
  flaggedMessages: FlaggedMessage[],
  originalUserId: string
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
    filter: (i) => i.customId.startsWith('vibecheck_ai_') && i.user.id === originalUserId,
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
