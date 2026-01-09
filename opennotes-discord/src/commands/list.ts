import {
  SlashCommandBuilder,
  ChatInputCommandInteraction,
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
  MessageFlags,
  ModalSubmitInteraction,
  ModalBuilder,
  TextInputBuilder,
  TextInputStyle,
  ModalActionRowComponentBuilder,
  ButtonInteraction,
  GuildMember,
} from 'discord.js';
import { apiClient, type JSONAPIResource, type NoteAttributes } from '../api-client.js';
import { ConfigCache } from '../lib/config-cache.js';
import { logger } from '../logger.js';
import { getBotChannelOrRedirect } from '../lib/bot-channel-helper.js';
import { BotChannelService } from '../services/BotChannelService.js';
import { v2MessageFlags } from '../utils/v2-components.js';
import { LIST_COMMAND_LIMITS } from '../lib/constants.js';
import {
  classifyApiError,
  getQueueErrorMessage,
} from '../lib/error-handler.js';
import { serviceProvider } from '../services/index.js';
import { DiscordFormatter } from '../services/DiscordFormatter.js';
import type { RequestStatus } from '../lib/types.js';
import { generateErrorId, extractErrorDetails, formatErrorForUser, ApiError } from '../lib/errors.js';
import { parseCustomId, generateShortId } from '../lib/validation.js';
import { hasManageGuildPermission } from '../lib/permissions.js';
import {
  QueueRendererV2,
  QueueItemV2,
  QueueSummaryV2,
  PaginationConfig,
} from '../lib/queue-renderer.js';
import { V2_ICONS, calculateUrgency } from '../utils/v2-components.js';
import type { ScoreConfidence } from '../services/ScoringService.js';
import { suppressExpectedDiscordErrors, extractPlatformMessageId } from '../lib/discord-utils.js';
import { cache } from '../cache.js';

const configCache = new ConfigCache(apiClient);
const lastUsage = new Map<string, number>();

interface QueueState {
  userId: string;
  guildId: string | null;
  communityServerUuid: string | undefined;
  currentPage: number;
  thresholds: { min_ratings_needed: number; min_raters_per_note: number };
  isAdmin: boolean;
}

function createSummaryV2(
  currentPage: number,
  totalNotes: number,
  notesPerPage: number
): QueueSummaryV2 {
  const totalPages = Math.ceil(totalNotes / notesPerPage);
  const startIndex = (currentPage - 1) * notesPerPage;
  const endIndex = Math.min(startIndex + notesPerPage, totalNotes);

  if (totalNotes === 0) {
    return {
      title: `${V2_ICONS.HELPFUL} Rating Queue`,
      subtitle: 'No notes need rating right now!',
      stats: 'All caught up! Check back later.',
    };
  }

  return {
    title: `${V2_ICONS.PENDING} Rating Queue`,
    subtitle: `${totalNotes} notes need your rating`,
    stats: `Showing notes ${startIndex + 1}-${endIndex} of ${totalNotes} (Page ${currentPage}/${totalPages})`,
  };
}

function createNoteItemV2(
  note: JSONAPIResource<NoteAttributes>,
  thresholds: { min_ratings_needed: number; min_raters_per_note: number },
  userMember?: GuildMember | null
): QueueItemV2 {
  const urgency = calculateUrgency(note.attributes.ratings_count, thresholds.min_ratings_needed);

  const helpfulButton = new ButtonBuilder()
    .setCustomId(`rate:${note.id}:helpful`)
    .setLabel('Helpful')
    .setStyle(ButtonStyle.Success);

  const notHelpfulButton = new ButtonBuilder()
    .setCustomId(`rate:${note.id}:not_helpful`)
    .setLabel('Not Helpful')
    .setStyle(ButtonStyle.Danger);

  const buttons: ButtonBuilder[] = [helpfulButton, notHelpfulButton];

  const isAdmin = userMember && hasManageGuildPermission(userMember);
  if (isAdmin) {
    const forcePublishButton = new ButtonBuilder()
      .setCustomId(`force_publish:${note.id}`)
      .setLabel('Force Publish')
      .setStyle(ButtonStyle.Danger);
    buttons.push(forcePublishButton);
  }

  const ratingButtons = new ActionRowBuilder<ButtonBuilder>().addComponents(...buttons);

  const truncatedSummary = note.attributes.summary.length > 200
    ? note.attributes.summary.substring(0, 197) + '...'
    : note.attributes.summary;

  return {
    id: note.id,
    title: `Note #${note.id}`,
    summary: truncatedSummary,
    urgencyEmoji: urgency.urgencyEmoji,
    ratingButtons,
  };
}

