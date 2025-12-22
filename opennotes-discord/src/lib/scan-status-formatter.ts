import {
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
} from 'discord.js';
import type {
  LatestScanResponse,
  FlaggedMessageResource,
} from './api-client.js';
import {
  formatMatchScore,
  formatMessageLink,
  truncateContent,
} from './bulk-scan-executor.js';

export interface FormatScanStatusOptions {
  scan: LatestScanResponse;
  guildId: string;
  days?: number;
  warningMessage?: string;
  includeButtons?: boolean;
}

export interface FormatScanStatusResult {
  content: string;
  components?: ActionRowBuilder<ButtonBuilder>[];
}

export function formatScanStatus(options: FormatScanStatusOptions): FormatScanStatusResult {
  const { scan, guildId, days, warningMessage, includeButtons = false } = options;
  const scanId = scan.data.id;
  const status = scan.data.attributes.status;
  const messagesScanned = scan.data.attributes.messages_scanned;
  const flaggedMessages = scan.included || [];

  const daysText = days !== undefined
    ? `**Period:** Last ${days} day${days !== 1 ? 's' : ''}\n`
    : '';

  const warningText = warningMessage
    ? `\n\n**Warning:** ${warningMessage}`
    : '';

  if (status === 'pending') {
    return {
      content: `**Scan Status: Pending**\n\n` +
        `**Scan ID:** \`${scanId}\`\n` +
        daysText +
        `The scan is pending and waiting to be processed.${warningText}`,
    };
  }

  if (status === 'in_progress') {
    return {
      content: `**Scan Status: In Progress**\n\n` +
        `**Scan ID:** \`${scanId}\`\n` +
        daysText +
        `**Messages scanned so far:** ${messagesScanned}\n\n` +
        `The scan is currently in progress...${warningText}`,
    };
  }

  if (status === 'failed') {
    return {
      content: `**Scan Status: Failed**\n\n` +
        `**Scan ID:** \`${scanId}\`\n` +
        daysText +
        `The scan failed. Please try again later.${warningText}`,
    };
  }

  if (flaggedMessages.length === 0) {
    return {
      content: `**Scan Complete**\n\n` +
        `**Scan ID:** \`${scanId}\`\n` +
        daysText +
        `**Messages scanned:** ${messagesScanned}\n\n` +
        `No flagged content found. No potential misinformation was detected.${warningText}`,
    };
  }

  const resultsContent = formatFlaggedMessagesList(flaggedMessages, guildId);
  const moreCount = flaggedMessages.length > 10 ? flaggedMessages.length - 10 : 0;
  const moreText = moreCount > 0 ? `\n\n_...and ${moreCount} more flagged messages_` : '';

  const content = `**Scan Complete**\n\n` +
    `**Scan ID:** \`${scanId}\`\n` +
    daysText +
    `**Messages scanned:** ${messagesScanned}\n` +
    `**Flagged:** ${flaggedMessages.length}\n\n` +
    `${resultsContent}${moreText}${warningText}`;

  if (includeButtons && flaggedMessages.length > 0) {
    const createButton = new ButtonBuilder()
      .setCustomId(`vibecheck_create:${scanId}`)
      .setLabel('Create Note Requests')
      .setStyle(ButtonStyle.Primary);

    const dismissButton = new ButtonBuilder()
      .setCustomId(`vibecheck_dismiss:${scanId}`)
      .setLabel('Dismiss')
      .setStyle(ButtonStyle.Secondary);

    const row = new ActionRowBuilder<ButtonBuilder>().addComponents(createButton, dismissButton);

    return {
      content,
      components: [row],
    };
  }

  return { content };
}

function formatFlaggedMessagesList(flaggedMessages: FlaggedMessageResource[], guildId: string): string {
  return flaggedMessages.slice(0, 10).map((msg, index) => {
    const messageLink = formatMessageLink(guildId, msg.attributes.channel_id, msg.id);
    const confidence = formatMatchScore(msg.attributes.match_score);
    const preview = truncateContent(msg.attributes.content);

    return `**${index + 1}.** [Message](${messageLink})\n` +
      `   Confidence: **${confidence}**\n` +
      `   Matched: "${msg.attributes.matched_claim}"\n` +
      `   Preview: "${preview}"`;
  }).join('\n\n');
}
