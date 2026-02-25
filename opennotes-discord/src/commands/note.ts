import {
  SlashCommandBuilder,
  ChatInputCommandInteraction,
  ModalBuilder,
  TextInputBuilder,
  TextInputStyle,
  ActionRowBuilder,
  ModalActionRowComponentBuilder,
  MessageFlags,
  ModalSubmitInteraction,
  Message,
  TextBasedChannel,
  User,
  GuildMember,
  PermissionFlagsBits,
  type APIContainerComponent,
} from 'discord.js';
import { serviceProvider } from '../services/index.js';
import { DiscordFormatter } from '../services/DiscordFormatter.js';
import { ConfigKey } from '../lib/config-schema.js';
import { logger } from '../logger.js';
import { generateErrorId, extractErrorDetails, formatErrorForUser, ApiError } from '../lib/errors.js';
import { validateMessageId, parseCustomId, validateNoteId } from '../lib/validation.js';
import { extractAndSanitizeImageUrl } from '../lib/url-validation.js';
import { handleEphemeralError } from '../lib/interaction-utils.js';
import { modalSubmissionRateLimiter } from '../lib/interaction-rate-limiter.js';
import { suppressExpectedDiscordErrors } from '../lib/discord-utils.js';
import { apiClient } from '../api-client.js';
import { extractUserContext } from '../lib/user-context.js';

export const data = new SlashCommandBuilder()
  .setName('note')
  .setDescription('Community notes commands')
  .addSubcommand(subcommand =>
    subcommand
      .setName('write')
      .setDescription('Write a community note for a message')
      .addStringOption(option =>
        option
          .setName('message-id')
          .setDescription('The ID of the message to write a note for')
          .setRequired(true)
      )
  )
  .addSubcommand(subcommand =>
    subcommand
      .setName('request')
      .setDescription('Request a community note for a message')
      .addStringOption(option =>
        option
          .setName('message-id')
          .setDescription('The ID of the message to request a note for')
          .setRequired(true)
      )
      .addStringOption(option =>
        option
          .setName('reason')
          .setDescription('Optional reason for requesting the note')
          .setRequired(false)
      )
  )
  .addSubcommand(subcommand =>
    subcommand
      .setName('view')
      .setDescription('View all community notes for a message')
      .addStringOption(option =>
        option
          .setName('message-id')
          .setDescription('The ID of the message to view notes for')
          .setRequired(true)
      )
  )
  .addSubcommand(subcommand =>
    subcommand
      .setName('score')
      .setDescription('View the score for a specific community note')
      .addStringOption(option =>
        option
          .setName('note-id')
          .setDescription('The ID of the note to view the score for')
          .setRequired(true)
      )
  )
  .addSubcommand(subcommand =>
    subcommand
      .setName('rate')
      .setDescription('Rate a community note as helpful or not helpful')
      .addStringOption(option =>
        option
          .setName('note-id')
          .setDescription('The ID of the note to rate')
          .setRequired(true)
      )
      .addBooleanOption(option =>
        option
          .setName('helpful')
          .setDescription('Is this note helpful?')
          .setRequired(true)
      )
  )
  .addSubcommand(subcommand =>
    subcommand
      .setName('queue-profiled')
      .setDescription('[PROFILING] View all notes awaiting ratings - with performance metrics')
  )
  .addSubcommand(subcommand =>
    subcommand
      .setName('force-publish')
      .setDescription('Force-publish a note (Admin only - overrides automatic publication thresholds)')
      .addStringOption(option =>
        option
          .setName('note-id')
          .setDescription('The ID of the note to force-publish')
          .setRequired(true)
      )
  );

