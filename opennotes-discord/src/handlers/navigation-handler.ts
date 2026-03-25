import { ButtonInteraction, MessageFlags, ActionRowBuilder, ButtonBuilder, ContainerBuilder, type APIMessageTopLevelComponent } from 'discord.js';
import { cache } from '../cache.js';
import { NavigationStateManager, ScreenState } from '../lib/navigation-state.js';
import { buildNavHub, buildBackButton, buildFullMenuButton } from '../lib/navigation-components.js';
import { v2MessageFlags, createContainer, createTextSection, createDivider, V2_COLORS } from '../utils/v2-components.js';

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

async function handleNavAction(interaction: ButtonInteraction): Promise<void> {
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
