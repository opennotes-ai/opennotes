import { ComponentType, ContainerBuilder, Message, TextDisplayBuilder } from 'discord.js';
import {
  createContainer,
  createSmallSeparator,
  createDivider,
  V2_COLORS,
} from '../utils/v2-components.js';

export const WELCOME_MESSAGE_REVISION = '2025-12-24.1';

export function buildWelcomeContainer(): ContainerBuilder {
  return createContainer(V2_COLORS.PRIMARY)
    .addTextDisplayComponents(
      new TextDisplayBuilder().setContent('## About OpenNotes')
    )
    .addTextDisplayComponents(
      new TextDisplayBuilder().setContent(
        'Open Notes is a community moderation tool that helps identify and surface helpful context about potentially misleading content.'
      )
    )
    .addSeparatorComponents(createDivider())
    .addTextDisplayComponents(
      new TextDisplayBuilder().setContent(
        '**:pencil: How It Works**\n' +
        '- Community members can write notes providing context on messages\n' +
        '- Notes are scored based on helpfulness and accuracy\n' +
        '- High-quality notes are surfaced to help others understand context'
      )
    )
    .addSeparatorComponents(createSmallSeparator())
    .addTextDisplayComponents(
      new TextDisplayBuilder().setContent(
        '**:star: Note Submission**\n' +
        '**Request a note:** Right-click a message > **Apps** > **Request Note** (or `/note request <message-id>`)\n' +
        '**Write a note:** Use `/note write <message-id>` to add context to a message\n\n' +
        'Good notes should:\n' +
        '- Provide factual context\n' +
        '- Be helpful and constructive\n' +
        '- Cite sources when possible'
      )
    )
    .addSeparatorComponents(createSmallSeparator())
    .addTextDisplayComponents(
      new TextDisplayBuilder().setContent(
        '**:clipboard: Commands**\n' +
        '`/note write <message-id>` - Write a community note\n' +
        '`/note request <message-id>` - Request a note on a message\n' +
        '`/note view <message-id>` - View notes for a message\n' +
        '`/note rate <note-id> <helpful>` - Rate a note\n' +
        '`/note score <note-id>` - View a note\'s score\n' +
        '`/list notes` - Browse notes awaiting your rating\n' +
        '`/list requests` - Browse pending note requests\n' +
        '`/list top-notes` - View highest-scored notes'
      )
    )
    .addSeparatorComponents(createSmallSeparator())
    .addTextDisplayComponents(
      new TextDisplayBuilder().setContent(
        '**:dart: Scoring System**\n' +
        'Community members rate notes as helpful or not helpful. Notes with high ratings are more visible and help moderate content collaboratively.'
      )
    )
    .addSeparatorComponents(createSmallSeparator())
    .addTextDisplayComponents(
      new TextDisplayBuilder().setContent(
        '**:shield: Community Moderation**\n' +
        'Open Notes empowers communities to self-moderate by surfacing context rather than removing content. This promotes transparency and informed discussion.'
      )
    )
    .addSeparatorComponents(createDivider())
    .addTextDisplayComponents(
      new TextDisplayBuilder().setContent('*Open Notes - Community-powered context*')
    )
    .addTextDisplayComponents(
      new TextDisplayBuilder().setContent(`-# Revision ${WELCOME_MESSAGE_REVISION}`)
    );
}

const REVISION_PATTERN = /Revision (\d{4}-\d{2}-\d{2}\.\d+)/;

export function extractRevisionFromMessage(message: Message): string | null {
  const container = message.components?.[0];
  if (!container || !('components' in container)) {
    return null;
  }

  for (const component of container.components) {
    const data = component.toJSON();
    if (data.type === ComponentType.TextDisplay && typeof data.content === 'string') {
      const match = data.content.match(REVISION_PATTERN);
      if (match) {
        return match[1];
      }
    }
  }

  return null;
}