export async function execute(interaction: ChatInputCommandInteraction): Promise<void> {
  const subcommand = interaction.options.getSubcommand();

  switch (subcommand) {
    case 'write':
      await handleWriteSubcommand(interaction);
      break;
    case 'request':
      await handleRequestSubcommand(interaction);
      break;
    case 'view':
      await handleViewSubcommand(interaction);
      break;
    case 'score':
      await handleScoreSubcommand(interaction);
      break;
    case 'rate':
      await handleRateSubcommand(interaction);
      break;
    case 'queue-profiled':
      await handleQueueProfiledSubcommand(interaction);
      break;
    case 'force-publish':
      await handleForcePublishSubcommand(interaction);
      break;
    default:
      await interaction.reply({
        content: 'Unknown subcommand',
        flags: MessageFlags.Ephemeral,
      });
  }
}

async function handleWriteSubcommand(interaction: ChatInputCommandInteraction): Promise<void> {
  const errorId = generateErrorId();
  const messageId = interaction.options.getString('message-id', true);
  const userId = interaction.user.id;
  const guildId = interaction.guildId;

  const validation = validateMessageId(messageId);
  if (!validation.valid) {
    logger.warn('Invalid message ID input validation failed', {
      error_id: errorId,
      user_id: userId,
      guild_id: guildId,
      provided_value: messageId,
      validation_error: validation.error,
      command: 'note write',
    });
    await interaction.reply({
      content: `Invalid message ID: ${validation.error}`,
      flags: MessageFlags.Ephemeral,
    });
    return;
  }

  try {
    logger.info('Executing write-note command', {
      error_id: errorId,
      command: 'note write',
      user_id: userId,
      community_server_id: guildId,
      message_id: messageId,
    });

    const modal = new ModalBuilder()
      .setCustomId(`note-write:${messageId}`)
      .setTitle('Write Community Note');

    const noteInput = new TextInputBuilder()
      .setCustomId('note-content')
      .setLabel('Note Content')
      .setStyle(TextInputStyle.Paragraph)
      .setPlaceholder('Explain what context or correction is needed...')
      .setRequired(true)
      .setMinLength(10)
      .setMaxLength(1000);

    const actionRow = new ActionRowBuilder<ModalActionRowComponentBuilder>().addComponents(noteInput);
    modal.addComponents(actionRow);

    await interaction.showModal(modal);

    logger.debug('Modal shown successfully', {
      error_id: errorId,
      command: 'note write',
      user_id: userId,
      message_id: messageId,
    });
  } catch (error) {
    const errorDetails = extractErrorDetails(error);

    logger.error('Failed to show write-note modal', {
      error_id: errorId,
      command: 'note write',
      user_id: userId,
      community_server_id: guildId,
      message_id: messageId,
      error: errorDetails.message,
      error_type: errorDetails.type,
      stack: errorDetails.stack,
    });

    await interaction.reply({
      content: formatErrorForUser(errorId, 'Failed to open note editor.'),
      flags: MessageFlags.Ephemeral,
    }).catch(suppressExpectedDiscordErrors('reply_after_modal_error'));
  }
}