export const data = new SlashCommandBuilder()
  .setName('list')
  .setDescription('View lists of notes and requests')
  .addSubcommand(subcommand =>
    subcommand
      .setName('notes')
      .setDescription('View all notes awaiting ratings')
  )
  .addSubcommand(subcommand =>
    subcommand
      .setName('requests')
      .setDescription('View a list of note requests')
      .addStringOption(option =>
        option
          .setName('status')
          .setDescription('Filter by request status')
          .setRequired(false)
          .addChoices(
            { name: 'Pending', value: 'PENDING' },
            { name: 'In Progress', value: 'IN_PROGRESS' },
            { name: 'Completed', value: 'COMPLETED' },
            { name: 'Failed', value: 'FAILED' }
          )
      )
      .addBooleanOption(option =>
        option
          .setName('my-requests-only')
          .setDescription('Only show requests you created')
          .setRequired(false)
      )
      .addIntegerOption(option =>
        option
          .setName('page')
          .setDescription('Page number (default: 1)')
          .setRequired(false)
          .setMinValue(1)
      )
      .addIntegerOption(option =>
        option
          .setName('page-size')
          .setDescription('Number of requests per page (default: 5, max: 100)')
          .setRequired(false)
          .setMinValue(1)
          .setMaxValue(100)
      )
  )
  .addSubcommand(subcommand =>
    subcommand
      .setName('top-notes')
      .setDescription('View the top-scored community notes')
      .addIntegerOption(option =>
        option
          .setName('limit')
          .setDescription('Number of notes to display (default: 10, max: 50)')
          .setMinValue(1)
          .setMaxValue(50)
          .setRequired(false)
      )
      .addStringOption(option =>
        option
          .setName('confidence')
          .setDescription('Filter by minimum confidence level')
          .addChoices(
            { name: 'Standard (5+ ratings)', value: 'standard' },
            { name: 'Provisional (<5 ratings)', value: 'provisional' },
            { name: 'No data (0 ratings)', value: 'no_data' }
          )
          .setRequired(false)
      )
      .addIntegerOption(option =>
        option
          .setName('tier')
          .setDescription('Filter by scoring tier (0-5)')
          .setMinValue(0)
          .setMaxValue(5)
          .setRequired(false)
      )
  );

export async function execute(interaction: ChatInputCommandInteraction): Promise<void> {
  const subcommand = interaction.options.getSubcommand();

  switch (subcommand) {
    case 'notes':
      return handleNotesSubcommand(interaction);
    case 'requests':
      return handleRequestsSubcommand(interaction);
    case 'top-notes':
      return handleTopNotesSubcommand(interaction);
    default:
      await interaction.reply({
        content: 'Unknown subcommand.',
        flags: MessageFlags.Ephemeral,
      });
  }
}

async function handleNotesSubcommand(interaction: ChatInputCommandInteraction): Promise<void> {
  const errorId = generateErrorId();
  const userId = interaction.user.id;
  const guildId = interaction.guildId;

  logger.info('Executing list notes subcommand', {
    error_id: errorId,
    command: 'list notes',
    user_id: userId,
    community_server_id: guildId,
  });

  const lastUse = lastUsage.get(userId);
  if (lastUse && Date.now() - lastUse < LIST_COMMAND_LIMITS.RATE_LIMIT_MS) {
    const resetTime = Math.floor((lastUse + LIST_COMMAND_LIMITS.RATE_LIMIT_MS) / 1000);
    await interaction.reply({
      content: `Please wait. You can use this command again <t:${resetTime}:R>`,
      flags: MessageFlags.Ephemeral,
    });
    return;
  }

  lastUsage.set(userId, Date.now());

  try {
    await interaction.deferReply({ flags: MessageFlags.Ephemeral });

    const botChannelService = new BotChannelService();
    const guildConfigService = serviceProvider.getGuildConfigService();
    const { shouldProceed } = await getBotChannelOrRedirect(
      interaction,
      botChannelService,
      guildConfigService
    );

    if (!shouldProceed) {
      return;
    }

    logger.info(`User ${userId} requested notes queue in bot channel`);

    let communityServerUuid: string | undefined;
    if (guildId) {
      try {
        const communityServer = await apiClient.getCommunityServerByPlatformId(guildId);
        communityServerUuid = communityServer.data.id;
      } catch (error) {
        logger.error('Failed to fetch community server UUID', {
          error_id: errorId,
          guild_id: guildId,
          error: error instanceof Error ? error.message : String(error),
        });
      }
    }

    const notesPerPage = LIST_COMMAND_LIMITS.NOTES_PER_PAGE;
    const [thresholds, notesResponse] = await Promise.all([
      configCache.getRatingThresholds(),
      apiClient.listNotesWithStatus('NEEDS_MORE_RATINGS', 1, notesPerPage, communityServerUuid, userId),
    ]);

    logger.debug('Fetched thresholds and notes', {
      thresholds,
      totalNotes: notesResponse.total,
    });

    const totalPages = Math.ceil(notesResponse.total / notesPerPage);
    const hasNotes = notesResponse.total > 0;

    const summaryV2 = createSummaryV2(1, notesResponse.total, notesPerPage);

    const member = interaction.guild?.members.cache.get(userId) || null;

    const itemsV2: QueueItemV2[] = notesResponse.data.map((note) =>
      createNoteItemV2(note, thresholds, member)
    );

    const queueStateId = generateShortId();
    await cache.set(`queue_state:${queueStateId}`, {
      userId,
      guildId,
      communityServerUuid,
      currentPage: 1,
      thresholds,
      isAdmin: member && hasManageGuildPermission(member),
    }, LIST_COMMAND_LIMITS.STATE_CACHE_TTL_SECONDS);

    const pagination: PaginationConfig | undefined =
      hasNotes && totalPages > 1
        ? {
            currentPage: 1,
            totalPages,
            previousButtonId: `queue:previous:${queueStateId}`,
            nextButtonId: `queue:next:${queueStateId}`,
          }
        : undefined;

    const containers = QueueRendererV2.buildContainers(summaryV2, itemsV2, pagination);

    if (containers.length === 0) {
      await interaction.editReply({
        content: 'No containers built for the notes queue.',
      });
      return;
    }

    await interaction.editReply({
      components: [containers[0]],
      flags: v2MessageFlags(),
    });

    logger.info('Notes queue rendered as ephemeral message', {
      error_id: errorId,
      user_id: userId,
      total_notes: notesResponse.total,
      page: 1,
      queue_state_id: queueStateId,
    });
  } catch (error) {
    const errorType = classifyApiError(error);
    const errorDetails = extractErrorDetails(error);

    logger.error('Error in list notes subcommand', {
      error_id: errorId,
      command: 'list notes',
      user_id: userId,
      community_server_id: guildId,
      error_type: errorType,
      error: errorDetails.message,
      stack: errorDetails.stack,
    });

    const userMessage = `${getQueueErrorMessage(errorType)}\n\nError ID: \`${errorId}\``;

    if (interaction.deferred) {
      await interaction.editReply({
        content: userMessage,
      });
    } else {
      await interaction.reply({
        content: userMessage,
        flags: MessageFlags.Ephemeral,
      });
    }
  }
}

