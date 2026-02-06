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
import { nanoid } from 'nanoid';
import pLimit from 'p-limit';
import { logger } from '../logger.js';
import { cache } from '../cache.js';
import { generateErrorId, extractErrorDetails, formatErrorForUser, ApiError } from '../lib/errors.js';
import { hasManageGuildPermission } from '../lib/permissions.js';
import { apiClient, type FlaggedMessageResource } from '../api-client.js';
import { VIBE_CHECK_DAYS_OPTIONS } from '../types/bulk-scan.js';
import { executeBulkScan } from '../lib/bulk-scan-executor.js';
import { formatScanStatusPaginated } from '../lib/scan-status-formatter.js';
import { TextPaginator } from '../lib/text-paginator.js';
import { BotChannelService } from '../services/BotChannelService.js';
import { serviceProvider } from '../services/index.js';
import { ConfigKey } from '../lib/config-schema.js';

interface VibecheckPaginationState {
  scanId: string;
  guildId: string;
  days: number;
  messagesScanned: number;
  flaggedMessages: FlaggedMessageResource[];
  warningMessage?: string;
}

const PAGINATION_STATE_TTL = 300;

export const VIBECHECK_COOLDOWN_MS = 1 * 60 * 1000;

const EXPLANATION_CONCURRENCY_LIMIT = 5;

const EXPLANATION_CACHE_TTL = 28800;

export function getExplanationsCacheKey(scanId: string): string {
  return `vibecheck:explanations:${scanId}`;
}

function createListRequestsButton(): ButtonBuilder {
  return new ButtonBuilder()
    .setCustomId('request_reply:list_requests')
    .setLabel('List Requests')
    .setStyle(ButtonStyle.Primary);
}

function createListNotesButton(): ButtonBuilder {
  return new ButtonBuilder()
    .setCustomId('request_reply:list_notes')
    .setLabel('List Notes')
    .setStyle(ButtonStyle.Secondary);
}

async function fetchExplanations(
  flaggedMessages: FlaggedMessageResource[],
  communityServerId: string
): Promise<Map<string, string>> {
  const explanations = new Map<string, string>();
  const limit = pLimit(EXPLANATION_CONCURRENCY_LIMIT);

  await Promise.all(
    flaggedMessages.map((msg) => limit(async () => {
      const matches = msg.attributes.matches;
      if (!matches || matches.length === 0) {
        return;
      }

      const match = matches[0];
      if (match.scan_type !== 'similarity' || !match.fact_check_item_id) {
        return;
      }

      try {
        const result = await apiClient.generateScanExplanation(
          msg.attributes.content,
          match.fact_check_item_id,
          communityServerId
        );
        explanations.set(msg.id, result.data.attributes.explanation);
      } catch (error) {
        logger.warn('Failed to generate explanation for message', {
          message_id: msg.id,
          error: error instanceof Error ? error.message : 'Unknown error',
        });
      }
    }))
  );

  return explanations;
}

export function getVibecheckCooldownKey(guildId: string): string {
  return `vibecheck:cooldown:${guildId}`;
}