export async function handleModalSubmit(interaction: ModalSubmitInteraction): Promise<void> {
  const errorId = generateErrorId();
  const userId = interaction.user.id;

  if (modalSubmissionRateLimiter.checkAndRecord(userId)) {
    await interaction.reply({
      content: '⏱️ Please wait a moment before submitting another note.',
      flags: MessageFlags.Ephemeral,
    }).catch(suppressExpectedDiscordErrors('rate_limit_reply'));
    return;
  }

  const parseResult = parseCustomId(interaction.customId, 2);
  if (!parseResult.success || !parseResult.parts) {
    logger.error('Failed to parse customId in note-write modal', {
      error_id: errorId,
      customId: interaction.customId,
      error: parseResult.error,
    });
    await interaction.reply({
      content: 'Invalid interaction data. Please try the command again.',
      flags: MessageFlags.Ephemeral,
    }).catch(suppressExpectedDiscordErrors('invalid_customid_reply'));
    return;
  }

  const messageId = parseResult.parts[1];
  const content = interaction.fields.getTextInputValue('note-content');
  const guildId = interaction.guildId;

  try {
    logger.info('Processing write-note modal submission', {
      error_id: errorId,
      command: 'note write',
      user_id: userId,
      community_server_id: guildId,
      message_id: messageId,
      content_length: content.length,
    });

    let ephemeral = false;
    if (guildId) {
      const configService = serviceProvider.getGuildConfigService();
      ephemeral = await configService.get(guildId, ConfigKey.WRITE_NOTE_EPHEMERAL) as boolean;
    }

    await interaction.deferReply(ephemeral ? { flags: MessageFlags.Ephemeral } : {});

    const userContext = extractUserContext(interaction.user, guildId, undefined, interaction.channelId);
    const writeNoteService = serviceProvider.getWriteNoteService();
    const result = await writeNoteService.execute({
      messageId,
      authorId: userId,
      content,
      channelId: interaction.channelId || undefined,
      guildId: guildId || undefined,
      username: userContext.username,
      displayName: userContext.displayName,
      avatarUrl: userContext.avatarUrl,
    });

    if (!result.success) {
      const errorResponse = DiscordFormatter.formatErrorV2(result);
      if (ephemeral) {
        await interaction.editReply(errorResponse);
      } else {
        await interaction.followUp({ ...errorResponse, flags: MessageFlags.Ephemeral });
        await interaction.deleteReply();
      }
      return;
    }

    const response = DiscordFormatter.formatWriteNoteSuccessV2(
      result.data!,
      messageId,
      guildId || undefined,
      interaction.channelId || undefined
    );
    await interaction.editReply(response);

    logger.info('Write-note completed successfully', {
      error_id: errorId,
      command: 'note write',
      user_id: userId,
      message_id: messageId,
      note_id: result.data?.note.data.id,
    });
  } catch (error) {
    const errorDetails = extractErrorDetails(error);

    logger.error('Unexpected error in write-note modal submission', {
      error_id: errorId,
      command: 'note write',
      user_id: userId,
      community_server_id: guildId,
      message_id: messageId,
      content_length: content.length,
      error: errorDetails.message,
      error_type: errorDetails.type,
      stack: errorDetails.stack,
      ...(error instanceof ApiError && {
        endpoint: error.endpoint,
        status_code: error.statusCode,
        response_body: error.responseBody,
      }),
    });

    const errorMessage = { content: formatErrorForUser(errorId, 'Failed to create note.') };

    await handleEphemeralError(interaction, errorMessage, guildId, errorId, ConfigKey.WRITE_NOTE_EPHEMERAL);
  }
}