async function handleRequestsSubcommand(interaction: ChatInputCommandInteraction): Promise<void> {
  const errorId = generateErrorId();
  const status = interaction.options.getString('status') as RequestStatus | null;
  const myRequestsOnly = interaction.options.getBoolean('my-requests-only') || false;
  const page = interaction.options.getInteger('page') || 1;
  const size = interaction.options.getInteger('page-size') || LIST_COMMAND_LIMITS.REQUESTS_PER_PAGE;
  const userId = interaction.user.id;
  const guildId = interaction.guildId;

  try {
    logger.info('Executing list requests subcommand', {
      error_id: errorId,
      command: 'list requests',
      user_id: userId,
      community_server_id: guildId,
      page,
      size,
      status,
      my_requests_only: myRequestsOnly,
    });

    await interaction.deferReply({ flags: MessageFlags.Ephemeral });

    const botChannelService = new BotChannelService();
    const guildConfigService = serviceProvider.getGuildConfigService();
    const { shouldProceed } = await getBotChannelOrRedirect(
      interaction,
      botChannelService,
      guildConfigService
    );

    if (!shouldProceed) {
      return;
    }

    let communityServerUuid: string | undefined;
    if (guildId) {
      try {
        const communityServer = await apiClient.getCommunityServerByPlatformId(guildId);
        communityServerUuid = communityServer.data.id;
      } catch (error) {
        logger.error('Failed to fetch community server UUID', {
          error_id: errorId,
          guild_id: guildId,
          error: error instanceof Error ? error.message : String(error),
        });
      }
    }

    const listRequestsService = serviceProvider.getListRequestsService();
    const result = await listRequestsService.execute({
      userId,
      page,
      size,
      status: status || undefined,
      myRequestsOnly,
      communityServerId: communityServerUuid,
    });

    if (!result.success) {
      const errorResponse = DiscordFormatter.formatErrorV2(result);
      await interaction.editReply({
        components: errorResponse.components,
        flags: errorResponse.flags,
      });
      return;
    }

    if (!result.data) {
      await interaction.editReply({
        content: 'No data returned from the service.',
      });
      return;
    }

    const formattedData = await DiscordFormatter.formatListRequestsSuccessV2(result.data, {
      status: status || undefined,
      myRequestsOnly,
      communityServerId: communityServerUuid,
    });

    await interaction.editReply({
      components: [formattedData.container.toJSON()],
      flags: formattedData.flags,
    });

    logger.info('List requests rendered as ephemeral message', {
      error_id: errorId,
      command: 'list requests',
      user_id: userId,
      result_count: result.data.requests.length,
      total: result.data.total,
    });
  } catch (error) {
    const errorDetails = extractErrorDetails(error);

    logger.error('Unexpected error in list requests subcommand', {
      error_id: errorId,
      command: 'list requests',
      user_id: userId,
      community_server_id: guildId,
      page,
      size,
      status,
      my_requests_only: myRequestsOnly,
      error: errorDetails.message,
      error_type: errorDetails.type,
      stack: errorDetails.stack,
      ...(error instanceof ApiError && {
        endpoint: error.endpoint,
        status_code: error.statusCode,
        response_body: error.responseBody,
      }),
    });

    await interaction.editReply({
      content: formatErrorForUser(errorId, 'Failed to retrieve request list.'),
    });
  }
}

