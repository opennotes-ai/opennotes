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
import { logger } from '../logger.js';
import { cache } from '../cache.js';
import { generateErrorId, extractErrorDetails, formatErrorForUser } from '../lib/errors.js';
import { hasManageGuildPermission } from '../lib/permissions.js';
import { apiClient } from '../api-client.js';

interface ClearConfirmationState {
  type: 'requests' | 'notes';
  mode: string;
  communityServerId: string;
  guildId: string;
  userId: string;
  wouldDeleteCount: number;
}

const CONFIRMATION_STATE_TTL = 300;

export const data = new SlashCommandBuilder()
  .setName('clear')
  .setDescription('Clear old data from your community (Admin only)')
  .addSubcommand(subcommand =>
    subcommand
      .setName('requests')
      .setDescription('Clear note requests')
      .addStringOption(option =>
        option
          .setName('mode')
          .setDescription("'all' or number of days (e.g., '30')")
          .setRequired(true)
      )
  )
  .addSubcommand(subcommand =>
    subcommand
      .setName('notes')
      .setDescription('Clear unpublished notes only')
      .addStringOption(option =>
        option
          .setName('mode')
          .setDescription("'all' or number of days (e.g., '30')")
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

  const subcommand = interaction.options.getSubcommand() as 'requests' | 'notes';
  const mode = interaction.options.getString('mode', true);

  if (!validateMode(mode)) {
    await interaction.reply({
      content: "Invalid mode. Please use 'all' or a positive number of days (e.g., '30').",
      flags: MessageFlags.Ephemeral,
    });
    return;
  }

  logger.info('Clear command initiated', {
    error_id: errorId,
    command: 'clear',
    subcommand,
    mode,
    user_id: userId,
    guild_id: guildId,
    guild_name: guild.name,
  });

  await interaction.deferReply({
    flags: MessageFlags.Ephemeral,
  });

  try {
    const communityServer = await apiClient.getCommunityServerByPlatformId(guildId);
    const communityServerId = communityServer.data.id;

    const previewResult = await getClearPreview(communityServerId, subcommand, mode);

    if (previewResult.wouldDeleteCount === 0) {
      const itemType = subcommand === 'requests' ? 'requests' : 'unpublished notes';
      const message = mode.toLowerCase() === 'all'
        ? `No ${itemType} found to delete.`
        : `No ${itemType} older than ${mode} days found to delete.`;

      await interaction.editReply({
        content: message,
      });
      return;
    }

    await showConfirmationPrompt(
      interaction,
      subcommand,
      mode,
      communityServerId,
      guildId,
      userId,
      previewResult.wouldDeleteCount
    );
  } catch (error) {
    const errorDetails = extractErrorDetails(error);

    logger.error('Clear command failed', {
      error_id: errorId,
      command: 'clear',
      subcommand,
      mode,
      user_id: userId,
      guild_id: guildId,
      error: errorDetails.message,
      error_type: errorDetails.type,
      stack: errorDetails.stack,
    });

    await interaction.editReply({
      content: formatErrorForUser(errorId, 'Failed to process clear request. Please try again later.'),
    });
  }
}

function validateMode(mode: string): boolean {
  if (mode.toLowerCase() === 'all') {
    return true;
  }

  const days = parseInt(mode, 10);
  return !isNaN(days) && days > 0;
}

interface ClearPreviewResult {
  wouldDeleteCount: number;
  message: string;
}

async function getClearPreview(
  communityServerId: string,
  type: 'requests' | 'notes',
  mode: string
): Promise<ClearPreviewResult> {
  const endpoint = type === 'requests'
    ? `/api/v2/community-servers/${communityServerId}/clear-requests/preview?mode=${encodeURIComponent(mode)}`
    : `/api/v2/community-servers/${communityServerId}/clear-notes/preview?mode=${encodeURIComponent(mode)}`;

  return await apiClient.getClearPreview(endpoint);
}

async function executeClear(
  communityServerId: string,
  type: 'requests' | 'notes',
  mode: string
): Promise<{ deletedCount: number; message: string }> {
  const endpoint = type === 'requests'
    ? `/api/v2/community-servers/${communityServerId}/clear-requests?mode=${encodeURIComponent(mode)}`
    : `/api/v2/community-servers/${communityServerId}/clear-notes?mode=${encodeURIComponent(mode)}`;

  return await apiClient.executeClear(endpoint);
}

async function showConfirmationPrompt(
  interaction: ChatInputCommandInteraction,
  type: 'requests' | 'notes',
  mode: string,
  communityServerId: string,
  guildId: string,
  userId: string,
  wouldDeleteCount: number
): Promise<void> {
  const stateId = nanoid(8);

  const state: ClearConfirmationState = {
    type,
    mode,
    communityServerId,
    guildId,
    userId,
    wouldDeleteCount,
  };

  await cache.set(`clear:confirmation:${stateId}`, state, CONFIRMATION_STATE_TTL);

  const itemType = type === 'requests' ? 'requests' : 'unpublished notes';
  const modeDescription = mode.toLowerCase() === 'all'
    ? 'all'
    : `older than ${mode} days`;

  const warningMessage = type === 'notes'
    ? '\n\n**Note:** Only unpublished notes (NEEDS_MORE_RATINGS) will be deleted. Published and force-published notes are preserved.'
    : '';

  const confirmButton = new ButtonBuilder()
    .setCustomId(`clear_confirm:${stateId}`)
    .setLabel(`Delete ${wouldDeleteCount} ${itemType}`)
    .setStyle(ButtonStyle.Danger);

  const cancelButton = new ButtonBuilder()
    .setCustomId(`clear_cancel:${stateId}`)
    .setLabel('Cancel')
    .setStyle(ButtonStyle.Secondary);

  const row = new ActionRowBuilder<ButtonBuilder>().addComponents(confirmButton, cancelButton);

  await interaction.editReply({
    content: `**Warning:** This will permanently delete **${wouldDeleteCount}** ${itemType} (${modeDescription}).${warningMessage}\n\nAre you sure you want to proceed?`,
    components: [row],
  });

  const reply = await interaction.fetchReply();

  const collector = reply.createMessageComponentCollector({
    componentType: ComponentType.Button,
    time: 60000,
    filter: (i) => i.user.id === userId && i.customId.startsWith('clear_'),
  });

  collector.on('collect', (buttonInteraction: ButtonInteraction) => {
    void handleConfirmationButton(buttonInteraction, stateId, collector);
  });

  collector.on('end', (_collected, reason) => {
    if (reason === 'time') {
      interaction.editReply({
        content: 'Confirmation timed out. Please run the command again if you still want to proceed.',
        components: [],
      }).catch(() => {
        /* Silently ignore - interaction may have expired */
      });
    }
  });
}

async function handleConfirmationButton(
  buttonInteraction: ButtonInteraction,
  stateId: string,
  collector: { stop: () => void }
): Promise<void> {
  const customId = buttonInteraction.customId;
  const [action, buttonStateId] = customId.split(':');

  if (buttonStateId !== stateId) {
    return;
  }

  const state = await cache.get<ClearConfirmationState>(`clear:confirmation:${stateId}`);

  if (!state) {
    await buttonInteraction.update({
      content: 'Session expired. Please run the command again.',
      components: [],
    });
    collector.stop();
    return;
  }

  if (action === 'clear_cancel') {
    await buttonInteraction.update({
      content: 'Clear operation cancelled.',
      components: [],
    });
    collector.stop();
    return;
  }

  if (action === 'clear_confirm') {
    await buttonInteraction.deferUpdate();

    try {
      const result = await executeClear(state.communityServerId, state.type, state.mode);

      const itemType = state.type === 'requests' ? 'requests' : 'unpublished notes';

      logger.info('Clear operation completed', {
        type: state.type,
        mode: state.mode,
        deleted_count: result.deletedCount,
        user_id: state.userId,
        guild_id: state.guildId,
        community_server_id: state.communityServerId,
      });

      await buttonInteraction.editReply({
        content: `Successfully deleted **${result.deletedCount}** ${itemType}.`,
        components: [],
      });
    } catch (error) {
      const errorId = generateErrorId();
      const errorDetails = extractErrorDetails(error);

      logger.error('Clear operation failed', {
        error_id: errorId,
        type: state.type,
        mode: state.mode,
        user_id: state.userId,
        guild_id: state.guildId,
        community_server_id: state.communityServerId,
        error: errorDetails.message,
        error_type: errorDetails.type,
        stack: errorDetails.stack,
      });

      await buttonInteraction.editReply({
        content: formatErrorForUser(errorId, 'Failed to complete the clear operation. Please try again later.'),
        components: [],
      });
    }

    collector.stop();
  }
}