export const data = new SlashCommandBuilder()
  .setName('vibecheck')
  .setDescription('Scan recent messages for potential misinformation (Admin only)')
  .addSubcommand(subcommand =>
    subcommand
      .setName('scan')
      .setDescription('Start a new scan of recent messages')
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
  )
  .addSubcommand(subcommand =>
    subcommand
      .setName('status')
      .setDescription('View the status of the most recent scan')
  )
  .addSubcommand(subcommand =>
    subcommand
      .setName('create-requests')
      .setDescription('Create note requests from a previous scan')
      .addStringOption(option =>
        option
          .setName('scan_id')
          .setDescription('The scan ID to create note requests from')
          .setRequired(true)
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

  const subcommand = interaction.options.getSubcommand();

  if (subcommand === 'status') {
    await handleStatusSubcommand(interaction, guildId, errorId);
    return;
  }

  if (subcommand === 'create-requests') {
    await handleCreateRequestsSubcommand(interaction, guildId, errorId);
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
          `No flashpoints or potential misinformation were detected.${warningText}`,
      });
      return;
    }

    const communityServer = await apiClient.getCommunityServerByPlatformId(guildId);
    const explanations = await fetchExplanations(
      result.flaggedMessages,
      communityServer.data.id
    );

    await displayFlaggedResults(
      interaction,
      result.scanId,
      guildId,
      days,
      result.messagesScanned,
      result.flaggedMessages,
      result.warningMessage,
      explanations
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
  flaggedMessages: FlaggedMessageResource[],
  warningMessage?: string,
  explanations?: Map<string, string>
): Promise<void> {
  const stateId = nanoid(10);
  const currentPage = 1;

  const paginatedResult = formatScanStatusPaginated({
    scan: {
      data: {
        type: 'bulk-scans',
        id: scanId,
        attributes: {
          status: 'completed',
          initiated_at: new Date().toISOString(),
          messages_scanned: messagesScanned,
          messages_flagged: flaggedMessages.length,
        },
      },
      included: flaggedMessages,
      jsonapi: { version: '1.1' },
    },
    guildId,
    days,
    warningMessage,
    includeButtons: true,
    explanations,
  });

  const state: VibecheckPaginationState = {
    scanId,
    guildId,
    days,
    messagesScanned,
    flaggedMessages,
    warningMessage,
  };
  await cache.set(`vibecheck:pagination:${stateId}`, state, PAGINATION_STATE_TTL);

  if (explanations && explanations.size > 0) {
    const explanationsObject = Object.fromEntries(explanations);
    await cache.set(getExplanationsCacheKey(scanId), explanationsObject, EXPLANATION_CACHE_TTL);
  }

  const pageContent = TextPaginator.getPage(paginatedResult.pages, currentPage);
  const fullContent = `${paginatedResult.header}\n${pageContent}`;

  const components: ActionRowBuilder<ButtonBuilder>[] = [];

  if (paginatedResult.pages.totalPages > 1) {
    const paginationRow = TextPaginator.buildPaginationButtons({
      currentPage,
      totalPages: paginatedResult.pages.totalPages,
      customIdPrefix: 'vibecheck_page',
      stateId,
    });
    components.push(paginationRow);
  }

  if (paginatedResult.actionButtons) {
    components.push(paginatedResult.actionButtons);
  }

  await interaction.editReply({
    content: fullContent,
    components,
  });

  const reply = await interaction.fetchReply();
  const originalUserId = interaction.user.id;
  const collector = reply.createMessageComponentCollector({
    componentType: ComponentType.Button,
    time: 300000,
    filter: (i) => i.user.id === originalUserId,
  });

  collector.on('collect', (buttonInteraction: ButtonInteraction) => {
    void handleVibecheckButton(
      buttonInteraction,
      scanId,
      stateId,
      flaggedMessages,
      originalUserId,
      paginatedResult,
      collector
    );
  });

  collector.on('end', (_collected, reason) => {
    if (reason === 'time') {
      const preservedContent = `${paginatedResult.header}\n${TextPaginator.getPage(paginatedResult.pages, 1)}`;
      interaction.editReply({
        content: `${preservedContent}\n\n---\n` +
          `⏰ **Session Expired** - Interactive buttons have been disabled.\n\n` +
          `**Scan ID:** \`${scanId}\`\n\n` +
          `To continue, use one of these commands:\n` +
          `• \`/vibecheck create-requests ${scanId}\` - Create note requests from this scan\n` +
          `• \`/vibecheck status\` - View the latest scan status`,
        components: [],
      }).catch(() => {
        /* Silently ignore - interaction may have expired */
      });
    }
  });
}

async function handleVibecheckButton(
  buttonInteraction: ButtonInteraction,
  scanId: string,
  stateId: string,
  flaggedMessages: FlaggedMessageResource[],
  originalUserId: string,
  paginatedResult: ReturnType<typeof formatScanStatusPaginated>,
  collector: { stop: () => void }
): Promise<void> {
  const customId = buttonInteraction.customId;

  if (customId.startsWith('vibecheck_page:')) {
    const parsed = TextPaginator.parseButtonCustomId(customId);
    if (!parsed || parsed.stateId !== stateId) {
      return;
    }

    const newPage = parsed.page;
    const pageContent = TextPaginator.getPage(paginatedResult.pages, newPage);
    const fullContent = `${paginatedResult.header}\n${pageContent}`;

    const components: ActionRowBuilder<ButtonBuilder>[] = [];

    if (paginatedResult.pages.totalPages > 1) {
      const paginationRow = TextPaginator.buildPaginationButtons({
        currentPage: newPage,
        totalPages: paginatedResult.pages.totalPages,
        customIdPrefix: 'vibecheck_page',
        stateId,
      });
      components.push(paginationRow);
    }

    if (paginatedResult.actionButtons) {
      components.push(paginatedResult.actionButtons);
    }

    await buttonInteraction.update({
      content: fullContent,
      components,
    });
    return;
  }

  const [action, buttonScanId] = customId.split(':');

  if (buttonScanId !== scanId) {
    return;
  }

  if (action === 'vibecheck_dismiss') {
    await buttonInteraction.update({
      content: 'Results dismissed.',
      components: [],
    });
    collector.stop();
    return;
  }

  if (action === 'vibecheck_create') {
    await showAiGenerationPrompt(buttonInteraction, scanId, flaggedMessages, originalUserId);
  }
}