async function handleTopNotesSubcommand(interaction: ChatInputCommandInteraction): Promise<void> {
  const errorId = generateErrorId();
  const limit = interaction.options.getInteger('limit') || 10;
  const confidence = interaction.options.getString('confidence') as ScoreConfidence | null;
  const tier = interaction.options.getInteger('tier');
  const userId = interaction.user.id;
  const guildId = interaction.guildId;

  try {
    logger.info('Executing list top-notes subcommand', {
      error_id: errorId,
      command: 'list top-notes',
      user_id: userId,
      community_server_id: guildId,
      limit,
      confidence,
      tier,
    });

    await interaction.deferReply({ flags: MessageFlags.Ephemeral });

    const botChannelService = new BotChannelService();
    const guildConfigService = serviceProvider.getGuildConfigService();
    const { shouldProceed } = await getBotChannelOrRedirect(
      interaction,
      botChannelService,
      guildConfigService
    );

    if (!shouldProceed) {
      return;
    }

    const scoringService = serviceProvider.getScoringService();
    const result = await scoringService.getTopNotes({
      limit,
      minConfidence: confidence || undefined,
      tier: tier || undefined,
    });

    if (!result.success) {
      let errorMessage: string;

      switch (result.error?.code) {
        case 'SERVICE_UNAVAILABLE':
          errorMessage = 'The scoring system is temporarily unavailable. Please try again later.';
          break;
        default:
          errorMessage = 'Failed to retrieve top notes. Please try again later.';
      }

      await interaction.editReply({
        content: errorMessage,
      });
      return;
    }

    if (result.data!.data.length === 0) {
      await interaction.editReply({
        content: 'No notes found matching the specified criteria.',
      });
      return;
    }

    const member = interaction.guild?.members.cache.get(userId) || null;
    const hasAdminButtons = member && hasManageGuildPermission(member);

    const formattedData = DiscordFormatter.formatTopNotesForQueueV2(result.data!, 1, limit, {
      includeForcePublishButtons: hasAdminButtons ?? false,
    });

    await interaction.editReply({
      components: [formattedData.container.toJSON()],
      flags: formattedData.flags,
    });

    logger.info('Top notes rendered as ephemeral message', {
      error_id: errorId,
      command: 'list top-notes',
      user_id: userId,
      note_count: result.data!.data.length,
      total_count: result.data!.meta?.total_count ?? result.data!.data.length,
    });
  } catch (error) {
    const errorDetails = extractErrorDetails(error);

    logger.error('Unexpected error in list top-notes subcommand', {
      error_id: errorId,
      command: 'list top-notes',
      user_id: userId,
      community_server_id: guildId,
      limit,
      confidence,
      tier,
      error: errorDetails.message,
      error_type: errorDetails.type,
      stack: errorDetails.stack,
    });

    await interaction.editReply({
      content: formatErrorForUser(errorId, 'Failed to retrieve top notes.'),
    }).catch(suppressExpectedDiscordErrors('edit_reply_top_notes_error'));
  }
}

export async function handleModalSubmit(interaction: ModalSubmitInteraction): Promise<void> {
  const errorId = generateErrorId();

  try {
    const parseResult = parseCustomId(interaction.customId, 2);
    if (!parseResult.success || !parseResult.parts) {
      logger.error('Failed to parse write_note_modal customId', {
        error_id: errorId,
        customId: interaction.customId,
        error: parseResult.error,
      });
      await interaction.reply({
        content: 'Invalid modal data. Please try again.',
        flags: MessageFlags.Ephemeral,
      });
      return;
    }

    const modalShortId = parseResult.parts[1];
    const modalCacheKey = `write_note_modal_state:${modalShortId}`;

    const requestId = await cache.get<string>(modalCacheKey);

    if (!requestId) {
      logger.error('Write note modal state not found in cache', {
        error_id: errorId,
        modalShortId,
        modalCacheKey,
      });
      await interaction.reply({
        content: 'Modal state expired. Please run the /list requests command again.',
        flags: MessageFlags.Ephemeral,
      });
      return;
    }

    logger.debug('Retrieved write note modal state from cache', { modalShortId, modalCacheKey, requestId });
    const summary = interaction.fields.getTextInputValue('summary');

    const classificationCacheKey = `write_note_classification:${modalShortId}`;
    const classificationInput = await cache.get<string>(classificationCacheKey);

    if (!classificationInput) {
      logger.error('Classification not found in cache', {
        error_id: errorId,
        modalShortId,
        classificationCacheKey,
      });
      await interaction.reply({
        content: 'Classification data expired. Please try again.',
        flags: MessageFlags.Ephemeral,
      });
      return;
    }

    await interaction.deferReply({ flags: MessageFlags.Ephemeral });

    const requestResponse = await apiClient.getRequest(requestId);

    const messageId = extractPlatformMessageId(
      requestResponse.data.attributes.platform_message_id ?? undefined,
      requestResponse.data.attributes.request_id
    );
    if (!messageId) {
      await interaction.editReply({
        content: 'This request does not have a platform message ID and cannot be used to create a note.',
      });
      return;
    }

    const writeNoteService = serviceProvider.getWriteNoteService();
    const result = await writeNoteService.execute({
      messageId,
      authorId: interaction.user.id,
      content: summary,
      classification: classificationInput as 'NOT_MISLEADING' | 'MISINFORMED_OR_POTENTIALLY_MISLEADING',
      requestId,
      guildId: interaction.guildId || undefined,
      channelId: interaction.channelId || undefined,
      username: interaction.user.username,
      displayName: interaction.user.displayName || interaction.user.username,
    });

    if (!result.success) {
      const errorResponse = DiscordFormatter.formatErrorV2(result);
      await interaction.editReply({
        components: errorResponse.components,
        flags: errorResponse.flags,
      });
      return;
    }

    const response = DiscordFormatter.formatWriteNoteSuccessV2(
      result.data!,
      messageId,
      interaction.guildId || undefined,
      interaction.channelId || undefined
    );
    await interaction.editReply({
      components: response.components,
      flags: response.flags,
    });

    logger.info('Note created from request queue', {
      error_id: errorId,
      request_id: requestId,
      user_id: interaction.user.id,
      note_id: result.data?.note.data.id,
    });
  } catch (error) {
    const errorDetails = extractErrorDetails(error);

    logger.error('Error handling write note modal submission', {
      error_id: errorId,
      user_id: interaction.user.id,
      error: errorDetails.message,
      error_type: errorDetails.type,
      stack: errorDetails.stack,
    });

    if (interaction.deferred) {
      await interaction.editReply({
        content: formatErrorForUser(errorId, 'Failed to create note.'),
      });
    } else {
      await interaction.reply({
        content: formatErrorForUser(errorId, 'Failed to create note.'),
        flags: MessageFlags.Ephemeral,
      });
    }
  }
}

