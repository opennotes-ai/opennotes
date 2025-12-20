import {
  SlashCommandBuilder,
  ChatInputCommandInteraction,
  MessageFlags,
  InteractionContextType,
  ChannelType,
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
  ComponentType,
  ContainerBuilder,
  TextDisplayBuilder,
  SectionBuilder,
} from 'discord.js';
import { apiClient } from '../api-client.js';
import { GuildConfigService } from '../services/GuildConfigService.js';
import { GuildSetupService } from '../services/GuildSetupService.js';
import { NotePublisherConfigService } from '../services/NotePublisherConfigService.js';
import { BotChannelService } from '../services/BotChannelService.js';
import { GuildOnboardingService } from '../services/GuildOnboardingService.js';
import { ConfigKey, ConfigValidator, CONFIG_SCHEMA } from '../lib/config-schema.js';
import { parseCustomId } from '../lib/validation.js';
import { buttonInteractionRateLimiter } from '../lib/interaction-rate-limiter.js';
import { TIMEOUTS } from '../lib/constants.js';
import { logger } from '../logger.js';
import { generateErrorId, extractErrorDetails, formatErrorForUser, ApiError } from '../lib/errors.js';
import { config } from '../config.js';
import { v2MessageFlags, V2_COLORS, createDivider, createSmallSeparator } from '../utils/v2-components.js';
import { resolveCommunityServerId } from '../lib/community-server-resolver.js';

const configService = new GuildConfigService(apiClient);
const guildSetupService = new GuildSetupService();
const notePublisherConfigService = new NotePublisherConfigService();
const botChannelService = new BotChannelService();
const guildOnboardingService = new GuildOnboardingService();

export const data = new SlashCommandBuilder()
  .setName('config')
  .setDescription('Configure Open Notes settings for this server')
  .setContexts(InteractionContextType.Guild)
  .addSubcommandGroup(group =>
    group
      .setName('admin')
      .setDescription('Manage Open Notes admins for this server')
      .addSubcommand(subcommand =>
        subcommand
          .setName('set')
          .setDescription('Add a user as Open Notes admin for this server')
          .addUserOption(option =>
            option
              .setName('user')
              .setDescription('User to promote to admin')
              .setRequired(true)
          )
      )
      .addSubcommand(subcommand =>
        subcommand
          .setName('remove')
          .setDescription('Remove Open Notes admin status from a user')
          .addUserOption(option =>
            option
              .setName('user')
              .setDescription('User to demote from admin')
              .setRequired(true)
          )
      )
      .addSubcommand(subcommand =>
        subcommand
          .setName('list')
          .setDescription('List all Open Notes admins for this server')
      )
  )
  .addSubcommandGroup(group =>
    group
      .setName('llm')
      .setDescription('Configure LLM provider for AI-powered features')
      .addSubcommand(subcommand =>
        subcommand
          .setName('set')
          .setDescription('Configure LLM provider API key')
          .addStringOption(option =>
            option
              .setName('provider')
              .setDescription('LLM provider (OpenAI or Anthropic)')
              .setRequired(true)
              .addChoices(
                { name: 'OpenAI', value: 'openai' },
                { name: 'Anthropic', value: 'anthropic' }
              )
          )
          .addStringOption(option =>
            option
              .setName('api_key')
              .setDescription('Your API key (will be encrypted and stored securely)')
              .setRequired(true)
          )
          .addBooleanOption(option =>
            option
              .setName('test_connection')
              .setDescription('Test the API key before saving (recommended)')
              .setRequired(false)
          )
      )
  )
  .addSubcommandGroup(group =>
    group
      .setName('opennotes')
      .setDescription('Configure Open Notes platform settings')
      .addSubcommand(subcommand =>
        subcommand
          .setName('view')
          .setDescription('View current server configuration')
      )
      .addSubcommand(subcommand =>
        subcommand
          .setName('set')
          .setDescription('Update a configuration setting')
          .addStringOption(option =>
            option
              .setName('key')
              .setDescription('Configuration key to update')
              .setRequired(true)
              .addChoices(
                ...Object.keys(CONFIG_SCHEMA).map(key => ({
                  name: CONFIG_SCHEMA[key as ConfigKey].description,
                  value: key,
                }))
              )
          )
          .addStringOption(option =>
            option
              .setName('value')
              .setDescription('New value for the configuration')
              .setRequired(true)
          )
      )
      .addSubcommand(subcommand =>
        subcommand
          .setName('reset')
          .setDescription('Reset configuration to defaults')
          .addStringOption(option =>
            option
              .setName('key')
              .setDescription('Configuration key to reset (leave empty to reset all)')
              .setRequired(false)
              .addChoices(
                ...Object.keys(CONFIG_SCHEMA).map(key => ({
                  name: CONFIG_SCHEMA[key as ConfigKey].description,
                  value: key,
                }))
              )
          )
      )
  )
  .addSubcommandGroup(group =>
    group
      .setName('content-monitor')
      .setDescription('Configure content monitoring for channels')
      .addSubcommand(subcommand =>
        subcommand
          .setName('enable')
          .setDescription('Enable content monitoring for a specific channel')
          .addChannelOption(option =>
            option
              .setName('channel')
              .setDescription('The channel to enable monitoring for')
              .setRequired(true)
              .addChannelTypes(ChannelType.GuildText, ChannelType.GuildNews)
          )
      )
      .addSubcommand(subcommand =>
        subcommand
          .setName('disable')
          .setDescription('Disable content monitoring for a specific channel')
          .addChannelOption(option =>
            option
              .setName('channel')
              .setDescription('The channel to disable monitoring for')
              .setRequired(true)
              .addChannelTypes(ChannelType.GuildText, ChannelType.GuildNews)
          )
      )
      .addSubcommand(subcommand =>
        subcommand
          .setName('enable-all')
          .setDescription('Enable content monitoring for all text channels in this server')
      )
  )
  .addSubcommandGroup(group =>
    group
      .setName('note-publisher')
      .setDescription('Configure automatic posting of high-quality notes')
      .addSubcommand(subcommand =>
        subcommand
          .setName('enable')
          .setDescription('Enable note-publishering for this server')
      )
      .addSubcommand(subcommand =>
        subcommand
          .setName('disable')
          .setDescription('Disable note-publishering for this server')
      )
      .addSubcommand(subcommand =>
        subcommand
          .setName('threshold')
          .setDescription('Set the score threshold for note-publishering')
          .addNumberOption(option =>
            option
              .setName('value')
              .setDescription('Threshold value (0.0-1.0, default 0.7)')
              .setRequired(true)
              .setMinValue(0)
              .setMaxValue(1)
          )
      )
      .addSubcommand(subcommand =>
        subcommand
          .setName('enable-channel')
          .setDescription('Enable note-publishering in a specific channel')
          .addChannelOption(option =>
            option
              .setName('channel')
              .setDescription('The channel to enable')
              .setRequired(true)
              .addChannelTypes(ChannelType.GuildText, ChannelType.GuildNews)
          )
      )
      .addSubcommand(subcommand =>
        subcommand
          .setName('disable-channel')
          .setDescription('Disable note-publishering in a specific channel')
          .addChannelOption(option =>
            option
              .setName('channel')
              .setDescription('The channel to disable')
              .setRequired(true)
              .addChannelTypes(ChannelType.GuildText, ChannelType.GuildNews)
          )
      )
      .addSubcommand(subcommand =>
        subcommand
          .setName('status')
          .setDescription('View current note-publisher configuration')
          .addChannelOption(option =>
            option
              .setName('channel')
              .setDescription('Check configuration for a specific channel (optional)')
              .setRequired(false)
              .addChannelTypes(ChannelType.GuildText, ChannelType.GuildNews)
          )
      )
  );