export async function createNoteRequest(params: {
  messageId: string;
  message?: Message;
  reason?: string;
  userId: string;
  community_server_id: string;
  channel?: TextBasedChannel | null;
  errorId: string;
  user?: User;
}): Promise<{ success: boolean; response: { components?: APIContainerComponent[]; flags?: number; content?: string } }> {
  const { messageId, message, reason, userId, community_server_id, channel, errorId, user } = params;

  let originalMessageContent: string | undefined;
  let attachmentUrl: string | undefined;
  let attachmentType: 'image' | 'video' | 'file' | undefined;
  let attachmentMetadata: Record<string, unknown> | undefined;
  let embeddedImageUrl: string | undefined;

  const extractImageUrlFromText = (text: string): string | undefined => {
    return extractAndSanitizeImageUrl(text);
  };

  const extractMessageData = (msg: Message): void => {
    originalMessageContent = msg.content || undefined;

    const firstAttachment = msg.attachments.first();
    if (firstAttachment) {
      attachmentUrl = firstAttachment.url;

      if (firstAttachment.contentType?.startsWith('image/')) {
        attachmentType = 'image';
        attachmentMetadata = {
          width: firstAttachment.width,
          height: firstAttachment.height,
          size: firstAttachment.size,
          filename: firstAttachment.name,
        };
      } else if (firstAttachment.contentType?.startsWith('video/')) {
        attachmentType = 'video';
        attachmentMetadata = {
          size: firstAttachment.size,
          filename: firstAttachment.name,
        };
      } else {
        attachmentType = 'file';
        attachmentMetadata = {
          size: firstAttachment.size,
          filename: firstAttachment.name,
        };
      }

      logger.info('Extracted attachment from message', {
        error_id: errorId,
        message_id: messageId,
        attachment_type: attachmentType,
        attachment_url: attachmentUrl,
        has_content: !!originalMessageContent,
      });
    }

    if (!attachmentUrl && msg.embeds.length > 0) {
      const firstEmbed = msg.embeds[0];

      if (firstEmbed.image?.url) {
        embeddedImageUrl = firstEmbed.image.url;
        logger.info('Extracted embed image from message', {
          error_id: errorId,
          message_id: messageId,
          embedded_image_url: embeddedImageUrl,
        });
      } else if (firstEmbed.thumbnail?.url) {
        embeddedImageUrl = firstEmbed.thumbnail.url;
        logger.info('Extracted embed thumbnail from message', {
          error_id: errorId,
          message_id: messageId,
          embedded_image_url: embeddedImageUrl,
        });
      }
    }

    if (!attachmentUrl && !embeddedImageUrl && originalMessageContent) {
      const textImageUrl = extractImageUrlFromText(originalMessageContent);
      if (textImageUrl) {
        embeddedImageUrl = textImageUrl;
        logger.info('Extracted image URL from message text', {
          error_id: errorId,
          message_id: messageId,
          embedded_image_url: embeddedImageUrl,
        });
      }
    }
  };

  if (message) {
    extractMessageData(message);
  } else if (channel?.isTextBased()) {
    try {
      const fetchedMessage = await channel.messages.fetch(messageId);
      if (fetchedMessage) {
        extractMessageData(fetchedMessage);
      }
    } catch (fetchError) {
      logger.warn('Failed to fetch original message content for request', {
        error_id: errorId,
        message_id: messageId,
        error: fetchError instanceof Error ? fetchError.message : String(fetchError),
      });
    }
  }

  const userContext = user ? extractUserContext(user, community_server_id, undefined, channel?.id) : undefined;
  const requestNoteService = serviceProvider.getRequestNoteService();
  const result = await requestNoteService.execute({
    messageId,
    userId,
    community_server_id,
    channelId: channel?.id,
    reason,
    originalMessageContent,
    attachmentUrl,
    attachmentType,
    attachmentMetadata,
    embeddedImageUrl,
    username: userContext?.username,
    displayName: userContext?.displayName,
    avatarUrl: userContext?.avatarUrl,
  });

  if (!result.success) {
    return {
      success: false,
      response: DiscordFormatter.formatErrorV2(result),
    };
  }

  return {
    success: true,
    response: DiscordFormatter.formatRequestNoteSuccessV2(
      messageId,
      userId,
      reason,
      community_server_id,
      channel?.id
    ),
  };
}

