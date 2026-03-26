import { ButtonInteraction, MessageFlags, ActionRowBuilder, ButtonBuilder, ContainerBuilder, type APIMessageTopLevelComponent } from 'discord.js';
import { cache } from '../cache.js';
import { logger } from '../logger.js';
import { NavigationStateManager, ScreenState } from '../lib/navigation-state.js';
import { buildNavHub, buildBackButton, buildContextualNav, NAV_GRAPH } from '../lib/navigation-components.js';
import { v2MessageFlags, createContainer, createTextSection, createDivider, V2_COLORS } from '../utils/v2-components.js';
import { buildWelcomeContainer } from '../lib/welcome-content.js';
import { serviceProvider } from '../services/index.js';
import { DiscordFormatter } from '../services/DiscordFormatter.js';
import { apiClient } from '../api-client.js';

const navState = new NavigationStateManager(cache);

function detectCommandContext(components: readonly { toJSON: () => unknown }[]): string {
  const navCustomIds = new Set<string>();
  for (const row of components) {
    const rowData = row.toJSON() as { components?: { custom_id?: string }[] };
    if (rowData.components) {
      for (const comp of rowData.components) {
        if (comp.custom_id?.startsWith('nav:') && comp.custom_id !== 'nav:menu') {
          navCustomIds.add(comp.custom_id);
        }
      }
    }
  }

  for (const [context, actions] of Object.entries(NAV_GRAPH)) {
    const expectedIds = new Set(actions.map(a => a.customId));
    if (expectedIds.size === navCustomIds.size &&
        [...expectedIds].every(id => navCustomIds.has(id))) {
      return context;
    }
  }

  return 'unknown';
}

export async function handleNavInteraction(interaction: ButtonInteraction): Promise<void> {
  const customId = interaction.customId;

  if (customId === 'nav:menu') {
    await handleMenuButton(interaction);
  } else if (customId === 'nav:back') {
    await handleBackButton(interaction);
  } else if (customId === 'nav:hub') {
    await handleHubButton(interaction);
  } else {
    await handleNavAction(interaction);
  }
}

async function handleMenuButton(interaction: ButtonInteraction): Promise<void> {
  const userId = interaction.user.id;
  const messageId = interaction.message.id;

  const components = interaction.message.components.map(c => c.toJSON());
  const flags = interaction.message.flags.bitfield;
  const content = interaction.message.content;

  const screenState: ScreenState = {
    commandContext: detectCommandContext(interaction.message.components),
    components,
    flags,
    ...(content ? { content } : {}),
  };

  await navState.push(userId, messageId, screenState);

  const container = buildHubContainer();

  const hubRows = buildNavHub();
  for (const row of hubRows) {
    container.addActionRowComponents(row);
  }

  container.addSeparatorComponents(createDivider());
  const navRow = new ActionRowBuilder<ButtonBuilder>();
  navRow.addComponents(buildBackButton());
  container.addActionRowComponents(navRow);

  await interaction.update({
    components: [container],
    flags: v2MessageFlags({ ephemeral: true }),
  });
}

async function handleBackButton(interaction: ButtonInteraction): Promise<void> {
  const userId = interaction.user.id;
  const messageId = interaction.message.id;

  const state = await navState.pop(userId, messageId);

  if (!state) {
    await interaction.reply({
      content: 'Nothing to go back to.',
      flags: MessageFlags.Ephemeral,
    });
    return;
  }

  await interaction.update({
    content: state.content ?? '',
    components: state.components as APIMessageTopLevelComponent[],
    flags: state.flags,
  });
}

async function handleHubButton(interaction: ButtonInteraction): Promise<void> {
  const userId = interaction.user.id;
  const messageId = interaction.message.id;

  await navState.clear(userId, messageId);

  const container = buildHubContainer();

  const hubRows = buildNavHub();
  for (const row of hubRows) {
    container.addActionRowComponents(row);
  }

  await interaction.update({
    components: [container],
    flags: v2MessageFlags({ ephemeral: true }),
  });
}

const REDIRECT_MESSAGES: Record<string, string> = {
  'note:write': 'Use `/note write <message-id>` to write a community note.',
  'vibecheck:scan': 'Use `/vibecheck scan` to scan your channel.',
  'note:rate': 'Use `/note rate <note-id> <helpful>` to rate a note.',
  'note:view': 'Use `/note view <message-id>` to view notes for a message.',
  'note:request': 'Use `/note request <message-id>` to request a note on a message.',
  'note:score': 'Use `/note score <note-id>` to view a note\'s score.',
  'vibecheck:status': 'Use `/vibecheck` to check the status of a scan.',
  'vibecheck:create-requests': 'Use `/vibecheck` to create note requests from a scan.',
  'clear:notes': 'Use `/clear` to clear notes.',
  'clear:requests': 'Use `/clear` to clear requests.',
  'config': 'Use `/config` to manage server configuration.',
  'note-request-context': 'Right-click a message > **Apps** > **Request Note** to request a note.',
};