export async function execute(interaction: ChatInputCommandInteraction): Promise<void> {
  const errorId = generateErrorId();
  const userId = interaction.user.id;
  const guildId = interaction.guildId;

  try {
    const group = interaction.options.getSubcommandGroup();
    const subcommand = interaction.options.getSubcommand();

    logger.info('Executing config command', {
      error_id: errorId,
      command: 'config',
      group,
      subcommand,
      user_id: userId,
      community_server_id: guildId,
    });

    await interaction.deferReply({ flags: v2MessageFlags({ ephemeral: true }) });

    if (!guildId) {
      await interaction.editReply({
        content: 'This command can only be used in a server.',
      });
      return;
    }

    switch (group) {
      case 'admin':
        await handleAdminSubcommands(interaction, guildId, subcommand, errorId);
        break;
      case 'llm':
        await handleLlmSubcommands(interaction, guildId, subcommand, errorId);
        break;
      case 'opennotes':
        await handleOpennotesSubcommands(interaction, guildId, subcommand, errorId);
        break;
      case 'content-monitor':
        await handleContentMonitorSubcommands(interaction, guildId, subcommand, errorId);
        break;
      case 'note-publisher':
        await handleNotePublisherSubcommands(interaction, guildId, subcommand, errorId);
        break;
      default:
        await interaction.editReply({
          content: 'Unknown configuration type.',
        });
    }

    logger.info('Config command completed successfully', {
      error_id: errorId,
      command: 'config',
      group,
      subcommand,
      user_id: userId,
      community_server_id: guildId,
    });
  } catch (error) {
    const errorDetails = extractErrorDetails(error);

    logger.error('Error in config command', {
      error_id: errorId,
      command: 'config',
      user_id: userId,
      community_server_id: guildId,
      error: errorDetails?.message || 'Unknown error',
      error_type: errorDetails?.type || 'Unknown',
      stack: errorDetails?.stack || '',
      ...(error instanceof ApiError && {
        endpoint: error.endpoint,
        status_code: error.statusCode,
        response_body: error.responseBody,
      }),
    });

    await interaction.editReply({
      content: formatErrorForUser(errorId, 'Failed to process configuration command.'),
    });
  }
}

async function handleAdminSubcommands(
  interaction: ChatInputCommandInteraction,
  guildId: string,
  subcommand: string,
  errorId: string
): Promise<void> {
  switch (subcommand) {
    case 'set':
      await handleAdminSet(interaction, guildId, errorId);
      break;
    case 'remove':
      await handleAdminRemove(interaction, guildId, errorId);
      break;
    case 'list':
      await handleAdminList(interaction, guildId, errorId);
      break;
    default:
      await interaction.editReply({
        content: 'Unknown subcommand.',
      });
  }
}

