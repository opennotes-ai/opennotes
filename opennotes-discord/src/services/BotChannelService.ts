import {
  ChannelType,
  Guild,
  GuildMember,
  PermissionFlagsBits,
  Role,
  TextChannel,
} from 'discord.js';
import { logger } from '../logger.js';
import { ConfigKey } from '../lib/config-schema.js';
import type { GuildConfigService } from './GuildConfigService.js';

export interface EnsureChannelResult {
  channel: TextChannel;
  wasCreated: boolean;
}

export class BotChannelService {
  findChannel(guild: Guild, channelName: string): TextChannel | undefined {
    const lowerName = channelName.toLowerCase();
    return guild.channels.cache.find(
      (channel): channel is TextChannel =>
        channel.type === ChannelType.GuildText && channel.name.toLowerCase() === lowerName
    );
  }

  findRole(guild: Guild, roleName: string): Role | undefined {
    const lowerName = roleName.toLowerCase();
    return guild.roles.cache.find((role) => role.name.toLowerCase() === lowerName);
  }

  async createChannel(guild: Guild, channelName: string): Promise<TextChannel> {
    try {
      const channel = await guild.channels.create({
        name: channelName,
        type: ChannelType.GuildText,
        topic: 'OpenNotes bot channel - use slash commands to interact with the bot',
      });

      logger.info('Created bot channel', {
        guildId: guild.id,
        channelId: channel.id,
        channelName,
      });

      return channel;
    } catch (error) {
      logger.error('Failed to create bot channel', {
        guildId: guild.id,
        channelName,
        error: error instanceof Error ? error.message : String(error),
      });
      throw error;
    }
  }

  async deleteChannel(guild: Guild, channel: TextChannel): Promise<void> {
    try {
      await channel.delete();

      logger.info('Deleted bot channel', {
        guildId: guild.id,
        channelId: channel.id,
      });
    } catch (error) {
      logger.error('Failed to delete bot channel', {
        guildId: guild.id,
        channelId: channel.id,
        error: error instanceof Error ? error.message : String(error),
      });
      throw error;
    }
  }

  async setupPermissions(
    channel: TextChannel,
    openNotesRole: Role,
    botMember: GuildMember
  ): Promise<void> {
    try {
      const everyoneRoleId = channel.guild.roles.everyone.id;

      await channel.permissionOverwrites.set([
        {
          id: everyoneRoleId,
          allow: [
            PermissionFlagsBits.ViewChannel,
            PermissionFlagsBits.UseApplicationCommands,
            PermissionFlagsBits.ReadMessageHistory,
          ],
          deny: [PermissionFlagsBits.SendMessages],
        },
        {
          id: openNotesRole.id,
          allow: [
            PermissionFlagsBits.ViewChannel,
            PermissionFlagsBits.SendMessages,
            PermissionFlagsBits.UseApplicationCommands,
            PermissionFlagsBits.ReadMessageHistory,
          ],
        },
        {
          id: botMember.id,
          allow: [
            PermissionFlagsBits.ViewChannel,
            PermissionFlagsBits.ManageChannels,
            PermissionFlagsBits.SendMessages,
            PermissionFlagsBits.ManageMessages,
            PermissionFlagsBits.EmbedLinks,
            PermissionFlagsBits.AttachFiles,
            PermissionFlagsBits.ReadMessageHistory,
            PermissionFlagsBits.UseApplicationCommands,
          ],
        },
      ]);

      logger.info('Set up bot channel permissions', {
        channelId: channel.id,
        roleId: openNotesRole.id,
        botMemberId: botMember.id,
      });
    } catch (error) {
      logger.error('Failed to set up bot channel permissions', {
        channelId: channel.id,
        roleId: openNotesRole.id,
        error: error instanceof Error ? error.message : String(error),
      });
      throw error;
    }
  }

  async ensureChannelExists(
    guild: Guild,
    guildConfigService: GuildConfigService
  ): Promise<EnsureChannelResult> {
    const channelName = (await guildConfigService.get(
      guild.id,
      ConfigKey.BOT_CHANNEL_NAME
    )) as string;

    const existingChannel = this.findChannel(guild, channelName);
    if (existingChannel) {
      logger.debug('Bot channel already exists', {
        guildId: guild.id,
        channelId: existingChannel.id,
        channelName,
      });
      return { channel: existingChannel, wasCreated: false };
    }

    const channel = await this.createChannel(guild, channelName);

    const roleName = (await guildConfigService.get(
      guild.id,
      ConfigKey.OPENNOTES_ROLE_NAME
    )) as string;
    const openNotesRole = this.findRole(guild, roleName);

    if (!openNotesRole) {
      logger.warn('OpenNotes role not found, skipping permission setup', {
        guildId: guild.id,
        roleName,
      });
      return { channel, wasCreated: true };
    }

    const botMember = guild.members.me;
    if (botMember) {
      await this.setupPermissions(channel, openNotesRole, botMember);
    }

    return { channel, wasCreated: true };
  }
}
