import {
  SlashCommandBuilder,
  ChatInputCommandInteraction,
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
  ComponentType,
  TextChannel,
  ThreadChannel,
  MessageFlags,
  ModalSubmitInteraction,
  TextInputBuilder,
  ButtonInteraction,
  GuildMember,
} from 'discord.js';
import { apiClient } from '../api-client.js';
import { configCache, getPrivateThreadManager as getQueueManager } from '../private-thread.js';
import { logger } from '../logger.js';
import {
  classifyApiError,
  getQueueErrorMessage,
  getPaginationErrorMessage,
} from '../lib/error-handler.js';
import { serviceProvider } from '../services/index.js';
import { DiscordFormatter } from '../services/DiscordFormatter.js';
import type { NoteWithRatings, RequestStatus } from '../lib/types.js';
import { generateErrorId, extractErrorDetails, formatErrorForUser, ApiError } from '../lib/errors.js';
import { parseCustomId, generateShortId } from '../lib/validation.js';
import { buttonInteractionRateLimiter } from '../lib/interaction-rate-limiter.js';
import { TIMEOUTS } from '../lib/constants.js';
import { hasManageGuildPermission } from '../lib/permissions.js';
import {
  QueueRenderer,
  QueueRendererV2,
  QueueItemV2,
  QueueSummaryV2,
  PaginationConfig,
} from '../lib/queue-renderer.js';
import { V2_ICONS, calculateUrgency } from '../utils/v2-components.js';
import type { ScoreConfidence } from '../services/ScoringService.js';
import { suppressExpectedDiscordErrors, extractPlatformMessageId, createForcePublishConfirmationButtons, createDisabledForcePublishButtons } from '../lib/discord-utils.js';
import { cache } from '../cache.js';

const RATE_LIMIT_MS = 60 * 1000;
const lastUsage = new Map<string, number>();
const RATED_NOTES_PER_PAGE = 5;

function createRatedNotesPagination(
  currentPage: number,
  totalPages: number,
  stateId: string
): PaginationConfig {
  return {
    currentPage,
    totalPages,
    previousButtonId: `rn_prev:${stateId}`,
    nextButtonId: `rn_next:${stateId}`,
    previousLabel: 'Previous',
    nextLabel: 'Next',
  };
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
  note: NoteWithRatings,
  thresholds: { min_ratings_needed: number; min_raters_per_note: number },
  userMember?: GuildMember | null
): QueueItemV2 {
  const urgency = calculateUrgency(note.ratings_count, thresholds.min_ratings_needed);

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

  const truncatedSummary = note.summary.length > 200
    ? note.summary.substring(0, 197) + '...'
    : note.summary;

  return {
    id: note.id,
    title: `Note #${note.id}`,
    summary: truncatedSummary,
    urgencyEmoji: urgency.urgencyEmoji,
    ratingButtons,
  };
}

function createRatedNotesSummaryV2(
  currentPage: number,
  totalNotes: number,
  notesPerPage: number
): QueueSummaryV2 {
  const totalPages = Math.ceil(totalNotes / notesPerPage);
  const startIndex = (currentPage - 1) * notesPerPage;
  const endIndex = Math.min(startIndex + notesPerPage, totalNotes);

  if (totalNotes === 0) {
    return {
      title: `${V2_ICONS.RATED} Your Rated Notes`,
      subtitle: 'You have not rated any pending notes yet.',
      stats: 'Rate notes in the queue above to see them tracked here.',
    };
  }

  return {
    title: `${V2_ICONS.RATED} Your Rated Notes`,
    subtitle: `Showing ${startIndex + 1}-${endIndex} of ${totalNotes} notes`,
    stats: `Notes you have rated that are still being processed (Page ${currentPage}/${totalPages})`,
  };
}

function createRatedNoteItemV2(
  note: NoteWithRatings,
  userRating: boolean,
  thresholds: { min_ratings_needed: number; min_raters_per_note: number }
): QueueItemV2 {
  const ratingIndicator = userRating ? V2_ICONS.HELPFUL : V2_ICONS.NOT_HELPFUL;
  const ratingLabel = userRating ? 'Helpful' : 'Not Helpful';
  const uniqueRaters = new Set(note.ratings.map(r => r.rater_participant_id)).size;

  const truncatedSummary = note.summary.length > 150
    ? note.summary.substring(0, 147) + '...'
    : note.summary;

  const summaryWithRating = `${ratingIndicator} You rated: **${ratingLabel}**\n\n${truncatedSummary}\n\n*Progress: ${note.ratings_count}/${thresholds.min_ratings_needed} ratings, ${uniqueRaters}/${thresholds.min_raters_per_note} raters*`;

  const emptyButtonRow = new ActionRowBuilder<ButtonBuilder>();

  return {
    id: note.id,
    title: `Note #${note.id}`,
    summary: summaryWithRating,
    urgencyEmoji: V2_ICONS.RATED,
    ratingButtons: emptyButtonRow,
  };
}