async function handleRequestSubcommand(interaction: ChatInputCommandInteraction): Promise<void> {
  const errorId = generateErrorId();
  const messageId = interaction.options.getString('message-id', true);
  const reason = interaction.options.getString('reason') || undefined;
  const userId = interaction.user.id;
  const guildId = interaction.guildId;

  const validation = validateMessageId(messageId);
  if (!validation.valid) {
    logger.warn('Invalid message ID input validation failed', {
      error_id: errorId,
      user_id: userId,
      guild_id: guildId,
      provided_value: messageId,
      validation_error: validation.error,
      command: 'note request',
    });
    await interaction.reply({
      content: `Invalid message ID: ${validation.error}`,
      flags: MessageFlags.Ephemeral,
    });
    return;
  }

  try {
    logger.info('Executing request-note command', {
      error_id: errorId,
      command: 'note request',
      user_id: userId,
      community_server_id: guildId,
      message_id: messageId,
      has_reason: !!reason,
    });

    let ephemeral = false;
    if (guildId) {
      const configService = serviceProvider.getGuildConfigService();
      ephemeral = await configService.get(guildId, ConfigKey.REQUEST_NOTE_EPHEMERAL) as boolean;
    }

    await interaction.deferReply(ephemeral ? { flags: MessageFlags.Ephemeral } : {});

    if (!guildId) {
      logger.error('Missing guild ID for note request', { error_id: errorId, user_id: userId });
      await interaction.editReply({
        content: '❌ This command can only be used in a server, not in DMs.',
      });
      return;
    }

    const result = await createNoteRequest({
      messageId,
      reason,
      userId,
      community_server_id: guildId,
      channel: interaction.channel,
      errorId,
      user: interaction.user,
    });

    if (!result.success) {
      if (ephemeral) {
        await interaction.editReply(result.response);
      } else {
        await interaction.followUp(result.response);
        await interaction.deleteReply();
      }
      return;
    }

    await interaction.editReply(result.response);

    logger.info('Request-note completed successfully', {
      error_id: errorId,
      command: 'note request',
      user_id: userId,
      message_id: messageId,
    });
  } catch (error) {
    const errorDetails = extractErrorDetails(error);

    logger.error('Unexpected error in request-note command', {
      error_id: errorId,
      command: 'note request',
      user_id: userId,
      community_server_id: guildId,
      message_id: messageId,
      has_reason: !!reason,
      error: errorDetails.message,
      error_type: errorDetails.type,
      stack: errorDetails.stack,
      ...(error instanceof ApiError && {
        endpoint: error.endpoint,
        status_code: error.statusCode,
        response_body: error.responseBody,
      }),
    });

    const errorMessage = { content: formatErrorForUser(errorId, 'Failed to create note request.') };

    await handleEphemeralError(interaction, errorMessage, guildId, errorId, ConfigKey.REQUEST_NOTE_EPHEMERAL);
  }
}

async function handleViewSubcommand(interaction: ChatInputCommandInteraction): Promise<void> {
  const errorId = generateErrorId();
  const messageId = interaction.options.getString('message-id', true);
  const userId = interaction.user.id;
  const guildId = interaction.guildId;

  const validation = validateMessageId(messageId);
  if (!validation.valid) {
    logger.warn('Invalid message ID input validation failed', {
      error_id: errorId,
      user_id: userId,
      guild_id: guildId,
      provided_value: messageId,
      validation_error: validation.error,
      command: 'note view',
    });
    await interaction.reply({
      content: `Invalid message ID: ${validation.error}`,
      flags: MessageFlags.Ephemeral,
    });
    return;
  }

  try {
    logger.info('Executing view-notes command', {
      error_id: errorId,
      command: 'note view',
      user_id: userId,
      community_server_id: guildId,
      message_id: messageId,
    });

    await interaction.deferReply();

    const viewNotesService = serviceProvider.getViewNotesService();
    const scoringService = serviceProvider.getScoringService();

    const result = await viewNotesService.execute({ messageId }, userId);

    if (!result.success) {
      const errorResponse = DiscordFormatter.formatErrorV2(result);
      await interaction.followUp({ ...errorResponse, flags: MessageFlags.Ephemeral });
      await interaction.deleteReply();
      return;
    }

    if (result.data!.notes.data.length === 0) {
      await interaction.editReply({
        content: 'No community notes found for this message.',
      });
      return;
    }

    const noteIds = result.data!.notes.data.map(note => note.id);
    const batchScoresResult = await scoringService.getBatchNoteScores(noteIds);

    const scoresMap = new Map();
    if (batchScoresResult.success && batchScoresResult.data) {
      for (const resource of batchScoresResult.data.data) {
        scoresMap.set(resource.id, resource.attributes);
      }
    }

    const response = DiscordFormatter.formatViewNotesSuccessV2(result.data!, scoresMap);
    await interaction.editReply(response);

    logger.info('View-notes completed successfully', {
      error_id: errorId,
      command: 'note view',
      user_id: userId,
      message_id: messageId,
      note_count: result.data!.notes.data.length,
    });
  } catch (error) {
    const errorDetails = extractErrorDetails(error);

    logger.error('Unexpected error in view-notes command', {
      error_id: errorId,
      command: 'note view',
      user_id: userId,
      community_server_id: guildId,
      message_id: messageId,
      error: errorDetails.message,
      error_type: errorDetails.type,
      stack: errorDetails.stack,
      ...(error instanceof ApiError && {
        endpoint: error.endpoint,
        status_code: error.statusCode,
        response_body: error.responseBody,
      }),
    });

    await interaction.followUp({
      content: formatErrorForUser(errorId, 'Failed to retrieve notes for this message.'),
      flags: MessageFlags.Ephemeral,
    }).catch(suppressExpectedDiscordErrors('followup_view_notes_error'));
    await interaction.deleteReply().catch(suppressExpectedDiscordErrors('delete_original_reply'));
  }
}

