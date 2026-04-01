import { ButtonBuilder, ButtonStyle, ActionRowBuilder } from 'discord.js';

export interface NavAction {
  label: string;
  customId: string;
  emoji?: string;
}

export const NAV_GRAPH: Record<string, NavAction[]> = {
  'list:notes': [
    { label: 'See note requests and write a note', customId: 'nav:list:requests', emoji: '\u{1F4CB}' },
  ],
  'list:requests': [
    { label: 'Read notes others have written and rate them', customId: 'nav:list:notes', emoji: '\u{1F4DD}' },
  ],
  'vibecheck:scan': [
    { label: 'Status', customId: 'nav:vibecheck:status', emoji: '\u{1F4CA}' },
    { label: 'Create Requests', customId: 'nav:vibecheck:create-requests', emoji: '\u{1F4E8}' },
  ],
  'vibecheck:status': [
    { label: 'Create Requests', customId: 'nav:vibecheck:create-requests', emoji: '\u{1F4E8}' },
    { label: 'See note requests and write a note', customId: 'nav:list:requests', emoji: '\u{1F4CB}' },
  ],
  'vibecheck:create-requests': [
    { label: 'See note requests and write a note', customId: 'nav:list:requests', emoji: '\u{1F4CB}' },
    { label: 'Read notes others have written and rate them', customId: 'nav:list:notes', emoji: '\u{1F4DD}' },
  ],
  'note:write': [
    { label: 'Read notes others have written and rate them', customId: 'nav:list:notes', emoji: '\u{1F4DD}' },
  ],
  'note:request': [
    { label: 'See note requests and write a note', customId: 'nav:list:requests', emoji: '\u{1F4CB}' },
  ],
  'note:view': [
    { label: 'Rate', customId: 'nav:note:rate', emoji: '\u{1F5F3}\uFE0F' },
    { label: 'Read notes others have written and rate them', customId: 'nav:list:notes', emoji: '\u{1F4DD}' },
  ],
  'note:score': [
    { label: 'Read notes others have written and rate them', customId: 'nav:list:notes', emoji: '\u{1F4DD}' },
  ],
  'note:rate': [
    { label: 'Read notes others have written and rate them', customId: 'nav:list:notes', emoji: '\u{1F4DD}' },
  ],
  'clear:notes': [
    { label: 'Read notes others have written and rate them', customId: 'nav:list:notes', emoji: '\u{1F4DD}' },
    { label: 'See note requests and write a note', customId: 'nav:list:requests', emoji: '\u{1F4CB}' },
  ],
  'clear:requests': [
    { label: 'Read notes others have written and rate them', customId: 'nav:list:notes', emoji: '\u{1F4DD}' },
    { label: 'See note requests and write a note', customId: 'nav:list:requests', emoji: '\u{1F4CB}' },
  ],
  'config': [
    { label: 'Status', customId: 'nav:status-bot', emoji: '\u{1F4CA}' },
    { label: 'About', customId: 'nav:about-opennotes', emoji: '\u2139\uFE0F' },
  ],
  'status-bot': [
    { label: 'Read notes others have written and rate them', customId: 'nav:list:notes', emoji: '\u{1F4DD}' },
    { label: 'About', customId: 'nav:about-opennotes', emoji: '\u2139\uFE0F' },
  ],
  'about-opennotes': [
    { label: 'Read notes others have written and rate them', customId: 'nav:list:notes', emoji: '\u{1F4DD}' },
    { label: 'See note requests and write a note', customId: 'nav:list:requests', emoji: '\u{1F4CB}' },
  ],
  'note-request-context': [
    { label: 'See note requests and write a note', customId: 'nav:list:requests', emoji: '\u{1F4CB}' },
  ],
};

export function buildMenuButton(): ButtonBuilder {
  return new ButtonBuilder()
    .setCustomId('nav:menu')
    .setLabel('Menu')
    .setStyle(ButtonStyle.Secondary)
    .setEmoji('\u{1F4D6}');
}

export function buildBackButton(): ButtonBuilder {
  return new ButtonBuilder()
    .setCustomId('nav:back')
    .setLabel('Back')
    .setStyle(ButtonStyle.Secondary)
    .setEmoji('\u25C0');
}

export function buildFullMenuButton(): ButtonBuilder {
  return new ButtonBuilder()
    .setCustomId('nav:hub')
    .setLabel('Full Menu')
    .setStyle(ButtonStyle.Secondary)
    .setEmoji('\u{1F3E0}');
}

export function buildContextualNav(commandContext: string): ActionRowBuilder<ButtonBuilder> {
  const actions = NAV_GRAPH[commandContext] ?? [];
  const row = new ActionRowBuilder<ButtonBuilder>();
  row.addComponents(buildMenuButton());
  for (const action of actions) {
    const btn = new ButtonBuilder()
      .setCustomId(action.customId)
      .setLabel(action.label)
      .setStyle(ButtonStyle.Secondary);
    if (action.emoji) {
      btn.setEmoji(action.emoji);
    }
    row.addComponents(btn);
  }
  return row;
}

export const HUB_ACTIONS: NavAction[] = [
  { label: 'Read notes others have written and rate them', customId: 'nav:list:notes', emoji: '\u{1F4DD}' },
  { label: 'See note requests and write a note', customId: 'nav:list:requests', emoji: '\u{1F4CB}' },
  { label: 'Vibecheck Scan', customId: 'nav:vibecheck:scan', emoji: '\u{1F50D}' },
  { label: 'Status', customId: 'nav:status-bot', emoji: '\u{1F4CA}' },
  { label: 'About', customId: 'nav:about-opennotes', emoji: '\u2139\uFE0F' },
];

export function buildNavHub(): ActionRowBuilder<ButtonBuilder>[] {
  const rows: ActionRowBuilder<ButtonBuilder>[] = [];
  let currentRow = new ActionRowBuilder<ButtonBuilder>();
  for (const action of HUB_ACTIONS) {
    if (currentRow.components.length >= 5) {
      rows.push(currentRow);
      currentRow = new ActionRowBuilder<ButtonBuilder>();
    }
    const btn = new ButtonBuilder()
      .setCustomId(action.customId)
      .setLabel(action.label)
      .setStyle(ButtonStyle.Primary);
    if (action.emoji) {
      btn.setEmoji(action.emoji);
    }
    currentRow.addComponents(btn);
  }
  if (currentRow.components.length > 0) {
    rows.push(currentRow);
  }
  return rows;
}
