import {
  ChatInputCommandInteraction,
  Guild,
  TextChannel,
  MessageFlags,
} from 'discord.js';
import { BotChannelService } from '../services/BotChannelService.js';
import { GuildConfigService } from '../services/GuildConfigService.js';
import { ConfigKey } from './config-schema.js';
import { logger } from '../logger.js';

export interface BotChannelCheckResult {
  isInBotChannel: boolean;
  botChannel: TextChannel | null;
  botChannelName: string;
}

export async function checkBotChannel(
  interaction: ChatInputCommandInteraction,
  botChannelService: BotChannelService,
  guildConfigService: GuildConfigService
): Promise<BotChannelCheckResult> {
  const guild = interaction.guild;

  if (!guild) {
    return {
      isInBotChannel: false,
      botChannel: null,
      botChannelName: 'open-notes',
    };
  }

  const botChannelName = (await guildConfigService.get(
    guild.id,
    ConfigKey.BOT_CHANNEL_NAME
  )) as string;

  const botChannel = botChannelService.findChannel(guild, botChannelName);

  if (!botChannel) {
    return {
      isInBotChannel: false,
      botChannel: null,
      botChannelName,
    };
  }

  const isInBotChannel = interaction.channelId === botChannel.id;

  return {
    isInBotChannel,
    botChannel,
    botChannelName,
  };
}

export interface BotChannelRedirectResult {
  shouldProceed: boolean;
  botChannel: TextChannel | null;
}

export async function getBotChannelOrRedirect(
  interaction: ChatInputCommandInteraction,
  botChannelService: BotChannelService,
  guildConfigService: GuildConfigService
): Promise<BotChannelRedirectResult> {
  const { isInBotChannel, botChannel, botChannelName } = await checkBotChannel(
    interaction,
    botChannelService,
    guildConfigService
  );

  if (isInBotChannel && botChannel) {
    return {
      shouldProceed: true,
      botChannel,
    };
  }

  if (botChannel) {
    logger.info('Redirecting user to bot channel', {
      userId: interaction.user.id,
      guildId: interaction.guildId,
      fromChannelId: interaction.channelId,
      botChannelId: botChannel.id,
      command: interaction.commandName,
    });

    const redirectMessage = `Please use this command in ${botChannel.toString()}`;

    if (interaction.deferred) {
      await interaction.editReply({
        content: redirectMessage,
      });
    } else {
      await interaction.reply({
        content: redirectMessage,
        flags: MessageFlags.Ephemeral,
      });
    }

    return {
      shouldProceed: false,
      botChannel,
    };
  }

  logger.warn('Bot channel not found for guild', {
    userId: interaction.user.id,
    guildId: interaction.guildId,
    expectedChannelName: botChannelName,
    command: interaction.commandName,
  });

  const noChannelMessage = `The bot channel "${botChannelName}" was not found. Please ask an administrator to set up the OpenNotes bot channel.`;

  if (interaction.deferred) {
    await interaction.editReply({
      content: noChannelMessage,
    });
  } else {
    await interaction.reply({
      content: noChannelMessage,
      flags: MessageFlags.Ephemeral,
    });
  }

  return {
    shouldProceed: false,
    botChannel: null,
  };
}

export async function ensureBotChannel(
  guild: Guild,
  botChannelService: BotChannelService,
  guildConfigService: GuildConfigService
): Promise<TextChannel | null> {
  try {
    const result = await botChannelService.ensureChannelExists(guild, guildConfigService);
    return result.channel;
  } catch (error) {
    logger.error('Failed to ensure bot channel exists', {
      guildId: guild.id,
      error: error instanceof Error ? error.message : String(error),
    });
    return null;
  }
}