async function handleScoreSubcommand(interaction: ChatInputCommandInteraction): Promise<void> {
  const errorId = generateErrorId();
  const noteId = interaction.options.getString('note-id', true);
  const userId = interaction.user.id;
  const guildId = interaction.guildId;

  const validation = validateNoteId(noteId);
  if (!validation.valid) {
    logger.warn('Invalid note ID input validation failed', {
      error_id: errorId,
      user_id: userId,
      guild_id: guildId,
      provided_value: noteId,
      validation_error: validation.error,
      command: 'note score',
    });
    await interaction.reply({
      content: `Invalid note ID: ${validation.error}`,
      flags: MessageFlags.Ephemeral,
    });
    return;
  }

  try {
    logger.info('Executing note-score command', {
      error_id: errorId,
      command: 'note score',
      user_id: userId,
      community_server_id: guildId,
      note_id: noteId,
    });

    await interaction.deferReply();

    const scoringService = serviceProvider.getScoringService();
    const result = await scoringService.getNoteScore(noteId);

    if (!result.success) {
      let errorMessage: string;

      switch (result.error?.code) {
        case 'NOT_FOUND':
          errorMessage = `Note with ID \`${noteId}\` not found or score not available yet.`;
          break;
        case 'SCORE_PENDING':
          errorMessage = `Score calculation for note \`${noteId}\` is in progress. Please try again in a moment.`;
          break;
        case 'SERVICE_UNAVAILABLE':
          errorMessage = 'The scoring system is temporarily unavailable. Please try again later.';
          break;
        case 'VALIDATION_ERROR':
          errorMessage = `Invalid note ID format: \`${noteId}\`. Note ID must be a number.`;
          break;
        default:
          errorMessage = `Failed to retrieve score for note \`${noteId}\`. Please try again later.`;
      }

      await interaction.followUp({
        content: errorMessage,
        flags: MessageFlags.Ephemeral,
      });
      await interaction.deleteReply().catch(suppressExpectedDiscordErrors('delete_after_service_error'));
      return;
    }

    const response = DiscordFormatter.formatNoteScoreV2(result.data!);
    await interaction.editReply(response);

    logger.info('Note score retrieved successfully', {
      error_id: errorId,
      command: 'note score',
      user_id: userId,
      note_id: noteId,
      score: result.data!.data.attributes.score,
      confidence: result.data!.data.attributes.confidence,
    });
  } catch (error) {
    const errorDetails = extractErrorDetails(error);

    logger.error('Unexpected error in note-score command', {
      error_id: errorId,
      command: 'note score',
      user_id: userId,
      community_server_id: guildId,
      note_id: noteId,
      error: errorDetails.message,
      error_type: errorDetails.type,
      stack: errorDetails.stack,
    });

    await interaction.followUp({
      content: formatErrorForUser(errorId, `Failed to retrieve score for note \`${noteId}\`.`),
      flags: MessageFlags.Ephemeral,
    }).catch(suppressExpectedDiscordErrors('followup_score_error'));
    await interaction.deleteReply().catch(suppressExpectedDiscordErrors('delete_original_reply'));
  }
}