export async function handleWriteNoteButton(interaction: ButtonInteraction): Promise<void> {
  const errorId = generateErrorId();

  try {
    const parts = interaction.customId.split(':');
    if (parts.length !== 3) {
      logger.error('Invalid write_note customId format', {
        error_id: errorId,
        customId: interaction.customId,
      });
      await interaction.reply({
        content: 'Invalid button data. Please try again.',
        flags: MessageFlags.Ephemeral,
      });
      return;
    }

    const classification = parts[1] as 'NOT_MISLEADING' | 'MISINFORMED_OR_POTENTIALLY_MISLEADING';
    const shortId = parts[2];
    const cacheKey = `write_note_state:${shortId}`;

    const requestId = await cache.get<string>(cacheKey);

    if (!requestId) {
      logger.error('Write note state not found in cache', {
        error_id: errorId,
        shortId,
        cacheKey,
      });
      await interaction.reply({
        content: 'Button expired. Please run the /list requests command again.',
        flags: MessageFlags.Ephemeral,
      });
      return;
    }

    const modalShortId = generateShortId();
    const modalCacheKey = `write_note_modal_state:${modalShortId}`;
    const classificationCacheKey = `write_note_classification:${modalShortId}`;
    const ttl = 300;

    await cache.set(modalCacheKey, requestId, ttl);
    await cache.set(classificationCacheKey, classification, ttl);

    const modal = new ModalBuilder()
      .setCustomId(`write_note_modal:${modalShortId}`)
      .setTitle(classification === 'NOT_MISLEADING' ? 'Write Note - Not Misleading' : 'Write Note - Misinformed');

    const noteInput = new TextInputBuilder()
      .setCustomId('summary')
      .setLabel('Note Content')
      .setStyle(TextInputStyle.Paragraph)
      .setPlaceholder('Write your community note explaining this content...')
      .setRequired(true)
      .setMinLength(10)
      .setMaxLength(1000);

    const actionRow = new ActionRowBuilder<ModalActionRowComponentBuilder>().addComponents(noteInput);
    modal.addComponents(actionRow);

    await interaction.showModal(modal);

    logger.info('Write note modal shown', {
      error_id: errorId,
      user_id: interaction.user.id,
      request_id: requestId,
      classification,
    });
  } catch (error) {
    const errorDetails = extractErrorDetails(error);

    logger.error('Error handling write note button', {
      error_id: errorId,
      user_id: interaction.user.id,
      error: errorDetails.message,
      error_type: errorDetails.type,
      stack: errorDetails.stack,
    });

    if (!interaction.replied && !interaction.deferred) {
      await interaction.reply({
        content: formatErrorForUser(errorId, 'Failed to open note editor.'),
        flags: MessageFlags.Ephemeral,
      });
    }
  }
}

export async function handleAiWriteNoteButton(interaction: ButtonInteraction): Promise<void> {
  const errorId = generateErrorId();

  try {
    const parts = interaction.customId.split(':');
    if (parts.length !== 2) {
      logger.error('Invalid ai_write_note customId format', {
        error_id: errorId,
        customId: interaction.customId,
      });
      await interaction.reply({
        content: 'Invalid button data. Please try again.',
        flags: MessageFlags.Ephemeral,
      });
      return;
    }

    const shortId = parts[1];
    const cacheKey = `write_note_state:${shortId}`;

    const requestId = await cache.get<string>(cacheKey);

    if (!requestId) {
      logger.error('AI write note state not found in cache', {
        error_id: errorId,
        shortId,
        cacheKey,
      });
      await interaction.reply({
        content: 'Button expired. Please run the /list requests command again.',
        flags: MessageFlags.Ephemeral,
      });
      return;
    }

    await interaction.deferReply({ flags: MessageFlags.Ephemeral });

    logger.info('Generating AI note', {
      error_id: errorId,
      user_id: interaction.user.id,
      request_id: requestId,
    });

    const userContext = {
      userId: interaction.user.id,
      username: interaction.user.username,
      displayName: interaction.user.displayName || interaction.user.username,
      avatarUrl: interaction.user.avatarURL() || undefined,
      guildId: interaction.guildId || undefined,
    };

    const result = await apiClient.generateAiNote(requestId, userContext);

    const noteId = result.data.id;
    const noteContent = result.data.attributes.summary || 'AI-generated note created.';

    await interaction.editReply({
      content: `✅ **AI Note Generated**\n\nNote ID: \`${noteId}\`\n\n> ${noteContent.slice(0, 200)}${noteContent.length > 200 ? '...' : ''}\n\nThe note has been created and will enter the rating queue.`,
    });

    logger.info('AI note generated successfully', {
      error_id: errorId,
      user_id: interaction.user.id,
      request_id: requestId,
      note_id: noteId,
    });
  } catch (error) {
    const errorDetails = extractErrorDetails(error);

    logger.error('Error generating AI note', {
      error_id: errorId,
      user_id: interaction.user.id,
      error: errorDetails.message,
      error_type: errorDetails.type,
      stack: errorDetails.stack,
    });

    if (interaction.deferred) {
      await interaction.editReply({
        content: formatErrorForUser(errorId, 'Failed to generate AI note. Please try again.'),
      });
    } else if (!interaction.replied) {
      await interaction.reply({
        content: formatErrorForUser(errorId, 'Failed to generate AI note.'),
        flags: MessageFlags.Ephemeral,
      });
    }
  }
}

