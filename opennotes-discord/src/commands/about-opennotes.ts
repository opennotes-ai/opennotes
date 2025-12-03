import {
  SlashCommandBuilder,
  ChatInputCommandInteraction,
  EmbedBuilder,
  MessageFlags,
} from 'discord.js';
import { logger } from '../logger.js';
import { generateErrorId, extractErrorDetails, formatErrorForUser } from '../lib/errors.js';

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

    await interaction.deferReply({ flags: MessageFlags.Ephemeral });

    const embed = new EmbedBuilder()
      .setColor(0x5865F2)
      .setTitle('About OpenNotes')
      .setDescription(
        'Open Notes is a community moderation tool that helps identify and surface helpful context about potentially misleading content.'
      )
      .addFields(
        {
          name: '📝 How It Works',
          value:
            '• Community members can write notes providing context on messages\n' +
            '• Notes are scored based on helpfulness and accuracy\n' +
            '• High-quality notes are surfaced to help others understand context',
          inline: false,
        },
        {
          name: '⭐ Note Submission',
          value:
            '**Request a note:** Right-click a message → **Apps** → **Request Note** (or `/note request <message-id>`)\n' +
            '**Write a note:** Use `/note write <message-id>` to add context to a message\n\n' +
            'Good notes should:\n' +
            '• Provide factual context\n' +
            '• Be helpful and constructive\n' +
            '• Cite sources when possible',
          inline: false,
        },
        {
          name: '📋 Commands',
          value:
            '`/note write <message-id>` - Write a community note\n' +
            '`/note request <message-id>` - Request a note on a message\n' +
            '`/note view <message-id>` - View notes for a message\n' +
            '`/note rate <note-id> <helpful>` - Rate a note\n' +
            '`/note score <note-id>` - View a note\'s score\n' +
            '`/list notes` - Browse notes awaiting your rating\n' +
            '`/list requests` - Browse pending note requests\n' +
            '`/list top-notes` - View highest-scored notes',
          inline: false,
        },
        {
          name: '🎯 Scoring System',
          value:
            'Community members rate notes as helpful or not helpful. Notes with high ratings are more visible and help moderate content collaboratively.',
          inline: false,
        },
        {
          name: '🛡️ Community Moderation',
          value:
            'Open Notes empowers communities to self-moderate by surfacing context rather than removing content. This promotes transparency and informed discussion.',
          inline: false,
        }
      )
      .setFooter({
        text: 'Open Notes - Community-powered context',
      })
      .setTimestamp();

    await interaction.editReply({ embeds: [embed] });

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