async function handleAdminSet(
  interaction: ChatInputCommandInteraction,
  guildId: string,
  errorId: string
): Promise<void> {
  const user = interaction.options.getUser('user', true);

  try {
    const adminResponse = await apiClient.addCommunityAdmin(guildId, user.id, {
      username: user.username,
      display_name: user.displayName || user.username,
      avatar_url: user.displayAvatarURL({ size: 256 }),
    });

    const container = new ContainerBuilder()
      .setAccentColor(V2_COLORS.HELPFUL)
      .addTextDisplayComponents(
        new TextDisplayBuilder().setContent('## Admin Added')
      )
      .addSeparatorComponents(createSmallSeparator())
      .addTextDisplayComponents(
        new TextDisplayBuilder().setContent(
          `Successfully added ${user.tag} as an Open Notes admin for this server.`
        )
      )
      .addSeparatorComponents(createSmallSeparator())
      .addTextDisplayComponents(
        new TextDisplayBuilder().setContent(
          `**User:** <@${user.id}>\n**Discord ID:** ${user.id}\n**Role:** ${adminResponse.community_role || 'admin'}`
        )
      );

    await interaction.editReply({
      components: [container.toJSON()],
      flags: v2MessageFlags({ ephemeral: true }),
    });

    logger.info('Community admin added', {
      error_id: errorId,
      community_server_id: guildId,
      user_discord_id: user.id,
      added_by: interaction.user.id,
    });
  } catch (error) {
    if (error instanceof ApiError || (error as {statusCode?: number})?.statusCode !== undefined) {
      const statusCode = (error as ApiError).statusCode;
      if (statusCode === 404) {
        await interaction.editReply({
          content: `Could not find server or user. Make sure the user has interacted with the bot before.`,
        });
        return;
      } else if (statusCode === 403) {
        await interaction.editReply({
          content: `❌ **Permission Denied**\n\nYou need either:\n• Discord "Manage Server" permission, OR\n• Open Notes admin role for this server\n\nAsk a server admin for help.`,
        });
        return;
      } else if (statusCode === 400) {
        await interaction.editReply({
          content: `Invalid request. The user may already be an admin.`,
        });
        return;
      }
    }
    throw error;
  }
}

async function handleAdminRemove(
  interaction: ChatInputCommandInteraction,
  guildId: string,
  errorId: string
): Promise<void> {
  const user = interaction.options.getUser('user', true);

  try {
    const removeResponse = await apiClient.removeCommunityAdmin(guildId, user.id);

    const container = new ContainerBuilder()
      .setAccentColor(V2_COLORS.HIGH)
      .addTextDisplayComponents(
        new TextDisplayBuilder().setContent('## Admin Removed')
      )
      .addSeparatorComponents(createSmallSeparator())
      .addTextDisplayComponents(
        new TextDisplayBuilder().setContent(removeResponse.message)
      )
      .addSeparatorComponents(createSmallSeparator())
      .addTextDisplayComponents(
        new TextDisplayBuilder().setContent(
          `**User:** <@${user.id}>\n**Discord ID:** ${user.id}`
        )
      );

    await interaction.editReply({
      components: [container.toJSON()],
      flags: v2MessageFlags({ ephemeral: true }),
    });

    logger.info('Community admin removed', {
      error_id: errorId,
      community_server_id: guildId,
      user_discord_id: user.id,
      removed_by: interaction.user.id,
    });
  } catch (error) {
    if (error instanceof ApiError || (error as {statusCode?: number})?.statusCode !== undefined) {
      const statusCode = (error as ApiError).statusCode;
      if (statusCode === 404) {
        await interaction.editReply({
          content: `Could not find server or user.`,
        });
        return;
      } else if (statusCode === 403) {
        await interaction.editReply({
          content: `❌ **Permission Denied**\n\nYou need either:\n• Discord "Manage Server" permission, OR\n• Open Notes admin role for this server\n\nAsk a server admin for help.`,
        });
        return;
      } else if (statusCode === 409) {
        await interaction.editReply({
          content: `Cannot remove the last admin from the server. At least one admin must remain.`,
        });
        return;
      }
    }
    throw error;
  }
}

async function handleAdminList(
  interaction: ChatInputCommandInteraction,
  guildId: string,
  errorId: string
): Promise<void> {
  try {
    const admins = await apiClient.listCommunityAdmins(guildId);

    if (admins.length === 0) {
      await interaction.editReply({
        content: 'No admins found for this server.',
      });
      return;
    }

    const container = new ContainerBuilder()
      .setAccentColor(V2_COLORS.INFO)
      .addTextDisplayComponents(
        new TextDisplayBuilder().setContent(`## Open Notes Admins (${admins.length})`)
      )
      .addTextDisplayComponents(
        new TextDisplayBuilder().setContent('Users with admin privileges for this server')
      )
      .addSeparatorComponents(createDivider());

    for (const admin of admins) {
      const adminSources = admin.admin_sources.map((source: string): string => {
        switch (source) {
          case 'opennotes_platform':
            return 'Platform Admin';
          case 'community_role':
            return 'Community Admin';
          case 'discord_manage_server':
            return 'Discord Manage Server';
          default:
            return source;
        }
      }).join(', ');

      container.addTextDisplayComponents(
        new TextDisplayBuilder().setContent(
          `**${admin.display_name}**\n<@${admin.discord_id}>\n**Sources:** ${adminSources}\n**Role:** ${admin.community_role || 'member'}`
        )
      );
      container.addSeparatorComponents(createSmallSeparator());
    }

    await interaction.editReply({
      components: [container.toJSON()],
      flags: v2MessageFlags({ ephemeral: true }),
    });

    logger.info('Community admins listed', {
      error_id: errorId,
      community_server_id: guildId,
      admin_count: admins.length,
      requested_by: interaction.user.id,
    });
  } catch (error) {
    if (error instanceof ApiError || (error as {statusCode?: number})?.statusCode !== undefined) {
      const statusCode = (error as ApiError).statusCode;
      if (statusCode === 404) {
        await interaction.editReply({
          content: `Could not find server.`,
        });
        return;
      } else if (statusCode === 403) {
        await interaction.editReply({
          content: `❌ **Permission Denied**\n\nYou need either:\n• Discord "Manage Server" permission, OR\n• Open Notes admin role for this server\n\nAsk a server admin for help.`,
        });
        return;
      }
    }
    throw error;
  }
}