export async function handleRateNoteButton(interaction: ButtonInteraction): Promise<void> {
  const errorId = generateErrorId();

  try {
    const parts = interaction.customId.split(':');
    if (parts.length !== 3) {
      logger.error('Invalid rate customId format', {
        error_id: errorId,
        customId: interaction.customId,
      });
      await interaction.reply({
        content: 'Invalid button data. Please try again.',
        flags: MessageFlags.Ephemeral,
      });
      return;
    }

    const noteId = parts[1];
    const ratingType = parts[2];
    const isHelpful = ratingType === 'helpful';

    await interaction.deferReply({ flags: MessageFlags.Ephemeral });

    logger.info('Rating note', {
      error_id: errorId,
      user_id: interaction.user.id,
      note_id: noteId,
      helpful: isHelpful,
    });

    const userContext = {
      userId: interaction.user.id,
      username: interaction.user.username,
      displayName: interaction.user.displayName || interaction.user.username,
      avatarUrl: interaction.user.avatarURL() || undefined,
      guildId: interaction.guildId || undefined,
    };

    await apiClient.rateNote({
      noteId,
      userId: interaction.user.id,
      helpful: isHelpful,
    }, userContext);

    await interaction.editReply({
      content: `✅ **Rating Submitted**\n\nYou rated this note as **${isHelpful ? 'Helpful' : 'Not Helpful'}**.\n\nThank you for your feedback!`,
    });

    logger.info('Note rated successfully', {
      error_id: errorId,
      user_id: interaction.user.id,
      note_id: noteId,
      helpful: isHelpful,
    });
  } catch (error) {
    const errorDetails = extractErrorDetails(error);

    logger.error('Error rating note', {
      error_id: errorId,
      user_id: interaction.user.id,
      error: errorDetails.message,
      error_type: errorDetails.type,
      stack: errorDetails.stack,
    });

    if (interaction.deferred) {
      await interaction.editReply({
        content: formatErrorForUser(errorId, 'Failed to submit rating. Please try again.'),
      });
    } else if (!interaction.replied) {
      await interaction.reply({
        content: formatErrorForUser(errorId, 'Failed to submit rating.'),
        flags: MessageFlags.Ephemeral,
      });
    }
  }
}

export async function handleRequestReplyButton(interaction: ButtonInteraction): Promise<void> {
  const errorId = generateErrorId();
  const userId = interaction.user.id;
  const guildId = interaction.guildId;
  const customId = interaction.customId;

  try {
    logger.info('Handling request reply button', {
      error_id: errorId,
      custom_id: customId,
      user_id: userId,
      community_server_id: guildId,
    });

    await interaction.deferReply({ flags: MessageFlags.Ephemeral });

    if (!guildId) {
      await interaction.editReply({
        content: 'This button can only be used in a server.',
      });
      return;
    }

    let communityServerUuid: string | undefined;
    try {
      const communityServer = await apiClient.getCommunityServerByPlatformId(guildId);
      communityServerUuid = communityServer.data.id;
    } catch (error) {
      logger.error('Failed to fetch community server UUID', {
        error_id: errorId,
        guild_id: guildId,
        error: error instanceof Error ? error.message : String(error),
      });
    }

    if (customId === 'request_reply:list_requests') {
      const listRequestsService = serviceProvider.getListRequestsService();
      const result = await listRequestsService.execute({
        userId,
        page: 1,
        size: LIST_COMMAND_LIMITS.REQUESTS_PER_PAGE,
        status: undefined,
        myRequestsOnly: false,
        communityServerId: communityServerUuid,
      });

      if (!result.success) {
        const errorResponse = DiscordFormatter.formatErrorV2(result);
        await interaction.editReply({
          components: errorResponse.components,
          flags: errorResponse.flags,
        });
        return;
      }

      if (!result.data) {
        await interaction.editReply({
          content: 'No data returned from the service.',
        });
        return;
      }

      const formattedData = await DiscordFormatter.formatListRequestsSuccessV2(result.data, {
        status: undefined,
        myRequestsOnly: false,
        communityServerId: communityServerUuid,
      });

      await interaction.editReply({
        components: [formattedData.container.toJSON()],
        flags: formattedData.flags,
      });

      logger.info('List requests from button rendered as ephemeral', {
        error_id: errorId,
        user_id: userId,
        result_count: result.data.requests.length,
        total: result.data.total,
      });
    } else if (customId === 'request_reply:list_notes') {
      const notesPerPage = LIST_COMMAND_LIMITS.NOTES_PER_PAGE;
      const [thresholds, notesResponse] = await Promise.all([
        configCache.getRatingThresholds(),
        apiClient.listNotesWithStatus('NEEDS_MORE_RATINGS', 1, notesPerPage, communityServerUuid, userId),
      ]);

      const totalPages = Math.ceil(notesResponse.total / notesPerPage);
      const hasNotes = notesResponse.total > 0;

      const summaryV2 = createSummaryV2(1, notesResponse.total, notesPerPage);

      const member = interaction.guild?.members.cache.get(userId) || null;

      const itemsV2: QueueItemV2[] = notesResponse.data.map((note) =>
        createNoteItemV2(note, thresholds, member)
      );

      const queueStateId = generateShortId();
      await cache.set(`queue_state:${queueStateId}`, {
        userId,
        guildId,
        communityServerUuid,
        currentPage: 1,
        thresholds,
        isAdmin: member && hasManageGuildPermission(member),
      }, LIST_COMMAND_LIMITS.STATE_CACHE_TTL_SECONDS);

      const pagination: PaginationConfig | undefined =
        hasNotes && totalPages > 1
          ? {
              currentPage: 1,
              totalPages,
              previousButtonId: `queue:previous:${queueStateId}`,
              nextButtonId: `queue:next:${queueStateId}`,
            }
          : undefined;

      const containers = QueueRendererV2.buildContainers(summaryV2, itemsV2, pagination);

      if (containers.length === 0) {
        await interaction.editReply({
          content: 'No containers built for the notes queue.',
        });
        return;
      }

      await interaction.editReply({
        components: [containers[0]],
        flags: v2MessageFlags(),
      });

      logger.info('List notes from button rendered as ephemeral', {
        error_id: errorId,
        user_id: userId,
        total_notes: notesResponse.total,
        queue_state_id: queueStateId,
      });
    } else {
      await interaction.editReply({
        content: 'Unknown button action.',
      });
    }
  } catch (error) {
    const errorDetails = extractErrorDetails(error);

    logger.error('Error handling request reply button', {
      error_id: errorId,
      custom_id: customId,
      user_id: userId,
      community_server_id: guildId,
      error: errorDetails.message,
      error_type: errorDetails.type,
      stack: errorDetails.stack,
    });

    if (interaction.deferred) {
      await interaction.editReply({
        content: formatErrorForUser(errorId, 'Failed to process button click.'),
      });
    } else {
      await interaction.reply({
        content: formatErrorForUser(errorId, 'Failed to process button click.'),
        flags: MessageFlags.Ephemeral,
      });
    }
  }
}