export const data = new SlashCommandBuilder()
  .setName('list')
  .setDescription('View lists of notes and requests')
  .addSubcommand(subcommand =>
    subcommand
      .setName('notes')
      .setDescription('View all notes awaiting ratings in a private thread')
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
  if (lastUse && Date.now() - lastUse < RATE_LIMIT_MS) {
    const resetTime = Math.floor((lastUse + RATE_LIMIT_MS) / 1000);
    await interaction.reply({
      content: `Please wait. You can use this command again <t:${resetTime}:R>`,
      flags: MessageFlags.Ephemeral,
    });
    return;
  }

  lastUsage.set(userId, Date.now());

  try {
    await interaction.deferReply({ flags: MessageFlags.Ephemeral });

    if (!(interaction.channel instanceof TextChannel || interaction.channel instanceof ThreadChannel)) {
      await interaction.editReply({
        content: 'This command can only be used in text channels or threads.',
      });
      return;
    }

    logger.info(`User ${userId} requested notes queue`);

    let communityServerUuid: string | undefined;
    if (guildId) {
      try {
        const communityServer = await apiClient.getCommunityServerByPlatformId(guildId);
        communityServerUuid = communityServer.id;
      } catch (error) {
        logger.error('Failed to fetch community server UUID', {
          error_id: errorId,
          guild_id: guildId,
          error: error instanceof Error ? error.message : String(error),
        });
      }
    }

    const [thresholds, notesResponse] = await Promise.all([
      configCache.getRatingThresholds(),
      apiClient.listNotesWithStatus('NEEDS_MORE_RATINGS', 1, 10, communityServerUuid, userId),
    ]);

    logger.debug('Fetched thresholds and notes', {
      thresholds,
      totalNotes: notesResponse.total,
    });

    const queueManager = getQueueManager();
    const thread = await queueManager.getOrCreateOpenNotesThread(
      interaction.user,
      interaction.channel,
      guildId!,
      notesResponse.notes,
      notesResponse.total
    );

    const totalPages = Math.ceil(notesResponse.total / queueManager.getNotesPerPage());
    const hasNotes = notesResponse.total > 0;

    const summaryV2 = createSummaryV2(1, notesResponse.total, queueManager.getNotesPerPage());

    const member = interaction.guild?.members.cache.get(userId) || null;

    const itemsV2: QueueItemV2[] = notesResponse.notes.map((note) =>
      createNoteItemV2(note, thresholds, member)
    );

    const pagination: PaginationConfig | undefined =
      hasNotes && totalPages > 1
        ? {
            currentPage: 1,
            totalPages,
            previousButtonId: 'queue:previous',
            nextButtonId: 'queue:next',
          }
        : undefined;

    const renderResult = await QueueRendererV2.render(thread, summaryV2, itemsV2, pagination);

    await interaction.editReply({
      content: `Created notes queue in ${thread.toString()}`,
    });

    if (hasNotes) {
      const allMessages = QueueRendererV2.getAllMessages(renderResult);
    const collectors = allMessages.map((msg) =>
      msg.createMessageComponentCollector({
        componentType: ComponentType.Button,
        time: TIMEOUTS.QUEUE_NOTES_COLLECTOR_TIMEOUT_MS,
      })
    );

    const handleButtonInteraction = async (buttonInteraction: ButtonInteraction): Promise<void> => {
      if (buttonInteraction.user.id !== userId) {
        logger.warn('Unauthorized queue interaction attempt', {
          authorized_user: userId,
          attempted_user: buttonInteraction.user.id,
          custom_id: buttonInteraction.customId,
          guild_id: guildId,
          command: 'list notes',
        });
        await buttonInteraction.reply({
          content: 'This queue belongs to another user.',
          flags: MessageFlags.Ephemeral,
        });
        return;
      }

      if (buttonInteractionRateLimiter.checkAndRecord(buttonInteraction.user.id)) {
        await buttonInteraction.reply({
          content: '⏱️ Please wait a moment before clicking again.',
          flags: MessageFlags.Ephemeral,
        });
        return;
      }

      try {
        if (buttonInteraction.customId.startsWith('force_publish:')) {
          const parseResult = parseCustomId(buttonInteraction.customId, 2);
          if (!parseResult.success || !parseResult.parts) {
            logger.error('Failed to parse force_publish customId', {
              error_id: errorId,
              customId: buttonInteraction.customId,
              error: parseResult.error,
            });
            await buttonInteraction.reply({
              content: 'Invalid interaction data. Please try the command again.',
              flags: MessageFlags.Ephemeral,
            });
            return;
          }

          const noteId = parseResult.parts[1];

          if (!member || !hasManageGuildPermission(member)) {
            await buttonInteraction.reply({
              content: '❌ You do not have permission to force publish notes. Only server admins can use this feature.',
              flags: MessageFlags.Ephemeral,
            });
            return;
          }

          const fpShortId = generateShortId();
          const fpCacheKey = `fp_state:${fpShortId}`;
          await cache.set(fpCacheKey, { noteId, userId }, 60);

          const confirmationData = createForcePublishConfirmationButtons(noteId, fpShortId);

          const confirmReply = await buttonInteraction.reply({
            content: confirmationData.content,
            components: confirmationData.components,
            flags: MessageFlags.Ephemeral,
            fetchReply: true,
          });

          const confirmCollector = confirmReply.createMessageComponentCollector({
            componentType: ComponentType.Button,
            time: TIMEOUTS.FORCE_PUBLISH_CONFIRM_TIMEOUT_MS,
            max: 1,
          });

          confirmCollector.on('collect', (confirmInteraction: ButtonInteraction) => {
            void (async () => {
              try {
                if (confirmInteraction.user.id !== userId) {
                  await confirmInteraction.reply({
                    content: 'This confirmation belongs to another user.',
                    flags: MessageFlags.Ephemeral,
                  });
                  return;
                }

                if (confirmInteraction.customId.startsWith('fp_cancel:')) {
                  await confirmInteraction.update({
                    content: 'Force publish cancelled.',
                    components: [],
                  });
                  return;
                }

                if (confirmInteraction.customId.startsWith('fp_confirm:')) {
                  const confirmParseResult = parseCustomId(confirmInteraction.customId, 2);
                  if (!confirmParseResult.success || !confirmParseResult.parts) {
                    await confirmInteraction.update({
                      content: 'Invalid confirmation data.',
                      components: [],
                    });
                    return;
                  }

                  const confirmShortId = confirmParseResult.parts[1];
                  const confirmCacheKey = `fp_state:${confirmShortId}`;
                  const fpState = await cache.get<{ noteId: string; userId: string }>(confirmCacheKey);

                  if (!fpState) {
                    await confirmInteraction.update({
                      content: 'Confirmation state expired. Please try again.',
                      components: [],
                    });
                    return;
                  }

                  await confirmInteraction.deferUpdate();

                  const forcePublishErrorId = generateErrorId();
                  try {
                    const publishedNote = await apiClient.forcePublishNote(fpState.noteId);

                    logger.info('Note force-published from queue', {
                      error_id: forcePublishErrorId,
                      command: 'list notes',
                      user_id: userId,
                      community_server_id: guildId,
                      note_id: fpState.noteId,
                      force_published_at: publishedNote.force_published_at,
                    });

                    await confirmInteraction.editReply({
                      content: `✅ **Note #${fpState.noteId} has been force-published**\n\n` +
                               `The note was manually published by an admin and will be marked as "Admin Published" when displayed.\n\n` +
                               `**Published At:** <t:${Math.floor(new Date(publishedNote.force_published_at || publishedNote.updated_at || publishedNote.created_at).getTime() / 1000)}:F>`,
                      components: [],
                    });
                  } catch (error) {
                    const errorDetails = extractErrorDetails(error);

                    let errorMessage: string;
                    if (error instanceof Error && 'statusCode' in error) {
                      const apiError = error as { statusCode?: number; responseBody?: string };
                      switch (apiError.statusCode) {
                        case 403:
                          errorMessage = '❌ **Permission Denied**\n\nYou do not have admin privileges to force-publish notes.';
                          break;
                        case 404:
                          errorMessage = `❌ **Note Not Found**\n\nNote with ID \`${fpState.noteId}\` does not exist.`;
                          break;
                        case 400:
                          errorMessage = `❌ **Invalid Request**\n\n${(apiError.responseBody ?? 'Unknown error') || 'This note cannot be force-published.'}`;
                          break;
                        default:
                          errorMessage = `❌ An error occurred while force-publishing the note.\n\nError ID: \`${forcePublishErrorId}\``;
                      }
                    } else {
                      errorMessage = `❌ An error occurred while force-publishing the note.\n\nError ID: \`${forcePublishErrorId}\``;
                    }

                    logger.error('Error force-publishing note from queue', {
                      error_id: forcePublishErrorId,
                      command: 'list notes',
                      user_id: userId,
                      community_server_id: guildId,
                      note_id: fpState.noteId,
                      error: errorDetails.message,
                      error_type: errorDetails.type,
                      stack: errorDetails.stack,
                    });

                    await confirmInteraction.editReply({
                      content: errorMessage,
                      components: [],
                    });
                  }
                }
              } catch (error) {
                logger.error('Error in force publish confirmation handler', {
                  error_id: errorId,
                  noteId,
                  userId,
                  error: error instanceof Error ? error.message : String(error),
                });
              }
            })();
          });

          confirmCollector.on('end', (collected) => {
            void (async () => {
              if (collected.size === 0) {
                logger.debug('Force publish confirmation timed out', {
                  error_id: errorId,
                  noteId,
                  userId,
                });
                try {
                  await buttonInteraction.editReply({
                    content: 'Force publish confirmation timed out.',
                    components: createDisabledForcePublishButtons(fpShortId),
                  });
                } catch {
                  // Ignore errors when editing timed out message
                }
              }
            })();
          });

          return;
        }

        if (buttonInteraction.customId.startsWith('rate:') && (buttonInteraction.customId.includes(':helpful') || buttonInteraction.customId.includes(':not_helpful'))) {
          await buttonInteraction.deferUpdate();

          const parseResult = parseCustomId(buttonInteraction.customId, 3);
          if (!parseResult.success || !parseResult.parts) {
            logger.error('Failed to parse inline rating customId', {
              error_id: errorId,
              customId: buttonInteraction.customId,
              error: parseResult.error,
            });
            await buttonInteraction.followUp({
              content: 'Invalid interaction data. Please try again.',
              flags: MessageFlags.Ephemeral,
            });
            return;
          }

          const noteId = parseResult.parts[1];
          const helpful = parseResult.parts[2] === 'helpful';

          const rateNoteService = serviceProvider.getRateNoteService();
          const result = await rateNoteService.execute({
            noteId,
            userId,
            helpful,
          });

          if (!result.success) {
            const errorResponse = DiscordFormatter.formatError(result);
            await buttonInteraction.followUp({
              content: errorResponse.content || 'Failed to submit rating.',
              flags: MessageFlags.Ephemeral,
            });
            return;
          }

          const ratedButton = new ButtonBuilder()
            .setCustomId(`rated:${noteId}`)
            .setLabel(helpful ? 'Rated Helpful' : 'Rated Not Helpful')
            .setStyle(helpful ? ButtonStyle.Success : ButtonStyle.Danger)
            .setDisabled(true);

          const newButtons: ButtonBuilder[] = [ratedButton];

          const originalComponents = buttonInteraction.message.components;
          if (originalComponents.length > 0) {
            const firstRow = originalComponents[0];
            if (firstRow.type === ComponentType.ActionRow) {
              for (const btn of firstRow.components) {
                if (btn.type === ComponentType.Button && 'customId' in btn && btn.customId?.startsWith('force_publish:')) {
                  const forcePublishButtonBuilder = new ButtonBuilder()
                    .setCustomId(btn.customId)
                    .setLabel('Force Publish')
                    .setStyle(ButtonStyle.Danger);
                  newButtons.push(forcePublishButtonBuilder);
                  break;
                }
              }
            }
          }

          const newButtonRow = new ActionRowBuilder<ButtonBuilder>().addComponents(...newButtons);

          await buttonInteraction.editReply({
            components: [newButtonRow],
          });

          logger.info('Note rated inline from queue', { noteId, userId, helpful });
          return;
        }

        await buttonInteraction.deferUpdate();

        let currentPage = queueManager.getCurrentPage(userId, guildId!);

        if (buttonInteraction.customId === 'queue:next') {
          currentPage++;
        } else if (buttonInteraction.customId === 'queue:previous') {
          currentPage--;
        }

        queueManager.setPage(userId, guildId!, currentPage);

        const newNotesResponse = await apiClient.listNotesWithStatus(
          'NEEDS_MORE_RATINGS',
          currentPage,
          queueManager.getNotesPerPage(),
          communityServerUuid,
          userId
        );

        queueManager.updateNotes(userId, guildId!, newNotesResponse.notes, newNotesResponse.total);

        const newSummaryV2 = createSummaryV2(
          currentPage,
          newNotesResponse.total,
          queueManager.getNotesPerPage()
        );

        const newItemsV2: QueueItemV2[] = newNotesResponse.notes.map((note) =>
          createNoteItemV2(note, thresholds, member)
        );

        const newTotalPages = Math.ceil(
          newNotesResponse.total / queueManager.getNotesPerPage()
        );

        const newPagination: PaginationConfig | undefined =
          newNotesResponse.notes.length > 0 && newTotalPages > 1
            ? {
                currentPage,
                totalPages: newTotalPages,
                previousButtonId: 'queue:previous',
                nextButtonId: 'queue:next',
              }
            : undefined;

        const updatedResult = await QueueRendererV2.update(
          renderResult,
          newSummaryV2,
          newItemsV2,
          newPagination
        );

        collectors.forEach((c) => c.stop());

        const newMessages = QueueRendererV2.getAllMessages(updatedResult);
        const newCollectors = newMessages.map((msg) =>
          msg.createMessageComponentCollector({
            componentType: ComponentType.Button,
            time: TIMEOUTS.QUEUE_NOTES_COLLECTOR_TIMEOUT_MS,
          })
        );

        newCollectors.forEach((collector) => {
          collector.on('collect', (interaction) => {
            void handleButtonInteraction(interaction);
          });
          collector.on('end', () => {
            logger.debug('Notes queue button collector ended', { userId, command: 'list notes' });
          });
        });

        collectors.length = 0;
        collectors.push(...newCollectors);
        Object.assign(renderResult, updatedResult);
      } catch (error) {
        const errorType = classifyApiError(error);
        const errorDetails = extractErrorDetails(error);
        const buttonErrorId = generateErrorId();

        logger.error('Error handling queue button interaction', {
          error_id: buttonErrorId,
          command: 'list notes',
          user_id: userId,
          community_server_id: guildId,
          custom_id: buttonInteraction.customId,
          error_type: errorType,
          error: errorDetails.message,
          stack: errorDetails.stack,
        });

        const userMessage = `${getPaginationErrorMessage(errorType)}\n\nError ID: \`${buttonErrorId}\``;
        await buttonInteraction.followUp({
          content: userMessage,
          flags: MessageFlags.Ephemeral,
        });
      }
    };

    collectors.forEach((collector) => {
      collector.on('collect', (interaction) => {
        void handleButtonInteraction(interaction);
      });
      collector.on('end', () => {
        logger.debug('Notes queue button collector ended', { userId, command: 'list notes' });
      });
    });
    }

    // === YOUR RATED NOTES SECTION ===
    try {
      if (!communityServerUuid) {
        logger.debug('Skipping rated notes section - no community server UUID', {
          error_id: errorId,
          user_id: userId,
          guild_id: guildId,
        });
      } else {
        const ratedNotesPage = 1;

        const ratedNotesResponse = await apiClient.listNotesRatedByUser(
          userId,
          ratedNotesPage,
          RATED_NOTES_PER_PAGE,
          communityServerUuid,
          'NEEDS_MORE_RATINGS'
        );

        logger.debug('Fetched rated notes', {
          error_id: errorId,
          user_id: userId,
          total: ratedNotesResponse.total,
          page: ratedNotesPage,
        });

        // Generate short ID for caching pagination state
        const ratedNotesStateId = generateShortId();
        const ratedNotesCacheKey = `rated_notes_state:${ratedNotesStateId}`;
        await cache.set(
          ratedNotesCacheKey,
          {
            userId,
            guildId,
            communityServerUuid,
            currentPage: ratedNotesPage,
          },
          3600
        );

        const ratedNotesSummaryV2 = createRatedNotesSummaryV2(
          ratedNotesPage,
          ratedNotesResponse.total,
          RATED_NOTES_PER_PAGE
        );

        const ratedNotesItemsV2: QueueItemV2[] = ratedNotesResponse.notes.map((note) => {
          const userRatingRecord = note.ratings.find(
            (r) => String(r.rater_participant_id) === String(userId)
          );
          const isHelpful = userRatingRecord?.helpfulness_level === 'HELPFUL';
          return createRatedNoteItemV2(note, isHelpful ?? false, thresholds);
        });

        const ratedNotesTotalPages = Math.ceil(ratedNotesResponse.total / RATED_NOTES_PER_PAGE);
        const ratedNotesPagination: PaginationConfig | undefined =
          ratedNotesResponse.total > 0 && ratedNotesTotalPages > 1
            ? createRatedNotesPagination(ratedNotesPage, ratedNotesTotalPages, ratedNotesStateId)
            : undefined;

        let ratedNotesRenderResult = await QueueRendererV2.render(
          thread,
          ratedNotesSummaryV2,
          ratedNotesItemsV2,
          ratedNotesPagination
        );

        // Set up collectors for rated notes pagination
        if (ratedNotesResponse.total > RATED_NOTES_PER_PAGE) {
          const ratedNotesMessages = QueueRendererV2.getAllMessages(ratedNotesRenderResult);
          let ratedNotesCollectors = ratedNotesMessages.map((msg) =>
            msg.createMessageComponentCollector({
              componentType: ComponentType.Button,
              time: TIMEOUTS.QUEUE_NOTES_COLLECTOR_TIMEOUT_MS,
            })
          );

          const handleRatedNotesButtonInteraction = async (
            buttonInteraction: ButtonInteraction
          ): Promise<void> => {
            if (buttonInteraction.user.id !== userId) {
              await buttonInteraction.reply({
                content: 'This section belongs to another user.',
                flags: MessageFlags.Ephemeral,
              });
              return;
            }

            if (buttonInteractionRateLimiter.checkAndRecord(buttonInteraction.user.id)) {
              await buttonInteraction.reply({
                content: 'Please wait a moment before clicking again.',
                flags: MessageFlags.Ephemeral,
              });
              return;
            }

            try {
              const customId = buttonInteraction.customId;
              if (!customId.startsWith('rn_prev:') && !customId.startsWith('rn_next:')) {
                return;
              }

              await buttonInteraction.deferUpdate();

              const parseResult = parseCustomId(customId, 2);
              if (!parseResult.success || !parseResult.parts) {
                logger.error('Failed to parse rated notes pagination customId', {
                  error_id: errorId,
                  customId,
                  error: parseResult.error,
                });
                await buttonInteraction.followUp({
                  content: 'Invalid interaction data. Please try the command again.',
                  flags: MessageFlags.Ephemeral,
                });
                return;
              }

              const stateId = parseResult.parts[1];
              const cacheKey = `rated_notes_state:${stateId}`;
              const state = await cache.get<{
                userId: string;
                guildId: string;
                communityServerUuid: string;
                currentPage: number;
              }>(cacheKey);

              if (!state) {
                logger.error('Rated notes pagination state not found in cache', {
                  error_id: errorId,
                  stateId,
                  cacheKey,
                });
                await buttonInteraction.followUp({
                  content: 'Pagination state expired. Please run the command again.',
                  flags: MessageFlags.Ephemeral,
                });
                return;
              }

              let newPage = state.currentPage;
              if (customId.startsWith('rn_prev:')) {
                newPage = Math.max(1, newPage - 1);
              } else if (customId.startsWith('rn_next:')) {
                newPage++;
              }

              // Fetch new page of rated notes
              const newRatedNotesResponse = await apiClient.listNotesRatedByUser(
                state.userId,
                newPage,
                RATED_NOTES_PER_PAGE,
                state.communityServerUuid,
                'NEEDS_MORE_RATINGS'
              );

              // Update cache with new page
              await cache.set(
                cacheKey,
                {
                  ...state,
                  currentPage: newPage,
                },
                3600
              );

              const newRatedNotesSummaryV2 = createRatedNotesSummaryV2(
                newPage,
                newRatedNotesResponse.total,
                RATED_NOTES_PER_PAGE
              );

              const newRatedNotesItemsV2: QueueItemV2[] = newRatedNotesResponse.notes.map((note) => {
                const userRatingRecord = note.ratings.find(
                  (r) => String(r.rater_participant_id) === String(state.userId)
                );
                const isHelpful = userRatingRecord?.helpfulness_level === 'HELPFUL';
                return createRatedNoteItemV2(note, isHelpful ?? false, thresholds);
              });

              const newRatedNotesTotalPages = Math.ceil(
                newRatedNotesResponse.total / RATED_NOTES_PER_PAGE
              );
              const newRatedNotesPagination: PaginationConfig | undefined =
                newRatedNotesResponse.total > 0 && newRatedNotesTotalPages > 1
                  ? createRatedNotesPagination(newPage, newRatedNotesTotalPages, stateId)
                  : undefined;

              const updatedRatedNotesResult = await QueueRendererV2.update(
                ratedNotesRenderResult,
                newRatedNotesSummaryV2,
                newRatedNotesItemsV2,
                newRatedNotesPagination
              );

              // Stop old collectors and create new ones
              ratedNotesCollectors.forEach((c) => c.stop());

              const newRatedNotesMessages = QueueRendererV2.getAllMessages(updatedRatedNotesResult);
              const newRatedNotesCollectors = newRatedNotesMessages.map((msg) =>
                msg.createMessageComponentCollector({
                  componentType: ComponentType.Button,
                  time: TIMEOUTS.QUEUE_NOTES_COLLECTOR_TIMEOUT_MS,
                })
              );

              newRatedNotesCollectors.forEach((collector) => {
                collector.on('collect', (btnInteraction) => {
                  void handleRatedNotesButtonInteraction(btnInteraction);
                });
                collector.on('end', () => {
                  logger.debug('Rated notes button collector ended', {
                    userId,
                    command: 'list notes',
                  });
                });
              });

              ratedNotesCollectors = newRatedNotesCollectors;
              ratedNotesRenderResult = updatedRatedNotesResult;

              logger.info('Rated notes page changed', {
                error_id: errorId,
                user_id: userId,
                new_page: newPage,
                result_count: newRatedNotesResponse.notes.length,
                total: newRatedNotesResponse.total,
              });
            } catch (error) {
              const buttonErrorId = generateErrorId();
              const errorDetails = extractErrorDetails(error);

              logger.error('Error handling rated notes pagination', {
                error_id: buttonErrorId,
                command: 'list notes',
                user_id: userId,
                custom_id: buttonInteraction.customId,
                error: errorDetails.message,
                stack: errorDetails.stack,
              });

              await buttonInteraction.followUp({
                content: `Failed to load page. Please try again.\n\nError ID: \`${buttonErrorId}\``,
                flags: MessageFlags.Ephemeral,
              });
            }
          };

          ratedNotesCollectors.forEach((collector) => {
            collector.on('collect', (btnInteraction) => {
              void handleRatedNotesButtonInteraction(btnInteraction);
            });
            collector.on('end', () => {
              logger.debug('Rated notes button collector ended', { userId, command: 'list notes' });
            });
          });
        }

        logger.info('Rated notes section rendered', {
          error_id: errorId,
          user_id: userId,
          total_notes: ratedNotesResponse.total,
        });
      }
    } catch (ratedNotesError) {
      const ratedNotesErrorDetails = extractErrorDetails(ratedNotesError);
      logger.error('Error rendering rated notes section', {
        error_id: errorId,
        user_id: userId,
        guild_id: guildId,
        error: ratedNotesErrorDetails.message,
        stack: ratedNotesErrorDetails.stack,
      });
    }
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
  const size = interaction.options.getInteger('page-size') || 5;
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

    if (!(interaction.channel instanceof TextChannel || interaction.channel instanceof ThreadChannel)) {
      await interaction.editReply({
        content: 'This command can only be used in text channels or threads.',
      });
      return;
    }

    let communityServerUuid: string | undefined;
    if (guildId) {
      try {
        const communityServer = await apiClient.getCommunityServerByPlatformId(guildId);
        communityServerUuid = communityServer.id;
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
      const errorResponse = DiscordFormatter.formatError(result);
      await interaction.editReply(errorResponse);
      return;
    }

    if (!result.data) {
      await interaction.editReply({
        content: 'No data returned from the service.',
      });
      return;
    }

    const queueManager = getQueueManager();
    const thread = await queueManager.getOrCreateOpenNotesThread(
      interaction.user,
      interaction.channel,
      guildId!,
      [],
      0
    );

    const formattedData = await DiscordFormatter.formatListRequestsSuccess(result.data, {
      status: status || undefined,
      myRequestsOnly,
      communityServerId: communityServerUuid,
    });

    const renderResult = await QueueRenderer.render(
      thread,
      formattedData.summary,
      formattedData.items,
      formattedData.pagination
    );

    await interaction.editReply({
      content: `Request queue posted to ${String(thread)}`,
    });

    logger.info('List requests completed successfully', {
      error_id: errorId,
      command: 'list requests',
      user_id: userId,
      result_count: result.data.requests.length,
      total: result.data.total,
    });

    const allMessages = QueueRenderer.getAllMessages(renderResult);
    const collectors = allMessages.map((msg) =>
      msg.createMessageComponentCollector({
        componentType: ComponentType.Button,
        time: TIMEOUTS.QUEUE_NOTES_COLLECTOR_TIMEOUT_MS,
      })
    );

    const handleButtonInteraction = async (buttonInteraction: ButtonInteraction): Promise<void> => {
      if (buttonInteraction.user.id !== userId) {
        await buttonInteraction.reply({
          content: 'This request queue belongs to another user.',
          flags: MessageFlags.Ephemeral,
        });
        return;
      }

      try {
        if (buttonInteraction.customId.startsWith('request_queue_page:')) {
            const parseResult = parseCustomId(buttonInteraction.customId, 3);
            if (!parseResult.success || !parseResult.parts) {
              logger.error('Failed to parse request_queue_page customId', {
                error_id: errorId,
                customId: buttonInteraction.customId,
                error: parseResult.error,
              });
              await buttonInteraction.reply({
                content: 'Invalid interaction data. Please try the command again.',
                flags: MessageFlags.Ephemeral,
              });
              return;
            }

            const newPage = parseInt(parseResult.parts[1], 10);
            const stateId = parseResult.parts[2];

            await buttonInteraction.deferUpdate();

            try {
              const cacheKey = `pagination:${stateId}`;
              const filterState = await cache.get<{
                status?: string;
                myRequestsOnly?: boolean;
                communityServerId?: string;
              }>(cacheKey);

              if (!filterState) {
                logger.error('Pagination state not found in cache', {
                  error_id: errorId,
                  stateId,
                  cacheKey,
                });
                await buttonInteraction.editReply({
                  content: 'Pagination state expired. Please run the command again.',
                });
                return;
              }

              logger.debug('Retrieved pagination state from cache', { stateId, cacheKey, filterState });

              const listRequestsService = serviceProvider.getListRequestsService();
              const result = await listRequestsService.execute({
                userId,
                page: newPage,
                size,
                status: filterState.status as RequestStatus | undefined,
                myRequestsOnly: filterState.myRequestsOnly ?? false,
                communityServerId: filterState.communityServerId,
              });

              if (!result.success) {
                const errorResponse = DiscordFormatter.formatError(result);
                await buttonInteraction.editReply(errorResponse);
                return;
              }

              if (!result.data) {
                await buttonInteraction.followUp({
                  content: 'No data returned from the service.',
                  flags: MessageFlags.Ephemeral,
                });
                return;
              }

              const newFormattedData = await DiscordFormatter.formatListRequestsSuccess(result.data, {
                status: filterState.status,
                myRequestsOnly: filterState.myRequestsOnly,
                communityServerId: filterState.communityServerId,
              });

              const updatedResult = await QueueRenderer.update(
                renderResult,
                newFormattedData.summary,
                newFormattedData.items,
                newFormattedData.pagination
              );

              collectors.forEach((c) => c.stop());

              const newMessages = QueueRenderer.getAllMessages(updatedResult);
              const newCollectors = newMessages.map((msg) =>
                msg.createMessageComponentCollector({
                  componentType: ComponentType.Button,
                  time: TIMEOUTS.QUEUE_NOTES_COLLECTOR_TIMEOUT_MS,
                })
              );

              newCollectors.forEach((collector) => {
                collector.on('collect', (interaction) => {
                  void handleButtonInteraction(interaction);
                });
              });

              collectors.length = 0;
              collectors.push(...newCollectors);
              Object.assign(renderResult, updatedResult);

              logger.info('Request queue page changed', {
                error_id: errorId,
                user_id: userId,
                new_page: newPage,
                result_count: result.data.requests.length,
                total: result.data.total,
              });
            } catch (error) {
              logger.error('Failed to retrieve pagination state or fetch page', {
                error_id: errorId,
                state_id: stateId,
                error: error instanceof Error ? error.message : String(error),
              });
              await buttonInteraction.editReply({
                content: 'Failed to load page. Please try the command again.',
              });
            }
          } else if (buttonInteraction.customId.startsWith('write_note:')) {
            const parseResult = parseCustomId(buttonInteraction.customId, 3);
            if (!parseResult.success || !parseResult.parts) {
              logger.error('Failed to parse write_note customId', {
                error_id: errorId,
                customId: buttonInteraction.customId,
                error: parseResult.error,
              });
              await buttonInteraction.reply({
                content: 'Invalid interaction data. Please try the command again.',
                flags: MessageFlags.Ephemeral,
              });
              return;
            }

            const classification = parseResult.parts[1];
            const shortId = parseResult.parts[2];
            const cacheKey = `write_note_state:${shortId}`;

            const requestId = await cache.get<string>(cacheKey);

            if (!requestId) {
              logger.error('Write note button state not found in cache', {
                error_id: errorId,
                shortId,
                cacheKey,
              });
              await buttonInteraction.reply({
                content: 'Button state expired. Please run the /list requests command again.',
                flags: MessageFlags.Ephemeral,
              });
              return;
            }

            logger.debug('Retrieved write note button state from cache', { shortId, cacheKey, requestId, classification });

            const { generateShortId } = await import('../lib/validation.js');
            const modalShortId = generateShortId();
            const modalCacheKey = `write_note_modal_state:${modalShortId}`;
            const classificationCacheKey = `write_note_classification:${modalShortId}`;

            await cache.set(modalCacheKey, requestId, 300);
            await cache.set(classificationCacheKey, classification, 300);

            logger.debug('Stored classification in cache', { modalShortId, classification });

            const Discord = await import('discord.js');

            const modal = new Discord.ModalBuilder()
              .setCustomId(`write_note_modal:${modalShortId}`)
              .setTitle('Write Community Note');

            const summaryInput = new Discord.TextInputBuilder()
              .setCustomId('summary')
              .setLabel('Note Summary')
              .setStyle(Discord.TextInputStyle.Paragraph)
              .setPlaceholder('Explain what is misleading or provide context...')
              .setRequired(true)
              .setMaxLength(280);

            const modalRow = new ActionRowBuilder<TextInputBuilder>()
              .addComponents(summaryInput);

            modal.addComponents(modalRow);

            await buttonInteraction.showModal(modal);
          } else if (buttonInteraction.customId.startsWith('ai_write_note:')) {
            const parseResult = parseCustomId(buttonInteraction.customId, 2);
            if (!parseResult.success || !parseResult.parts) {
              logger.error('Failed to parse ai_write_note customId', {
                error_id: errorId,
                customId: buttonInteraction.customId,
                error: parseResult.error,
              });
              await buttonInteraction.reply({
                content: 'Invalid interaction data. Please try the command again.',
                flags: MessageFlags.Ephemeral,
              });
              return;
            }

            const shortId = parseResult.parts[1];
            const cacheKey = `write_note_state:${shortId}`;

            const requestId = await cache.get<string>(cacheKey);

            if (!requestId) {
              logger.error('AI write note button state not found in cache', {
                error_id: errorId,
                shortId,
                cacheKey,
              });
              await buttonInteraction.reply({
                content: 'Button state expired. Please run the /list requests command again.',
                flags: MessageFlags.Ephemeral,
              });
              return;
            }

            logger.debug('Retrieved AI write note button state from cache', { shortId, cacheKey, requestId });

            await buttonInteraction.deferReply({ flags: MessageFlags.Ephemeral });

            logger.info('Generating AI note for request', {
              error_id: errorId,
              request_id: requestId,
              user_id: userId,
            });

            try {
              const noteResult = await apiClient.generateAiNote(requestId);

              logger.info('AI note generated successfully', {
                error_id: errorId,
                request_id: requestId,
                note_id: noteResult.id,
                user_id: userId,
              });

              await buttonInteraction.editReply({
                content: [
                  '✨ **AI Note Generated Successfully!**',
                  '',
                  `**Note ID:** ${noteResult.id}`,
                  `**Summary:** ${noteResult.summary}`,
                  `**Classification:** ${noteResult.classification}`,
                  '',
                  '_Note: The AI-generated note has been created and is now available for rating._',
                ].join('\n'),
              });
            } catch (error) {
              const errorDetails = extractErrorDetails(error);

              logger.error('Failed to generate AI note', {
                error_id: errorId,
                request_id: requestId,
                user_id: userId,
                error: errorDetails.message,
                error_type: errorDetails.type,
                stack: errorDetails.stack,
                ...(error instanceof ApiError && {
                  endpoint: error.endpoint,
                  status_code: error.statusCode,
                  response_body: error.responseBody,
                }),
              });

              let errorMessage = 'Failed to generate AI note.';
              if (error instanceof ApiError) {
                if (error.statusCode === 400) {
                  errorMessage =
                    'This request cannot be used for AI note generation. It may be missing required fact-check data.';
                } else if (error.statusCode === 429) {
                  errorMessage = 'Rate limit exceeded. Please try again later.';
                } else if (error.statusCode === 503) {
                  errorMessage = 'AI note writing service is currently unavailable.';
                }
              }

              await buttonInteraction.editReply({
                content: formatErrorForUser(errorId, errorMessage),
              });
            }
          }
      } catch (error) {
        logger.error('Error handling button interaction', {
          error_id: errorId,
          command: 'list requests',
          user_id: userId,
          custom_id: buttonInteraction.customId,
          error: extractErrorDetails(error).message,
        });

        if (buttonInteraction.deferred) {
          await buttonInteraction.editReply({
            content: 'An error occurred. Please try again.',
          });
        } else {
          await buttonInteraction.reply({
            content: 'An error occurred. Please try again.',
            flags: MessageFlags.Ephemeral,
          });
        }
      }
    };

    collectors.forEach((collector) => {
      collector.on('collect', (interaction) => {
        void handleButtonInteraction(interaction);
      });
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

    if (!(interaction.channel instanceof TextChannel || interaction.channel instanceof ThreadChannel)) {
      await interaction.editReply({
        content: 'This command can only be used in text channels or threads.',
      });
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

    if (result.data!.notes.length === 0) {
      await interaction.editReply({
        content: 'No notes found matching the specified criteria.',
      });
      return;
    }

    const queueManager = getQueueManager();
    const thread = await queueManager.getOrCreateOpenNotesThread(
      interaction.user,
      interaction.channel,
      guildId!,
      [],
      0
    );

    const member = interaction.guild?.members.cache.get(userId) || null;

    const formattedData = DiscordFormatter.formatTopNotesForQueue(result.data!, 1, limit, member);

    const renderResult = await QueueRenderer.render(
      thread,
      formattedData.summary,
      formattedData.items,
      formattedData.pagination
    );

    await interaction.editReply({
      content: `Top notes posted to ${String(thread)}`,
    });

    const hasAdminButtons = member && hasManageGuildPermission(member);
    if (hasAdminButtons) {
      const allMessages = QueueRenderer.getAllMessages(renderResult);
      const collectors = allMessages.map((msg) =>
        msg.createMessageComponentCollector({
          componentType: ComponentType.Button,
          time: TIMEOUTS.QUEUE_NOTES_COLLECTOR_TIMEOUT_MS,
        })
      );

      const handleButtonInteraction = async (buttonInteraction: ButtonInteraction): Promise<void> => {
        if (buttonInteraction.user.id !== userId) {
          logger.warn('Unauthorized top-notes interaction attempt', {
            authorized_user: userId,
            attempted_user: buttonInteraction.user.id,
            custom_id: buttonInteraction.customId,
            guild_id: guildId,
            command: 'list top-notes',
          });
          await buttonInteraction.reply({
            content: 'This queue belongs to another user.',
            flags: MessageFlags.Ephemeral,
          });
          return;
        }

        if (buttonInteractionRateLimiter.checkAndRecord(buttonInteraction.user.id)) {
          await buttonInteraction.reply({
            content: '⏱️ Please wait a moment before clicking again.',
            flags: MessageFlags.Ephemeral,
          });
          return;
        }

        try {
          if (buttonInteraction.customId.startsWith('force_publish:')) {
            const parseResult = parseCustomId(buttonInteraction.customId, 2);
            if (!parseResult.success || !parseResult.parts) {
              logger.error('Failed to parse force_publish customId in top-notes', {
                error_id: errorId,
                customId: buttonInteraction.customId,
                error: parseResult.error,
              });
              await buttonInteraction.reply({
                content: 'Invalid interaction data. Please try the command again.',
                flags: MessageFlags.Ephemeral,
              });
              return;
            }

            const noteId = parseResult.parts[1];

            if (!member || !hasManageGuildPermission(member)) {
              await buttonInteraction.reply({
                content: '❌ You do not have permission to force publish notes. Only server admins can use this feature.',
                flags: MessageFlags.Ephemeral,
              });
              return;
            }

            const fpShortId = generateShortId();
            const fpCacheKey = `fp_state:${fpShortId}`;
            await cache.set(fpCacheKey, { noteId, userId }, 60);

            const confirmationData = createForcePublishConfirmationButtons(noteId, fpShortId);

            const confirmReply = await buttonInteraction.reply({
              content: confirmationData.content,
              components: confirmationData.components,
              flags: MessageFlags.Ephemeral,
              fetchReply: true,
            });

            const confirmCollector = confirmReply.createMessageComponentCollector({
              componentType: ComponentType.Button,
              time: TIMEOUTS.FORCE_PUBLISH_CONFIRM_TIMEOUT_MS,
              max: 1,
            });

            confirmCollector.on('collect', (confirmInteraction: ButtonInteraction) => {
              void (async () => {
                try {
                  if (confirmInteraction.user.id !== userId) {
                    await confirmInteraction.reply({
                      content: 'This confirmation belongs to another user.',
                      flags: MessageFlags.Ephemeral,
                    });
                    return;
                  }

                  if (confirmInteraction.customId.startsWith('fp_cancel:')) {
                    await confirmInteraction.update({
                      content: 'Force publish cancelled.',
                      components: [],
                    });
                    return;
                  }

                  if (confirmInteraction.customId.startsWith('fp_confirm:')) {
                    const confirmParseResult = parseCustomId(confirmInteraction.customId, 2);
                    if (!confirmParseResult.success || !confirmParseResult.parts) {
                      await confirmInteraction.update({
                        content: 'Invalid confirmation data.',
                        components: [],
                      });
                      return;
                    }

                    const confirmShortId = confirmParseResult.parts[1];
                    const confirmCacheKey = `fp_state:${confirmShortId}`;
                    const fpState = await cache.get<{ noteId: string; userId: string }>(confirmCacheKey);

                    if (!fpState) {
                      await confirmInteraction.update({
                        content: 'Confirmation state expired. Please try again.',
                        components: [],
                      });
                      return;
                    }

                    await confirmInteraction.deferUpdate();

                    const forcePublishErrorId = generateErrorId();
                    try {
                      const publishedNote = await apiClient.forcePublishNote(fpState.noteId);

                      logger.info('Note force-published from top-notes', {
                        error_id: forcePublishErrorId,
                        command: 'list top-notes',
                        user_id: userId,
                        community_server_id: guildId,
                        note_id: fpState.noteId,
                        force_published_at: publishedNote.force_published_at,
                      });

                      await confirmInteraction.editReply({
                        content: `✅ **Note #${fpState.noteId} has been force-published**\n\n` +
                                 `The note was manually published by an admin and will be marked as "Admin Published" when displayed.\n\n` +
                                 `**Published At:** <t:${Math.floor(new Date(publishedNote.force_published_at || publishedNote.updated_at || publishedNote.created_at).getTime() / 1000)}:F>`,
                        components: [],
                      });
                    } catch (error) {
                      const errorDetails = extractErrorDetails(error);

                      let errorMessage: string;
                      if (error instanceof Error && 'statusCode' in error) {
                        const apiError = error as { statusCode?: number; responseBody?: string };
                        switch (apiError.statusCode) {
                          case 403:
                            errorMessage = '❌ **Permission Denied**\n\nYou do not have admin privileges to force-publish notes.';
                            break;
                          case 404:
                            errorMessage = `❌ **Note Not Found**\n\nNote with ID \`${fpState.noteId}\` does not exist.`;
                            break;
                          case 400:
                            errorMessage = `❌ **Invalid Request**\n\n${(apiError.responseBody ?? 'Unknown error') || 'This note cannot be force-published.'}`;
                            break;
                          default:
                            errorMessage = `❌ An error occurred while force-publishing the note.\n\nError ID: \`${forcePublishErrorId}\``;
                        }
                      } else {
                        errorMessage = `❌ An error occurred while force-publishing the note.\n\nError ID: \`${forcePublishErrorId}\``;
                      }

                      logger.error('Error force-publishing note from top-notes', {
                        error_id: forcePublishErrorId,
                        command: 'list top-notes',
                        user_id: userId,
                        community_server_id: guildId,
                        note_id: fpState.noteId,
                        error: errorDetails.message,
                        error_type: errorDetails.type,
                        stack: errorDetails.stack,
                      });

                      await confirmInteraction.editReply({
                        content: errorMessage,
                        components: [],
                      });
                    }
                  }
                } catch (error) {
                  logger.error('Error in force publish confirmation handler (top-notes)', {
                    error_id: errorId,
                    noteId,
                    userId,
                    error: error instanceof Error ? error.message : String(error),
                  });
                }
              })();
            });

            confirmCollector.on('end', (collected) => {
              void (async () => {
                if (collected.size === 0) {
                  logger.debug('Force publish confirmation timed out (top-notes)', {
                    error_id: errorId,
                    noteId,
                    userId,
                  });
                  try {
                    await buttonInteraction.editReply({
                      content: 'Force publish confirmation timed out.',
                      components: createDisabledForcePublishButtons(fpShortId),
                    });
                  } catch {
                    // Ignore errors when editing timed out message
                  }
                }
              })();
            });

            return;
          }
        } catch (error) {
          const errorDetails = extractErrorDetails(error);
          const buttonErrorId = generateErrorId();

          logger.error('Error handling top-notes button interaction', {
            error_id: buttonErrorId,
            command: 'list top-notes',
            user_id: userId,
            community_server_id: guildId,
            custom_id: buttonInteraction.customId,
            error: errorDetails.message,
            stack: errorDetails.stack,
          });

          await buttonInteraction.followUp({
            content: `An error occurred. Please try again.\n\nError ID: \`${buttonErrorId}\``,
            flags: MessageFlags.Ephemeral,
          });
        }
      };

      collectors.forEach((collector) => {
        collector.on('collect', (interaction) => {
          void handleButtonInteraction(interaction);
        });
        collector.on('end', () => {
          logger.debug('Top-notes button collector ended', { userId, command: 'list top-notes' });
        });
      });
    }

    logger.info('Top notes retrieved successfully', {
      error_id: errorId,
      command: 'list top-notes',
      user_id: userId,
      note_count: result.data!.notes.length,
      total_count: result.data!.total_count,
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

    const request = await apiClient.getRequest(requestId);

    const messageId = extractPlatformMessageId(request.platform_message_id, request.request_id);
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
      const errorResponse = DiscordFormatter.formatError(result);
      await interaction.editReply(errorResponse);
      return;
    }

    const response = DiscordFormatter.formatWriteNoteSuccess(result.data!, messageId);
    await interaction.editReply(response);

    logger.info('Note created from request queue', {
      error_id: errorId,
      request_id: requestId,
      user_id: interaction.user.id,
      note_id: result.data?.note.id,
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

    if (!(interaction.channel instanceof TextChannel || interaction.channel instanceof ThreadChannel)) {
      await interaction.editReply({
        content: 'This button can only be used in text channels or threads.',
      });
      return;
    }

    if (!guildId) {
      await interaction.editReply({
        content: 'This button can only be used in a server.',
      });
      return;
    }

    let communityServerUuid: string | undefined;
    try {
      const communityServer = await apiClient.getCommunityServerByPlatformId(guildId);
      communityServerUuid = communityServer.id;
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
        size: 5,
        status: undefined,
        myRequestsOnly: false,
        communityServerId: communityServerUuid,
      });

      if (!result.success) {
        const errorResponse = DiscordFormatter.formatError(result);
        await interaction.editReply(errorResponse);
        return;
      }

      if (!result.data) {
        await interaction.editReply({
          content: 'No data returned from the service.',
        });
        return;
      }

      const queueManager = getQueueManager();
      const thread = await queueManager.getOrCreateOpenNotesThread(
        interaction.user,
        interaction.channel,
        guildId,
        [],
        0
      );

      const formattedData = await DiscordFormatter.formatListRequestsSuccess(result.data, {
        status: undefined,
        myRequestsOnly: false,
        communityServerId: communityServerUuid,
      });

      await QueueRenderer.render(
        thread,
        formattedData.summary,
        formattedData.items,
        formattedData.pagination
      );

      await interaction.editReply({
        content: `Request queue posted to ${String(thread)}`,
      });

      logger.info('List requests from button completed successfully', {
        error_id: errorId,
        user_id: userId,
        result_count: result.data.requests.length,
        total: result.data.total,
      });
    } else if (customId === 'request_reply:list_notes') {
      const [thresholds, notesResponse] = await Promise.all([
        configCache.getRatingThresholds(),
        apiClient.listNotesWithStatus('NEEDS_MORE_RATINGS', 1, 10, communityServerUuid, userId),
      ]);

      const queueManager = getQueueManager();
      const thread = await queueManager.getOrCreateOpenNotesThread(
        interaction.user,
        interaction.channel,
        guildId,
        notesResponse.notes,
        notesResponse.total
      );

      const totalPages = Math.ceil(notesResponse.total / queueManager.getNotesPerPage());
      const hasNotes = notesResponse.total > 0;

      const summaryV2 = createSummaryV2(1, notesResponse.total, queueManager.getNotesPerPage());

      const member = interaction.guild?.members.cache.get(userId) || null;

      const itemsV2: QueueItemV2[] = notesResponse.notes.map((note) =>
        createNoteItemV2(note, thresholds, member)
      );

      const pagination: PaginationConfig | undefined =
        hasNotes && totalPages > 1
          ? {
              currentPage: 1,
              totalPages,
              previousButtonId: 'queue:previous',
              nextButtonId: 'queue:next',
            }
          : undefined;

      await QueueRendererV2.render(thread, summaryV2, itemsV2, pagination);

      await interaction.editReply({
        content: `Notes queue posted to ${String(thread)}`,
      });

      logger.info('List notes from button completed successfully', {
        error_id: errorId,
        user_id: userId,
        total_notes: notesResponse.total,
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