async function showAiGenerationPrompt(
  buttonInteraction: ButtonInteraction,
  scanId: string,
  flaggedMessages: FlaggedMessageResource[],
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

    const messageIds = flaggedMessages.map(msg => msg.id);

    void (async (): Promise<void> => {
      try {
        const result = await apiClient.createNoteRequestsFromScan(
          scanId,
          messageIds,
          generateAiNotes
        );
        const createdCount = result.data.attributes.created_count;

        const buttons: ButtonBuilder[] = [];
        if (createdCount > 0) {
          buttons.push(createListRequestsButton());
          if (generateAiNotes) {
            buttons.push(createListNotesButton());
          }
        }

        const components = buttons.length > 0
          ? [new ActionRowBuilder<ButtonBuilder>().addComponents(buttons)]
          : [];

        await aiButtonInteraction.update({
          content: `Created ${createdCount} note request${createdCount !== 1 ? 's' : ''}` +
            (generateAiNotes ? ' with AI-generated drafts.' : '.'),
          components,
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
        content: `⏰ **Selection Timed Out**\n\n` +
          `**Scan ID:** \`${scanId}\`\n\n` +
          `You can still create requests using:\n` +
          `\`/vibecheck create-requests ${scanId}\``,
        components: [],
      }).catch(() => {
        /* Silently ignore - interaction may have expired */
      });
    }
  });
}

async function handleStatusSubcommand(
  interaction: ChatInputCommandInteraction,
  guildId: string,
  errorId: string
): Promise<void> {
  await interaction.deferReply({
    flags: MessageFlags.Ephemeral,
  });

  logger.info('Checking vibecheck scan status', {
    error_id: errorId,
    command: 'vibecheck status',
    user_id: interaction.user.id,
    guild_id: guildId,
  });

  try {
    const communityServer = await apiClient.getCommunityServerByPlatformId(guildId);

    const latestScan = await apiClient.getLatestScan(communityServer.data.id);
    const flaggedMessages = latestScan.included || [];

    const cachedExplanations = await cache.get<Record<string, string>>(
      getExplanationsCacheKey(latestScan.data.id)
    );
    const explanations = cachedExplanations
      ? new Map(Object.entries(cachedExplanations))
      : undefined;

    const paginatedResult = formatScanStatusPaginated({
      scan: latestScan,
      guildId,
      includeButtons: false,
      explanations,
    });

    const stateId = nanoid(10);
    const currentPage = 1;

    const state: VibecheckPaginationState = {
      scanId: latestScan.data.id,
      guildId,
      days: 0,
      messagesScanned: latestScan.data.attributes.messages_scanned,
      flaggedMessages,
    };
    await cache.set(`vibecheck:pagination:${stateId}`, state, PAGINATION_STATE_TTL);

    const pageContent = TextPaginator.getPage(paginatedResult.pages, currentPage);
    const fullContent = `${paginatedResult.header}\n${pageContent}`;

    const components: ActionRowBuilder<ButtonBuilder>[] = [];

    if (paginatedResult.pages.totalPages > 1) {
      const paginationRow = TextPaginator.buildPaginationButtons({
        currentPage,
        totalPages: paginatedResult.pages.totalPages,
        customIdPrefix: 'vibecheck_page',
        stateId,
      });
      components.push(paginationRow);
    }

    await interaction.editReply({
      content: fullContent,
      components,
    });

    if (paginatedResult.pages.totalPages > 1) {
      const reply = await interaction.fetchReply();
      const originalUserId = interaction.user.id;
      const collector = reply.createMessageComponentCollector({
        componentType: ComponentType.Button,
        time: 300000,
        filter: (i) => i.user.id === originalUserId,
      });

      collector.on('collect', (buttonInteraction: ButtonInteraction) => {
        void handleStatusPaginationButton(
          buttonInteraction,
          stateId,
          paginatedResult
        );
      });

      collector.on('end', (_collected, reason) => {
        if (reason === 'time') {
          interaction.editReply({
            content: `Session expired.\n\n**Scan ID:** \`${latestScan.data.id}\``,
            components: [],
          }).catch(() => {
            /* Silently ignore - interaction may have expired */
          });
        }
      });
    }
  } catch (error) {
    if (error instanceof ApiError && error.statusCode === 404) {
      await interaction.editReply({
        content: 'No scans have been run for this server yet. Use `/vibecheck scan` to start one.',
      });
      return;
    }

    const errorDetails = extractErrorDetails(error);

    logger.error('Vibecheck status check failed', {
      error_id: errorId,
      command: 'vibecheck status',
      user_id: interaction.user.id,
      guild_id: guildId,
      error: errorDetails.message,
      error_type: errorDetails.type,
      stack: errorDetails.stack,
    });

    await interaction.editReply({
      content: formatErrorForUser(errorId, 'Failed to retrieve scan status. Please try again later.'),
    });
  }
}