export async function handlePaginationButton(interaction: ButtonInteraction): Promise<void> {
  const errorId = generateErrorId();
  const customId = interaction.customId;

  try {
    const parseResult = parseCustomId(customId, 3);
    if (!parseResult.success || !parseResult.parts) {
      logger.error('Failed to parse pagination button customId', {
        error_id: errorId,
        customId,
        error: parseResult.error,
      });
      await interaction.reply({
        content: 'Invalid button data. Please run `/list notes` again.',
        flags: MessageFlags.Ephemeral,
      });
      return;
    }

    const [, direction, stateId] = parseResult.parts;
    const cacheKey = `queue_state:${stateId}`;
    const state = await cache.get<QueueState>(cacheKey);

    if (!state) {
      logger.debug('Queue state not found - may have expired', {
        error_id: errorId,
        stateId,
        user_id: interaction.user.id,
      });
      await interaction.update({
        content: 'Queue session has expired. Please run `/list notes` again.',
        components: [],
      });
      return;
    }

    if (interaction.user.id !== state.userId) {
      await interaction.reply({
        content: 'This queue belongs to another user. Please run `/list notes` to view your own queue.',
        flags: MessageFlags.Ephemeral,
      });
      return;
    }

    const notesPerPage = LIST_COMMAND_LIMITS.NOTES_PER_PAGE;
    const notesResponse = await apiClient.listNotesWithStatus(
      'NEEDS_MORE_RATINGS',
      1,
      1,
      state.communityServerUuid,
      state.userId
    );
    const totalNotes = notesResponse.total;
    const totalPages = Math.ceil(totalNotes / notesPerPage);

    let newPage = state.currentPage;
    if (direction === 'previous') {
      newPage = Math.max(1, state.currentPage - 1);
    } else if (direction === 'next') {
      newPage = Math.min(totalPages, state.currentPage + 1);
    }

    if (newPage === state.currentPage) {
      await interaction.deferUpdate();
      return;
    }

    const newNotesResponse = await apiClient.listNotesWithStatus(
      'NEEDS_MORE_RATINGS',
      newPage,
      notesPerPage,
      state.communityServerUuid,
      state.userId
    );

    const updatedState: QueueState = {
      ...state,
      currentPage: newPage,
    };
    await cache.set(cacheKey, updatedState, LIST_COMMAND_LIMITS.STATE_CACHE_TTL_SECONDS);

    const summaryV2 = createSummaryV2(newPage, totalNotes, notesPerPage);
    const member = interaction.guild?.members.cache.get(state.userId) || null;

    const itemsV2: QueueItemV2[] = newNotesResponse.data.map((note) =>
      createNoteItemV2(note, state.thresholds, member)
    );

    const pagination: PaginationConfig = {
      currentPage: newPage,
      totalPages,
      previousButtonId: `queue:previous:${stateId}`,
      nextButtonId: `queue:next:${stateId}`,
    };

    const containers = QueueRendererV2.buildContainers(summaryV2, itemsV2, pagination);

    if (containers.length === 0) {
      await interaction.update({
        content: 'No notes available.',
        components: [],
      });
      return;
    }

    await interaction.update({
      components: [containers[0]],
      flags: v2MessageFlags(),
    });

    logger.info('Pagination button handled successfully', {
      error_id: errorId,
      user_id: interaction.user.id,
      direction,
      old_page: state.currentPage,
      new_page: newPage,
      total_pages: totalPages,
      stateId,
    });
  } catch (error) {
    const errorType = classifyApiError(error);
    const errorDetails = extractErrorDetails(error);

    logger.error('Error handling pagination button', {
      error_id: errorId,
      customId,
      user_id: interaction.user.id,
      error_type: errorType,
      error: errorDetails.message,
      stack: errorDetails.stack,
    });

    const userMessage = `${getQueueErrorMessage(errorType)}\n\nError ID: \`${errorId}\``;

    try {
      if (interaction.deferred || interaction.replied) {
        await interaction.followUp({
          content: userMessage,
          flags: MessageFlags.Ephemeral,
        });
      } else {
        await interaction.reply({
          content: userMessage,
          flags: MessageFlags.Ephemeral,
        });
      }
    } catch {
      logger.debug('Failed to send error response for pagination button', {
        error_id: errorId,
      });
    }
  }
}