async function handleRateSubcommand(interaction: ChatInputCommandInteraction): Promise<void> {
  const errorId = generateErrorId();
  const noteId = interaction.options.getString('note-id', true);
  const helpful = interaction.options.getBoolean('helpful', true);
  const userId = interaction.user.id;
  const guildId = interaction.guildId;

  const validation = validateNoteId(noteId);
  if (!validation.valid) {
    logger.warn('Invalid note ID input validation failed', {
      error_id: errorId,
      user_id: userId,
      guild_id: guildId,
      provided_value: noteId,
      validation_error: validation.error,
      command: 'note rate',
    });
    await interaction.reply({
      content: `Invalid note ID: ${validation.error}`,
      flags: MessageFlags.Ephemeral,
    });
    return;
  }

  try {
    logger.info('Executing rate-note command', {
      error_id: errorId,
      command: 'note rate',
      user_id: userId,
      community_server_id: guildId,
      note_id: noteId,
      helpful,
    });

    let ephemeral = false;
    if (guildId) {
      const configService = serviceProvider.getGuildConfigService();
      ephemeral = await configService.get(guildId, ConfigKey.RATE_NOTE_EPHEMERAL) as boolean;
    }

    await interaction.deferReply(ephemeral ? { flags: MessageFlags.Ephemeral } : {});

    const userContext = extractUserContext(interaction.user, guildId, undefined, interaction.channelId);
    const rateNoteService = serviceProvider.getRateNoteService();
    const result = await rateNoteService.execute({
      noteId,
      userId,
      helpful,
      username: userContext.username,
      displayName: userContext.displayName,
      avatarUrl: userContext.avatarUrl,
      guildId: userContext.guildId,
      channelId: userContext.channelId,
    });

    if (!result.success) {
      const errorResponse = DiscordFormatter.formatErrorV2(result);
      if (ephemeral) {
        await interaction.editReply(errorResponse);
      } else {
        await interaction.followUp({ ...errorResponse, flags: MessageFlags.Ephemeral });
        await interaction.deleteReply();
      }
      return;
    }

    const response = DiscordFormatter.formatRateNoteSuccessV2(result.data!, noteId, helpful);
    await interaction.editReply(response);

    logger.info('Rate-note completed successfully', {
      error_id: errorId,
      command: 'note rate',
      user_id: userId,
      note_id: noteId,
      helpful,
    });
  } catch (error) {
    const errorDetails = extractErrorDetails(error);

    logger.error('Unexpected error in rate-note command', {
      error_id: errorId,
      command: 'note rate',
      user_id: userId,
      community_server_id: guildId,
      note_id: noteId,
      helpful,
      error: errorDetails.message,
      error_type: errorDetails.type,
      stack: errorDetails.stack,
      ...(error instanceof ApiError && {
        endpoint: error.endpoint,
        status_code: error.statusCode,
        response_body: error.responseBody,
      }),
    });

    const errorMessage = { content: formatErrorForUser(errorId, 'Failed to rate note.') };

    await handleEphemeralError(interaction, errorMessage, guildId, errorId, ConfigKey.RATE_NOTE_EPHEMERAL);
  }
}

async function handleQueueProfiledSubcommand(interaction: ChatInputCommandInteraction): Promise<void> {
  const errorId = generateErrorId();
  await interaction.reply({
    content: '⚠️ The profiled queue command has been temporarily disabled during the slash command refactoring. It will be restored in a future update.',
    flags: MessageFlags.Ephemeral,
  });
  logger.info('note-queue-profiled subcommand accessed (disabled)', {
    error_id: errorId,
    command: 'note queue-profiled',
    user_id: interaction.user.id,
  });
}