async function handleStatusPaginationButton(
  buttonInteraction: ButtonInteraction,
  stateId: string,
  paginatedResult: ReturnType<typeof formatScanStatusPaginated>
): Promise<void> {
  const customId = buttonInteraction.customId;

  if (!customId.startsWith('vibecheck_page:')) {
    return;
  }

  const parsed = TextPaginator.parseButtonCustomId(customId);
  if (!parsed || parsed.stateId !== stateId) {
    return;
  }

  const newPage = parsed.page;
  const pageContent = TextPaginator.getPage(paginatedResult.pages, newPage);
  const fullContent = `${paginatedResult.header}\n${pageContent}`;

  const components: ActionRowBuilder<ButtonBuilder>[] = [];

  if (paginatedResult.pages.totalPages > 1) {
    const paginationRow = TextPaginator.buildPaginationButtons({
      currentPage: newPage,
      totalPages: paginatedResult.pages.totalPages,
      customIdPrefix: 'vibecheck_page',
      stateId,
    });
    components.push(paginationRow);
  }

  await buttonInteraction.update({
    content: fullContent,
    components,
  });
}

async function handleCreateRequestsSubcommand(
  interaction: ChatInputCommandInteraction,
  guildId: string,
  errorId: string
): Promise<void> {
  await interaction.deferReply({
    flags: MessageFlags.Ephemeral,
  });

  const scanId = interaction.options.getString('scan_id', true);

  logger.info('Creating note requests from scan', {
    error_id: errorId,
    command: 'vibecheck create-requests',
    user_id: interaction.user.id,
    guild_id: guildId,
    scan_id: scanId,
  });

  try {
    const scanResults = await apiClient.getBulkScanResults(scanId);
    const flaggedMessages = scanResults.included || [];

    if (flaggedMessages.length === 0) {
      await interaction.editReply({
        content: 'This scan has no flagged messages to create note requests from.',
      });
      return;
    }

    const messageIds = flaggedMessages.map(msg => msg.id);
    const result = await apiClient.createNoteRequestsFromScan(
      scanId,
      messageIds,
      false
    );

    const createdCount = result.data.attributes.created_count;

    const components = createdCount > 0
      ? [new ActionRowBuilder<ButtonBuilder>().addComponents(createListRequestsButton())]
      : [];

    await interaction.editReply({
      content: `Created ${createdCount} note request${createdCount !== 1 ? 's' : ''}.`,
      components,
    });
  } catch (error) {
    if (error instanceof ApiError && error.statusCode === 404) {
      await interaction.editReply({
        content: `Scan not found. Please check the scan ID and try again.\n\n**Scan ID provided:** \`${scanId}\``,
      });
      return;
    }

    const errorDetails = extractErrorDetails(error);

    logger.error('Failed to create note requests from scan', {
      error_id: errorId,
      command: 'vibecheck create-requests',
      user_id: interaction.user.id,
      guild_id: guildId,
      scan_id: scanId,
      error: errorDetails.message,
      error_type: errorDetails.type,
      stack: errorDetails.stack,
    });

    await interaction.editReply({
      content: formatErrorForUser(errorId, 'Failed to create note requests. Please try again later.'),
    });
  }
}