interface RequestQueueFilterState {
  status?: RequestStatus;
  myRequestsOnly?: boolean;
  communityServerId?: string;
}

export async function handleForcePublishButton(interaction: ButtonInteraction): Promise<void> {
  const errorId = generateErrorId();

  try {
    const parts = interaction.customId.split(':');
    if (parts.length !== 2) {
      logger.error('Invalid force_publish customId format', {
        error_id: errorId,
        customId: interaction.customId,
      });
      await interaction.reply({
        content: 'Invalid button data. Please try again.',
        flags: MessageFlags.Ephemeral,
      });
      return;
    }

    const noteId = parts[1];

    await interaction.deferReply({ flags: MessageFlags.Ephemeral });

    logger.info('Force publishing note', {
      error_id: errorId,
      user_id: interaction.user.id,
      note_id: noteId,
    });

    const userContext = {
      userId: interaction.user.id,
      username: interaction.user.username,
      displayName: interaction.user.displayName || interaction.user.username,
      avatarUrl: interaction.user.avatarURL() || undefined,
      guildId: interaction.guildId || undefined,
    };

    await apiClient.forcePublishNote(noteId, userContext);

    await interaction.editReply({
      content: `✅ **Note Force Published**\n\nNote \`${noteId}\` has been force published successfully.`,
    });

    logger.info('Note force published successfully', {
      error_id: errorId,
      user_id: interaction.user.id,
      note_id: noteId,
    });
  } catch (error) {
    const errorDetails = extractErrorDetails(error);

    logger.error('Failed to force publish note', {
      error_id: errorId,
      customId: interaction.customId,
      user_id: interaction.user.id,
      error: errorDetails.message,
      stack: errorDetails.stack,
    });

    const userMessage = formatErrorForUser(
      'Failed to force publish note. Please try again later.',
      errorId
    );

    try {
      if (interaction.deferred || interaction.replied) {
        await interaction.editReply({ content: userMessage });
      } else {
        await interaction.reply({
          content: userMessage,
          flags: MessageFlags.Ephemeral,
        });
      }
    } catch {
      logger.debug('Failed to send error response for force publish button', {
        error_id: errorId,
      });
    }
  }
}

export async function handleRequestQueuePageButton(interaction: ButtonInteraction): Promise<void> {
  const errorId = generateErrorId();
  const customId = interaction.customId;

  try {
    const parts = customId.split(':');
    if (parts.length !== 3) {
      logger.error('Invalid request_queue_page customId format', {
        error_id: errorId,
        customId,
      });
      await interaction.reply({
        content: 'Invalid button data. Please run `/list requests` again.',
        flags: MessageFlags.Ephemeral,
      });
      return;
    }

    const page = parseInt(parts[1], 10);
    const stateId = parts[2];

    if (isNaN(page) || page < 1) {
      logger.error('Invalid page number in request_queue_page customId', {
        error_id: errorId,
        customId,
        page: parts[1],
      });
      await interaction.reply({
        content: 'Invalid page number. Please run `/list requests` again.',
        flags: MessageFlags.Ephemeral,
      });
      return;
    }

    const cacheKey = `pagination:${stateId}`;
    const filterState = await cache.get<RequestQueueFilterState>(cacheKey);

    if (!filterState) {
      logger.debug('Request queue pagination state not found - may have expired', {
        error_id: errorId,
        stateId,
        user_id: interaction.user.id,
      });
      await interaction.update({
        content: 'Session expired. Please run `/list requests` again.',
        components: [],
      });
      return;
    }

    await interaction.deferUpdate();

    const listRequestsService = serviceProvider.getListRequestsService();
    const result = await listRequestsService.execute({
      userId: interaction.user.id,
      page,
      size: LIST_COMMAND_LIMITS.REQUESTS_PER_PAGE,
      status: filterState.status,
      myRequestsOnly: filterState.myRequestsOnly,
      communityServerId: filterState.communityServerId,
    });

    if (!result.success || !result.data) {
      const errorResponse = DiscordFormatter.formatErrorV2(result);
      await interaction.editReply({
        components: errorResponse.components,
        flags: errorResponse.flags,
      });
      return;
    }

    const formatted = await DiscordFormatter.formatListRequestsSuccessV2(result.data, {
      status: filterState.status,
      myRequestsOnly: filterState.myRequestsOnly,
      communityServerId: filterState.communityServerId,
    });

    await interaction.editReply({
      components: formatted.components,
      flags: formatted.flags,
    });

    logger.info('Request queue page button handled successfully', {
      error_id: errorId,
      user_id: interaction.user.id,
      page,
      stateId,
    });
  } catch (error) {
    const errorType = classifyApiError(error);
    const errorDetails = extractErrorDetails(error);

    logger.error('Error handling request queue page button', {
      error_id: errorId,
      customId,
      user_id: interaction.user.id,
      error_type: errorType,
      error: errorDetails.message,
      stack: errorDetails.stack,
    });

    const userMessage = `${getQueueErrorMessage(errorType)}\n\nError ID: \`${errorId}\``;

    try {
      if (interaction.deferred || interaction.replied) {
        await interaction.followUp({
          content: userMessage,
          flags: MessageFlags.Ephemeral,
        });
      } else {
        await interaction.reply({
          content: userMessage,
          flags: MessageFlags.Ephemeral,
        });
      }
    } catch {
      logger.debug('Failed to send error response for request queue page button', {
        error_id: errorId,
      });
    }
  }
}
