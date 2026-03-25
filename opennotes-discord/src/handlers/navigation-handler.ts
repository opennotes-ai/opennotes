import { ButtonInteraction, MessageFlags, ActionRowBuilder, ButtonBuilder, ContainerBuilder, type APIMessageTopLevelComponent } from 'discord.js';
import { cache } from '../cache.js';
import { logger } from '../logger.js';
import { NavigationStateManager, ScreenState } from '../lib/navigation-state.js';
import { buildNavHub, buildBackButton, buildFullMenuButton, buildContextualNav } from '../lib/navigation-components.js';
import { v2MessageFlags, createContainer, createTextSection, createDivider, V2_COLORS } from '../utils/v2-components.js';
import { buildWelcomeContainer } from '../lib/welcome-content.js';
import { serviceProvider } from '../services/index.js';
import { DiscordFormatter } from '../services/DiscordFormatter.js';
import { apiClient } from '../api-client.js';
import { resolveUserProfileId } from '../lib/user-profile-resolver.js';

const navState = new NavigationStateManager(cache);

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

  const screenState: ScreenState = {
    commandContext: 'unknown',
    components,
    flags,
  };

  await navState.push(userId, messageId, screenState);

  const container = buildHubContainer();

  const navRow = new ActionRowBuilder<ButtonBuilder>();
  navRow.addComponents(buildBackButton(), buildFullMenuButton());

  container.addSeparatorComponents(createDivider());
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
  'list:notes': handleListNotes,
  'list:requests': handleListRequests,
  'list:top-notes': handleListTopNotes,
};

async function handleNavAction(interaction: ButtonInteraction): Promise<void> {
  const action = interaction.customId.slice(4);

  const handler = ACTION_HANDLERS[action];
  if (handler) {
    await handler(interaction);
    return;
  }

  const redirectMessage = REDIRECT_MESSAGES[action];
  if (redirectMessage) {
    await interaction.deferReply({ flags: MessageFlags.Ephemeral });
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
  await interaction.deferReply({ flags: MessageFlags.Ephemeral });

  const container = buildWelcomeContainer();
  container.addActionRowComponents(buildContextualNav('about-opennotes'));

  await interaction.editReply({
    components: [container],
    flags: v2MessageFlags({ ephemeral: true }),
  });
}

async function handleStatusBot(interaction: ButtonInteraction): Promise<void> {
  await interaction.deferReply({ flags: MessageFlags.Ephemeral });

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

  const scoringResult = await scoringService.getScoringStatus();

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
}

async function handleListNotes(interaction: ButtonInteraction): Promise<void> {
  await interaction.deferReply({ flags: MessageFlags.Ephemeral });

  try {
    const userId = interaction.user.id;
    const guildId = interaction.guildId;

    let profileUuid: string | undefined;
    try {
      profileUuid = await resolveUserProfileId(userId, apiClient);
    } catch {
      await interaction.editReply({ content: 'Could not find your user profile. Please try again later.' });
      return;
    }

    let communityServerUuid: string | undefined;
    if (guildId) {
      try {
        const communityServer = await apiClient.getCommunityServerByPlatformId(guildId);
        communityServerUuid = communityServer.data.id;
      } catch {
        logger.warn('Failed to resolve community server for nav list:notes', { guildId });
      }
    }

    const notesResponse = await apiClient.listNotesWithStatus(
      'NEEDS_MORE_RATINGS', 1, 5, communityServerUuid, profileUuid
    );

    const container = createContainer(V2_COLORS.INFO);

    if (notesResponse.total === 0) {
      container.addTextDisplayComponents(
        createTextSection('## Rating Queue\n\nNo notes need rating right now! All caught up.')
      );
    } else {
      container.addTextDisplayComponents(
        createTextSection(`## Rating Queue\n\n${notesResponse.total} notes need your rating.\n\nUse \`/list notes\` for the full interactive queue with rating buttons.`)
      );
    }

    container.addSeparatorComponents(createDivider());
    container.addActionRowComponents(buildContextualNav('list:notes'));

    await interaction.editReply({
      components: [container],
      flags: v2MessageFlags({ ephemeral: true }),
    });
  } catch (error) {
    logger.error('Failed to handle nav list:notes', {
      error: error instanceof Error ? error.message : String(error),
    });
    await interaction.editReply({
      content: 'Failed to load the notes queue. Please try `/list notes` instead.',
    });
  }
}

async function handleListRequests(interaction: ButtonInteraction): Promise<void> {
  await interaction.deferReply({ flags: MessageFlags.Ephemeral });

  const listRequestsService = serviceProvider.getListRequestsService();
  const result = await listRequestsService.execute({
    userId: interaction.user.id,
    page: 1,
    size: 5,
  });

  if (!result.success) {
    const errorResponse = DiscordFormatter.formatErrorV2(result);
    await interaction.editReply({
      components: errorResponse.components,
      flags: errorResponse.flags,
    });
    return;
  }

  const formatted = await DiscordFormatter.formatListRequestsSuccessV2(
    result.data!,
    { guildId: interaction.guildId ?? undefined }
  );

  formatted.container.addActionRowComponents(buildContextualNav('list:requests'));

  await interaction.editReply({
    components: [formatted.container.toJSON()],
    flags: formatted.flags,
  });
}

async function handleListTopNotes(interaction: ButtonInteraction): Promise<void> {
  await interaction.deferReply({ flags: MessageFlags.Ephemeral });

  const scoringService = serviceProvider.getScoringService();
  const result = await scoringService.getTopNotes({ limit: 10 });

  if (!result.success) {
    const errorResponse = DiscordFormatter.formatErrorV2(result);
    await interaction.editReply({
      components: errorResponse.components,
      flags: errorResponse.flags,
    });
    return;
  }

  const formatted = DiscordFormatter.formatTopNotesForQueueV2(result.data!, 1, 10);

  formatted.container.addActionRowComponents(buildContextualNav('list:top-notes'));

  await interaction.editReply({
    components: [formatted.container.toJSON()],
    flags: formatted.flags,
  });
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