async function handleLlmSubcommands(
  interaction: ChatInputCommandInteraction,
  guildId: string,
  subcommand: string,
  errorId: string
): Promise<void> {
  switch (subcommand) {
    case 'set':
      await handleLlmSet(interaction, guildId, errorId);
      break;
    default:
      await interaction.editReply({
        content: 'Unknown subcommand.',
      });
  }
}

async function handleLlmSet(
  interaction: ChatInputCommandInteraction,
  guildId: string,
  errorId: string
): Promise<void> {
  const provider = interaction.options.getString('provider', true) as 'openai' | 'anthropic';
  const apiKey = interaction.options.getString('api_key', true);

  if (provider === 'openai' && !apiKey.startsWith('sk-')) {
    await interaction.editReply({
      content: '❌ Invalid OpenAI API key format. OpenAI API keys must start with "sk-".',
    });
    return;
  }

  if (provider === 'anthropic' && !apiKey.startsWith('sk-ant-')) {
    await interaction.editReply({
      content: '❌ Invalid Anthropic API key format. Anthropic API keys must start with "sk-ant-".',
    });
    return;
  }

  try {
    const communityServerId = await resolveCommunityServerId(guildId);
    const llmConfig = await apiClient.createLLMConfig(communityServerId, {
      provider,
      api_key: apiKey,
      enabled: true,
    });

    logger.info('LLM API key configured successfully', {
      error_id: errorId,
      community_server_id: guildId,
      user_id: interaction.user.id,
      config_id: llmConfig.id,
      provider,
    });

    const providerName = provider === 'openai' ? 'OpenAI' : 'Anthropic';
    const features = [
      `✅ **${providerName} API Key Configured Successfully**`,
      '',
      '**AI-Powered Features Enabled:**',
      '  • Automatic fact-checking against known datasets',
      '  • AI-assisted note writing suggestions',
      '  • Enhanced content analysis',
      '',
      '🔒 **Security:** Your API key is encrypted at rest and never exposed in bot responses.',
    ];

    await interaction.editReply({
      content: features.join('\n'),
    });
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.statusCode === 409) {
        await interaction.editReply({
          content: '⚠️ LLM configuration already exists for this server. Use the update command to modify it.',
        });
        return;
      }

      if (error.statusCode === 400) {
        await interaction.editReply({
          content: '❌ Invalid API key format or configuration. Please check your API key and try again.',
        });
        return;
      }

      if (error.statusCode === 403) {
        await interaction.editReply({
          content: `❌ **Permission Denied**\n\nYou need either:\n• Discord "Manage Server" permission, OR\n• Open Notes admin role for this server\n\nAsk a server admin for help.`,
        });
        return;
      }

      if (error.statusCode === 503 || error.statusCode >= 500) {
        await interaction.editReply({
          content: formatErrorForUser(errorId, 'Unable to connect to the server. Please try again later.'),
        });
        return;
      }
    }

    throw error;
  }
}

async function handleOpennotesSubcommands(
  interaction: ChatInputCommandInteraction,
  guildId: string,
  subcommand: string,
  errorId: string
): Promise<void> {
  switch (subcommand) {
    case 'view':
      await handleOpennotesView(interaction, guildId, errorId);
      break;
    case 'set':
      await handleOpennotesSet(interaction, guildId, errorId);
      break;
    case 'reset':
      await handleOpennotesReset(interaction, guildId, errorId);
      break;
    default:
      await interaction.editReply({
        content: 'Unknown subcommand.',
      });
  }
}

