import {
  SlashCommandBuilder,
  ChatInputCommandInteraction,
  TextDisplayBuilder,
} from 'discord.js';
import { logger } from '../logger.js';
import { generateErrorId, extractErrorDetails, formatErrorForUser } from '../lib/errors.js';
import {
  createContainer,
  createSmallSeparator,
  createDivider,
  v2MessageFlags,
  V2_COLORS,
} from '../utils/v2-components.js';

export const data = new SlashCommandBuilder()
  .setName('about-opennotes')
  .setDescription('Learn about Open Notes and how it works');

export async function execute(interaction: ChatInputCommandInteraction): Promise<void> {
  const errorId = generateErrorId();
  const userId = interaction.user.id;
  const guildId = interaction.guildId;

  try {
    logger.info('Executing about-opennotes command', {
      error_id: errorId,
      command: 'about-opennotes',
      user_id: userId,
      community_server_id: guildId,
    });

    await interaction.deferReply({ flags: v2MessageFlags({ ephemeral: true }) });

    const container = createContainer(V2_COLORS.PRIMARY)
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
      );

    await interaction.editReply({
      components: [container],
      flags: v2MessageFlags({ ephemeral: true }),
    });

    logger.info('About command completed successfully', {
      error_id: errorId,
      command: 'about-opennotes',
      user_id: userId,
    });
  } catch (error) {
    const errorDetails = extractErrorDetails(error);

    logger.error('Unexpected error in about-opennotes command', {
      error_id: errorId,
      command: 'about-opennotes',
      user_id: userId,
      community_server_id: guildId,
      error: errorDetails.message,
      error_type: errorDetails.type,
      stack: errorDetails.stack,
    });

    await interaction.editReply({
      content: formatErrorForUser(errorId, 'Failed to display information about OpenNotes.'),
    });
  }
}