async function handleForcePublishSubcommand(interaction: ChatInputCommandInteraction): Promise<void> {
  const errorId = generateErrorId();
  const noteIdStr = interaction.options.getString('note-id', true);
  const userId = interaction.user.id;
  const guildId = interaction.guildId;

  const validation = validateNoteId(noteIdStr);
  if (!validation.valid) {
    logger.warn('Invalid note ID input validation failed', {
      error_id: errorId,
      user_id: userId,
      guild_id: guildId,
      provided_value: noteIdStr,
      validation_error: validation.error,
      command: 'note force-publish',
    });
    await interaction.reply({
      content: `Invalid note ID: ${validation.error}`,
      flags: MessageFlags.Ephemeral,
    });
    return;
  }

  if (!guildId) {
    await interaction.reply({
      content: 'This command can only be used in a server.',
      flags: MessageFlags.Ephemeral,
    });
    return;
  }

  const member = interaction.member as GuildMember | null;

  try {
    logger.info('Executing note-force-publish command', {
      error_id: errorId,
      command: 'note force-publish',
      user_id: userId,
      community_server_id: guildId,
      note_id: noteIdStr,
      has_manage_server: member?.permissions.has(PermissionFlagsBits.ManageGuild) ?? false,
    });

    await interaction.deferReply({ flags: MessageFlags.Ephemeral });

    const userContext = extractUserContext(interaction.user, guildId, member, interaction.channelId);
    const note = await apiClient.forcePublishNote(noteIdStr, userContext);

    const attrs = note.data.attributes;
    logger.info('Note force-published successfully', {
      error_id: errorId,
      command: 'note force-publish',
      user_id: userId,
      community_server_id: guildId,
      note_id: noteIdStr,
      force_published_at: attrs.force_published_at,
    });

    await interaction.editReply({
      content: `✅ **Note #${noteIdStr} has been force-published**\n\n` +
               `⚠️ This note was manually published by an admin and will be marked as "Admin Published" when displayed.\n\n` +
               `**Note Summary:** ${attrs.summary.substring(0, 200)}${attrs.summary.length > 200 ? '...' : ''}\n` +
               `**Status:** ${attrs.status}\n` +
               `**Published At:** <t:${Math.floor(new Date(attrs.force_published_at ?? attrs.updated_at ?? attrs.created_at ?? new Date().toISOString()).getTime() / 1000)}:F>`,
    });
  } catch (error) {
    const errorDetails = extractErrorDetails(error);

    let errorMessage: string;
    if (error instanceof ApiError) {
      switch (error.statusCode) {
        case 403:
          errorMessage = `❌ **Permission Denied**\n\nYou need either:\n• Discord "Manage Server" permission, OR\n• Open Notes admin role for this server\n\nOnly admins can force-publish notes. Ask a server admin for help.`;
          break;
        case 404:
          errorMessage = `❌ **Note Not Found**\n\nNote with ID \`${noteIdStr}\` does not exist or could not be found.`;
          break;
        case 400: {
          const detail = typeof error.responseBody === 'object' && error.responseBody !== null && 'detail' in error.responseBody
            ? (error.responseBody as Record<string, unknown>).detail
            : undefined;
          errorMessage = `❌ **Invalid Request**\n\n${typeof detail === 'string' ? detail : 'This note cannot be force-published. It may already be published or may have other validation issues.'}`;
          break;
        }
        default:
          errorMessage = formatErrorForUser(errorId, `Failed to force-publish note \`${noteIdStr}\`.`);
      }
    } else {
      errorMessage = formatErrorForUser(errorId, `Failed to force-publish note \`${noteIdStr}\`.`);
    }

    logger.error('Error in note-force-publish command', {
      error_id: errorId,
      command: 'note force-publish',
      user_id: userId,
      community_server_id: guildId,
      note_id: noteIdStr,
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
      content: errorMessage,
    });
  }
}