async function handleOpennotesView(
  interaction: ChatInputCommandInteraction,
  guildId: string,
  errorId: string
): Promise<void> {
  const currentConfig = await configService.getAll(guildId);

  const visibilityKeys = [
    ConfigKey.REQUEST_NOTE_EPHEMERAL,
    ConfigKey.WRITE_NOTE_EPHEMERAL,
    ConfigKey.RATE_NOTE_EPHEMERAL,
    ConfigKey.LIST_REQUESTS_EPHEMERAL,
    ConfigKey.STATUS_EPHEMERAL,
  ];

  const featureKeys = [
    ConfigKey.NOTES_ENABLED,
    ConfigKey.RATINGS_ENABLED,
    ConfigKey.REQUESTS_ENABLED,
  ];

  const rateLimitKeys = [
    ConfigKey.NOTE_RATE_LIMIT,
    ConfigKey.RATING_RATE_LIMIT,
    ConfigKey.REQUEST_RATE_LIMIT,
  ];

  const notificationKeys = [
    ConfigKey.NOTIFY_NOTE_HELPFUL,
    ConfigKey.NOTIFY_REQUEST_FULFILLED,
  ];

  const botChannelKeys = [
    ConfigKey.BOT_CHANNEL_NAME,
    ConfigKey.OPENNOTES_ROLE_NAME,
  ];

  const formatSetting = (cfg: Record<string, unknown>, key: ConfigKey): string => {
    const schema = CONFIG_SCHEMA[key];
    const value = cfg[key];
    const isDefault = value === schema.default;
    const valueDisplay = isDefault ? `\`${String(value)}\` (default)` : `**\`${String(value)}\`**`;
    return `${schema.description}: ${valueDisplay}`;
  };

  const buildConfigContainer = (cfg: Record<string, unknown>, statusMessage?: string): ContainerBuilder => {
    const container = new ContainerBuilder()
      .setAccentColor(V2_COLORS.PRIMARY)
      .addTextDisplayComponents(
        new TextDisplayBuilder().setContent('## Server Configuration')
      )
      .addSeparatorComponents(createDivider());

    container.addTextDisplayComponents(
      new TextDisplayBuilder().setContent('### Command Visibility')
    );
    for (const key of visibilityKeys) {
      const toggleButton = new ButtonBuilder()
        .setCustomId(`config:toggle:${key}`)
        .setLabel(cfg[key] ? 'Disable' : 'Enable')
        .setStyle(ButtonStyle.Secondary);

      container.addSectionComponents(
        new SectionBuilder()
          .addTextDisplayComponents(
            new TextDisplayBuilder().setContent(formatSetting(cfg, key))
          )
          .setButtonAccessory(toggleButton)
      );
    }

    container.addSeparatorComponents(createDivider());
    container.addTextDisplayComponents(
      new TextDisplayBuilder().setContent('### Feature Toggles')
    );
    for (const key of featureKeys) {
      container.addTextDisplayComponents(
        new TextDisplayBuilder().setContent(`- ${formatSetting(cfg, key)}`)
      );
    }

    container.addSeparatorComponents(createDivider());
    container.addTextDisplayComponents(
      new TextDisplayBuilder().setContent('### Rate Limits')
    );
    for (const key of rateLimitKeys) {
      container.addTextDisplayComponents(
        new TextDisplayBuilder().setContent(`- ${formatSetting(cfg, key)}`)
      );
    }

    container.addSeparatorComponents(createDivider());
    container.addTextDisplayComponents(
      new TextDisplayBuilder().setContent('### Notifications')
    );
    for (const key of notificationKeys) {
      container.addTextDisplayComponents(
        new TextDisplayBuilder().setContent(`- ${formatSetting(cfg, key)}`)
      );
    }

    container.addSeparatorComponents(createDivider());
    container.addTextDisplayComponents(
      new TextDisplayBuilder().setContent('### Bot Channel')
    );
    for (const key of botChannelKeys) {
      container.addTextDisplayComponents(
        new TextDisplayBuilder().setContent(`- ${formatSetting(cfg, key)}`)
      );
    }

    container.addSeparatorComponents(createDivider());

    let tipMessage = 'Use `/config opennotes set` to change specific settings.';
    if (statusMessage) {
      tipMessage = statusMessage + '\n\n' + tipMessage;
    }
    container.addTextDisplayComponents(
      new TextDisplayBuilder().setContent(tipMessage)
    );

    container.addActionRowComponents(
      new ActionRowBuilder<ButtonBuilder>().addComponents(
        new ButtonBuilder()
          .setCustomId('config:reset:all')
          .setLabel('Reset All Settings')
          .setStyle(ButtonStyle.Danger),
        new ButtonBuilder()
          .setCustomId('config:refresh')
          .setLabel('Refresh')
          .setStyle(ButtonStyle.Primary)
      )
    );

    return container;
  };

  const buildConfirmationContainer = (): ContainerBuilder => {
    const container = new ContainerBuilder()
      .setAccentColor(V2_COLORS.CRITICAL)
      .addTextDisplayComponents(
        new TextDisplayBuilder().setContent('## Reset Configuration')
      )
      .addSeparatorComponents(createSmallSeparator())
      .addTextDisplayComponents(
        new TextDisplayBuilder().setContent(
          '**Warning:** This will reset ALL server configuration settings to their defaults.\n\nThis action cannot be undone. Are you sure you want to continue?'
        )
      )
      .addSeparatorComponents(createDivider())
      .addActionRowComponents(
        new ActionRowBuilder<ButtonBuilder>().addComponents(
          new ButtonBuilder()
            .setCustomId('config:reset:confirm')
            .setLabel('Confirm Reset All')
            .setStyle(ButtonStyle.Danger),
          new ButtonBuilder()
            .setCustomId('config:reset:cancel')
            .setLabel('Cancel')
            .setStyle(ButtonStyle.Secondary)
        )
      );

    return container;
  };

  const configContainer = buildConfigContainer(currentConfig);

  const message = await interaction.editReply({
    components: [configContainer.toJSON()],
    flags: v2MessageFlags({ ephemeral: true }),
  });

  const collector = message.createMessageComponentCollector({
    componentType: ComponentType.Button,
    time: TIMEOUTS.COLLECTOR_TIMEOUT_MS,
  });

  collector.on('collect', (buttonInteraction): void => {
    void (async (): Promise<void> => {
      if (buttonInteraction.user.id !== interaction.user.id) {
        logger.warn('Unauthorized button interaction attempt', {
          authorized_user: interaction.user.id,
          attempted_user: buttonInteraction.user.id,
          custom_id: buttonInteraction.customId,
          guild_id: guildId,
          command: 'config',
        });
        await buttonInteraction.reply({
          content: 'Only the user who ran the command can use these buttons.',
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
        await buttonInteraction.deferUpdate();

        const parseResult = parseCustomId(buttonInteraction.customId, 2);
        if (!parseResult.success || !parseResult.parts) {
          logger.error('Failed to parse customId in config command', {
            error_id: errorId,
            customId: buttonInteraction.customId,
            error: parseResult.error,
          });
          await buttonInteraction.followUp({
            content: 'Invalid interaction data. Please try the command again.',
            flags: MessageFlags.Ephemeral,
          });
          return;
        }

        const [action, type, key] = parseResult.parts;

        if (action === 'config') {
          if (type === 'refresh') {
            const freshConfig = await configService.getAll(guildId);
            const refreshedContainer = buildConfigContainer(freshConfig);
            await buttonInteraction.editReply({
              components: [refreshedContainer.toJSON()],
              flags: v2MessageFlags({ ephemeral: true }),
            });
          } else if (type === 'toggle' && key) {
            const currentValue = await configService.get(guildId, key as ConfigKey);
            const newValue = !currentValue;
            await configService.set(guildId, key as ConfigKey, newValue, buttonInteraction.user.id);

            const updatedConfig = await configService.getAll(guildId);
            const statusMsg = `Toggled **${CONFIG_SCHEMA[key as ConfigKey].description}** to **\`${newValue}\`**`;
            const updatedContainer = buildConfigContainer(updatedConfig, statusMsg);
            await buttonInteraction.editReply({
              components: [updatedContainer.toJSON()],
              flags: v2MessageFlags({ ephemeral: true }),
            });

            logger.info('Config toggled via button', { guildId, key, newValue, userId: buttonInteraction.user.id });
          } else if (type === 'reset' && key === 'all') {
            const confirmContainer = buildConfirmationContainer();
            await buttonInteraction.editReply({
              components: [confirmContainer.toJSON()],
              flags: v2MessageFlags({ ephemeral: true }),
            });
          } else if (type === 'reset' && key === 'confirm') {
            await configService.reset(guildId, undefined, buttonInteraction.user.id);

            const resetConfig = await configService.getAll(guildId);
            const resetContainer = buildConfigContainer(resetConfig, 'All settings have been reset to defaults.');
            await buttonInteraction.editReply({
              components: [resetContainer.toJSON()],
              flags: v2MessageFlags({ ephemeral: true }),
            });

            logger.info('All config reset via button', { guildId, userId: buttonInteraction.user.id });
          } else if (type === 'reset' && key === 'cancel') {
            const cancelConfig = await configService.getAll(guildId);
            const cancelContainer = buildConfigContainer(cancelConfig, 'Reset cancelled.');
            await buttonInteraction.editReply({
              components: [cancelContainer.toJSON()],
              flags: v2MessageFlags({ ephemeral: true }),
            });
          }
        }
      } catch (error) {
        const errorDetails = extractErrorDetails(error);
        logger.error('Error handling config button interaction', {
          error_id: errorId,
          community_server_id: guildId,
          user_id: buttonInteraction.user.id,
          custom_id: buttonInteraction.customId,
          error: errorDetails.message,
          error_type: errorDetails.type,
          stack: errorDetails.stack,
        });
        await buttonInteraction.followUp({
          content: formatErrorForUser(errorId, 'Failed to process button action.'),
          flags: MessageFlags.Ephemeral,
        });
      }
    })();
  });

  collector.on('end', () => {
    interaction.editReply({
      components: [],
    }).catch(() => {
    });
  });
}

async function handleOpennotesSet(
  interaction: ChatInputCommandInteraction,
  guildId: string,
  errorId: string
): Promise<void> {
  const key = interaction.options.getString('key', true) as ConfigKey;
  const valueStr = interaction.options.getString('value', true);

  const validation = ConfigValidator.validate(key, valueStr);
  if (!validation.valid) {
    await interaction.editReply({
      content: `❌ Invalid value: ${validation.error}`,
    });
    return;
  }

  const updatedBy = interaction.user.id;

  if (key === ConfigKey.BOT_CHANNEL_NAME && interaction.guild) {
    const oldChannelName = (await configService.get(guildId, ConfigKey.BOT_CHANNEL_NAME)) as string;
    const newChannelName = validation.parsedValue as string;

    if (oldChannelName !== newChannelName) {
      try {
        const result = await botChannelService.migrateChannel(
          interaction.guild,
          oldChannelName,
          newChannelName,
          configService
        );

        await guildOnboardingService.postWelcomeToChannel(result.newChannel);

        await configService.set(guildId, key, newChannelName, updatedBy);

        const schema = CONFIG_SCHEMA[key];
        const deleteMessage = result.oldChannelDeleted
          ? `Old channel \`#${oldChannelName}\` has been deleted.`
          : `Old channel \`#${oldChannelName}\` could not be deleted (you may need to remove it manually).`;

        await interaction.editReply({
          content: `✅ Updated **${schema.description}** to **${newChannelName}**\n\nNew bot channel ${result.newChannel.toString()} has been created with welcome message.\n${deleteMessage}`,
        });

        logger.info('Bot channel migrated via config command', {
          error_id: errorId,
          guildId,
          oldChannelName,
          newChannelName,
          newChannelId: result.newChannel.id,
          oldChannelDeleted: result.oldChannelDeleted,
          updatedBy,
        });
        return;
      } catch (error) {
        logger.error('Failed to migrate bot channel', {
          error_id: errorId,
          guildId,
          oldChannelName,
          newChannelName,
          error: error instanceof Error ? error.message : String(error),
          stack: error instanceof Error ? error.stack : undefined,
        });
        await interaction.editReply({
          content: `❌ Failed to migrate bot channel: ${error instanceof Error ? error.message : 'Unknown error'}`,
        });
        return;
      }
    }
  }

  await configService.set(guildId, key, validation.parsedValue!, updatedBy);

  const schema = CONFIG_SCHEMA[key];
  await interaction.editReply({
    content: `✅ Updated **${schema.description}** to **${validation.parsedValue}**`,
  });

  logger.info('Guild config updated via command', {
    guildId,
    key,
    value: validation.parsedValue,
    updatedBy,
  });
}

async function handleOpennotesReset(
  interaction: ChatInputCommandInteraction,
  guildId: string,
  _errorId: string
): Promise<void> {
  const key = interaction.options.getString('key', false) as ConfigKey | null;
  const updatedBy = interaction.user.id;

  if (key) {
    await configService.reset(guildId, key, updatedBy);
    const schema = CONFIG_SCHEMA[key];
    const defaultValue = schema.default;
    await interaction.editReply({
      content: `✅ Reset **${schema.description}** to default value: **${defaultValue}**`,
    });
    logger.info('Guild config key reset via command', { guildId, key, updatedBy });
  } else {
    await configService.reset(guildId, undefined, updatedBy);
    await interaction.editReply({
      content: '✅ All configuration settings have been reset to their default values.',
    });
    logger.info('All guild config reset via command', { guildId, updatedBy });
  }
}

async function handleContentMonitorSubcommands(
  interaction: ChatInputCommandInteraction,
  guildId: string,
  subcommand: string,
  errorId: string
): Promise<void> {
  switch (subcommand) {
    case 'enable':
      await handleContentMonitorEnable(interaction, guildId, errorId);
      break;
    case 'disable':
      await handleContentMonitorDisable(interaction, guildId, errorId);
      break;
    case 'enable-all':
      await handleContentMonitorEnableAll(interaction, guildId, errorId);
      break;
    default:
      await interaction.editReply({
        content: 'Unknown subcommand.',
      });
  }
}

async function handleContentMonitorEnable(
  interaction: ChatInputCommandInteraction,
  guildId: string,
  errorId: string
): Promise<void> {
  const channel = interaction.options.getChannel('channel', true);
  if (!channel.id) {
    await interaction.editReply({ content: '❌ Invalid channel' });
    return;
  }

  try {
    await apiClient.getMonitoredChannel(channel.id);

    await apiClient.updateMonitoredChannel(channel.id, {
      enabled: true,
      updated_by: interaction.user.id,
    });

    await interaction.editReply({
      content:
        `✅ **Content monitoring enabled** for <#${channel.id}>.\n\n` +
        'Messages in this channel will be monitored for potential fact-checking needs.',
    });

    logger.info('Content monitoring enabled for channel', {
      error_id: errorId,
      channel_id: channel.id,
      guild_id: guildId,
      user_id: interaction.user.id,
    });
  } catch (error) {
    if (error instanceof ApiError && error.statusCode === 404) {
      const result = await apiClient.createMonitoredChannel({
        community_server_id: guildId,
        channel_id: channel.id,
        enabled: true,
        similarity_threshold: config.similaritySearchDefaultThreshold,
        dataset_tags: ['snopes'],
        updated_by: interaction.user.id,
      });

      if (result === null) {
        await interaction.editReply({
          content:
            `✅ **Content monitoring already enabled** for <#${channel.id}>.\n\n` +
            'This channel is already being monitored.',
        });
      } else {
        await interaction.editReply({
          content:
            `✅ **Content monitoring enabled** for <#${channel.id}>.\n\n` +
            'Messages in this channel will now be monitored for potential fact-checking needs.',
        });

        logger.info('Content monitoring enabled for new channel', {
          error_id: errorId,
          channel_id: channel.id,
          guild_id: guildId,
          user_id: interaction.user.id,
        });
      }
    } else {
      throw error;
    }
  }
}

async function handleContentMonitorDisable(
  interaction: ChatInputCommandInteraction,
  guildId: string,
  errorId: string
): Promise<void> {
  const channel = interaction.options.getChannel('channel', true);
  if (!channel.id) {
    await interaction.editReply({ content: '❌ Invalid channel' });
    return;
  }

  try {
    await apiClient.getMonitoredChannel(channel.id);

    await apiClient.updateMonitoredChannel(channel.id, {
      enabled: false,
      updated_by: interaction.user.id,
    });

    await interaction.editReply({
      content:
        `✅ **Content monitoring disabled** for <#${channel.id}>.\n\n` +
        'Messages in this channel will no longer be monitored for fact-checking.\n' +
        'Use `/config content-monitor enable` to re-enable monitoring.',
    });

    logger.info('Content monitoring disabled for channel', {
      error_id: errorId,
      channel_id: channel.id,
      guild_id: guildId,
      user_id: interaction.user.id,
    });
  } catch (error) {
    if (error instanceof ApiError && error.statusCode === 404) {
      await interaction.editReply({
        content:
          `❌ Channel <#${channel.id}> is not currently monitored.\n\n` +
          'Use `/config content-monitor enable` to start monitoring this channel.',
      });
    } else {
      throw error;
    }
  }
}

async function handleContentMonitorEnableAll(
  interaction: ChatInputCommandInteraction,
  guildId: string,
  errorId: string
): Promise<void> {
  const guild = interaction.guild;
  if (!guild) {
    await interaction.editReply({
      content: 'Unable to access guild information. Please try again.',
    });
    return;
  }

  await guildSetupService.autoRegisterChannels(guild);

  const container = new ContainerBuilder()
    .setAccentColor(V2_COLORS.HELPFUL)
    .addTextDisplayComponents(
      new TextDisplayBuilder().setContent('## Content Monitoring Setup Complete')
    )
    .addSeparatorComponents(createSmallSeparator())
    .addTextDisplayComponents(
      new TextDisplayBuilder().setContent(
        'All text channels have been registered for content monitoring.\n\n' +
        'Channels that were already monitored were skipped. ' +
        'New channels will now be monitored for messages that may need Community Notes.'
      )
    );

  await interaction.editReply({
    components: [container.toJSON()],
    flags: v2MessageFlags({ ephemeral: true }),
  });

  logger.info('Content monitoring enabled for all channels', {
    error_id: errorId,
    guild_id: guildId,
    user_id: interaction.user.id,
  });
}

async function handleNotePublisherSubcommands(
  interaction: ChatInputCommandInteraction,
  guildId: string,
  subcommand: string,
  _errorId: string
): Promise<void> {
  switch (subcommand) {
    case 'enable':
      await handleNotePublisherEnable(interaction, guildId);
      break;
    case 'disable':
      await handleNotePublisherDisable(interaction, guildId);
      break;
    case 'threshold':
      await handleNotePublisherThreshold(interaction, guildId);
      break;
    case 'enable-channel':
      await handleNotePublisherEnableChannel(interaction, guildId);
      break;
    case 'disable-channel':
      await handleNotePublisherDisableChannel(interaction, guildId);
      break;
    case 'status':
      await handleNotePublisherStatus(interaction, guildId);
      break;
    default:
      await interaction.editReply({
        content: 'Unknown subcommand.',
      });
  }
}

async function handleNotePublisherEnable(
  interaction: ChatInputCommandInteraction,
  guildId: string
): Promise<void> {
  await notePublisherConfigService.setConfig(guildId, true, undefined, undefined, interaction.user.id);

  await interaction.editReply({
    content:
      '✅ **Note publishering enabled** for this server.\n\n' +
      'High-quality notes (score ≥ threshold with ≥5 ratings) will be automatically posted as replies.\n\n' +
      `Use \`/config note-publisher threshold\` to adjust the score threshold.\n` +
      `Use \`/config note-publisher disable-channel\` to opt-out specific channels.`,
  });
}

async function handleNotePublisherDisable(
  interaction: ChatInputCommandInteraction,
  guildId: string
): Promise<void> {
  await notePublisherConfigService.setConfig(guildId, false, undefined, undefined, interaction.user.id);

  await interaction.editReply({
    content:
      '✅ **Note publishering disabled** for this server.\n\n' +
      'Notes will no longer be automatically posted. Use `/config note-publisher enable` to re-enable.',
  });
}

async function handleNotePublisherThreshold(
  interaction: ChatInputCommandInteraction,
  guildId: string
): Promise<void> {
  const threshold = interaction.options.getNumber('value', true);

  await notePublisherConfigService.setThreshold(guildId, threshold, undefined, interaction.user.id);

  const percentage = (threshold * 100).toFixed(0);

  await interaction.editReply({
    content:
      `✅ **Threshold updated** to **${percentage}%** (${threshold}).\n\n` +
      `Notes must reach this score with standard confidence (≥5 ratings) to be note-publishered.`,
  });
}

async function handleNotePublisherEnableChannel(
  interaction: ChatInputCommandInteraction,
  guildId: string
): Promise<void> {
  const channel = interaction.options.getChannel('channel', true);
  if (!channel.id) {
    await interaction.editReply({ content: '❌ Invalid channel' });
    return;
  }

  await notePublisherConfigService.enableChannel(guildId, channel.id, interaction.user.id);

  await interaction.editReply({
    content: `✅ **Note publishering enabled** in <#${channel.id}>.`,
  });
}

async function handleNotePublisherDisableChannel(
  interaction: ChatInputCommandInteraction,
  guildId: string
): Promise<void> {
  const channel = interaction.options.getChannel('channel', true);
  if (!channel.id) {
    await interaction.editReply({ content: '❌ Invalid channel' });
    return;
  }

  await notePublisherConfigService.disableChannel(guildId, channel.id, interaction.user.id);

  await interaction.editReply({
    content:
      `✅ **Note publishering disabled** in <#${channel.id}>.\n\n` +
      `High-quality notes will not be automatically posted in this channel.\n` +
      `Use \`/config note-publisher enable-channel\` to re-enable.`,
  });
}

async function handleNotePublisherStatus(
  interaction: ChatInputCommandInteraction,
  guildId: string
): Promise<void> {
  const channel = interaction.options.getChannel('channel');
  const channelId = channel?.id;

  const publisherConfig = await notePublisherConfigService.getConfig(guildId, channelId);

  const statusEmoji = publisherConfig.enabled ? '✅ Enabled' : '❌ Disabled';
  const thresholdPercentage = ((publisherConfig.threshold || 0.7) * 100).toFixed(0);
  const scope = channelId ? `for <#${String(channelId)}>` : 'for this server';

  let message = `**Auto-Post Configuration** ${scope}\n\n`;
  message += `**Status:** ${statusEmoji}\n`;
  message += `**Threshold:** ${thresholdPercentage}% (${publisherConfig.threshold || 0.7})\n`;
  message += `**Default Threshold:** ${(notePublisherConfigService.getDefaultThreshold() * 100).toFixed(0)}%\n\n`;

  if (publisherConfig.enabled) {
    message += `High-quality notes will be automatically posted as replies when they reach the threshold with standard confidence (≥5 ratings).`;
  } else {
    message += `Note publishering is currently disabled. Use \`/config note-publisher enable\` to enable.`;
  }

  await interaction.editReply({ content: message });
}