type NavActionHandler = (interaction: ButtonInteraction) => Promise<void>;

const ACTION_HANDLERS: Record<string, NavActionHandler> = {
  'about-opennotes': handleAboutOpennotes,
  'status-bot': handleStatusBot,
};

const COMMAND_REDIRECTS: Record<string, { command: string; subcommand: string; description: string }> = {
  'list:notes': { command: 'list', subcommand: 'notes', description: 'Browse and rate community notes' },
  'list:requests': { command: 'list', subcommand: 'requests', description: 'View and respond to note requests' },
};

function formatCommandMention(interaction: ButtonInteraction, command: string, subcommand: string): string {
  const cmd = interaction.client.application?.commands.cache.find(c => c.name === command);
  if (cmd) {
    return `</${command} ${subcommand}:${cmd.id}>`;
  }
  return `\`/${command} ${subcommand}\``;
}

async function handleNavAction(interaction: ButtonInteraction): Promise<void> {
  const action = interaction.customId.slice(4);

  const handler = ACTION_HANDLERS[action];
  if (handler) {
    await handler(interaction);
    return;
  }

  const commandRedirect = COMMAND_REDIRECTS[action];
  if (commandRedirect) {
    const mention = formatCommandMention(interaction, commandRedirect.command, commandRedirect.subcommand);
    await interaction.reply({
      content: `${mention} — ${commandRedirect.description}`,
      flags: MessageFlags.Ephemeral,
    });
    return;
  }

  const redirectMessage = REDIRECT_MESSAGES[action];
  if (redirectMessage) {
    await interaction.deferReply({ flags: v2MessageFlags({ ephemeral: true }) });
    await interaction.editReply({ content: redirectMessage });
    return;
  }

  const container = buildHubContainer();
  const hubRows = buildNavHub();
  for (const row of hubRows) {
    container.addActionRowComponents(row);
  }
  await interaction.update({
    components: [container],
    flags: v2MessageFlags({ ephemeral: true }),
  });
}

async function handleAboutOpennotes(interaction: ButtonInteraction): Promise<void> {
  await interaction.deferReply({ flags: v2MessageFlags({ ephemeral: true }) });

  const container = buildWelcomeContainer();
  container.addActionRowComponents(buildContextualNav('about-opennotes'));

  await interaction.editReply({
    components: [container],
    flags: v2MessageFlags({ ephemeral: true }),
  });
}

async function handleStatusBot(interaction: ButtonInteraction): Promise<void> {
  await interaction.deferReply({ flags: v2MessageFlags({ ephemeral: true }) });

  try {
    const guilds = interaction.client.guilds.cache.size;
    const statusService = serviceProvider.getStatusService();
    const scoringService = serviceProvider.getScoringService();

    const result = await statusService.execute(guilds);

    if (!result.success) {
      const errorResponse = DiscordFormatter.formatErrorV2(result);
      await interaction.editReply({
        components: errorResponse.components,
        flags: errorResponse.flags,
      });
      return;
    }

    let communityServerId: string | undefined;
    if (interaction.guildId) {
      try {
        const communityServer = await apiClient.getCommunityServerByPlatformId(interaction.guildId);
        communityServerId = communityServer.data.id;
      } catch (error) {
        logger.error('Failed to fetch community server UUID for scoring status', {
          guild_id: interaction.guildId,
          error: error instanceof Error ? error.message : String(error),
        });
      }
    }

    const scoringResult = await scoringService.getScoringStatus(communityServerId);

    const response = DiscordFormatter.formatStatusSuccessV2(result.data!);

    if (scoringResult.success && scoringResult.data) {
      const scoringV2 = DiscordFormatter.formatScoringStatusV2(scoringResult.data);
      response.container
        .addSeparatorComponents(scoringV2.separator)
        .addTextDisplayComponents(scoringV2.textDisplay);
    }

    response.container.addActionRowComponents(buildContextualNav('status-bot'));

    await interaction.editReply({
      components: [response.container.toJSON()],
      flags: response.flags,
    });
  } catch (error) {
    logger.error('Failed to handle nav status-bot', {
      error: error instanceof Error ? error.message : String(error),
    });
    await interaction.editReply({
      content: 'Failed to load bot status. Please try `/vibecheck` instead.',
    });
  }
}


function buildHubContainer(): ContainerBuilder {
  const container = createContainer(V2_COLORS.PRIMARY);

  container.addTextDisplayComponents(
    createTextSection('## OpenNotes Navigation')
  );
  container.addTextDisplayComponents(
    createTextSection('Browse all available actions and navigate between features.')
  );
  container.addSeparatorComponents(createDivider());

  return container;
}
