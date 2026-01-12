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

export interface MigrateChannelResult {
  newChannel: TextChannel;
  oldChannelDeleted: boolean;
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

  validateChannelName(name: string): void {
    if (name.length < 1 || name.length > 100) {
      throw new Error('Channel name must be 1-100 characters');
    }
    if (!/^[a-z0-9-_]+$/.test(name)) {
      throw new Error(
        'Channel name can only contain lowercase letters, numbers, hyphens, and underscores'
      );
    }
  }

  async createChannel(guild: Guild, channelName: string): Promise<TextChannel> {
    this.validateChannelName(channelName);

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
          deny: [
            PermissionFlagsBits.ViewChannel,
            PermissionFlagsBits.SendMessages,
          ],
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

    let channel: TextChannel;
    try {
      channel = await this.createChannel(guild, channelName);
    } catch (error) {
      if (this.isDuplicateChannelError(error)) {
        logger.info('Race condition detected: channel was created by another process, retrying lookup', {
          guildId: guild.id,
          channelName,
        });
        const retryChannel = this.findChannel(guild, channelName);
        if (retryChannel) {
          return { channel: retryChannel, wasCreated: false };
        }
      }
      throw error;
    }

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

    const botMember = await this.fetchBotMember(guild);
    if (botMember) {
      await this.setupPermissions(channel, openNotesRole, botMember);
    }

    return { channel, wasCreated: true };
  }

  private isDuplicateChannelError(error: unknown): boolean {
    return (
      error !== null &&
      typeof error === 'object' &&
      'code' in error &&
      (error as { code: number }).code === 50035
    );
  }

  private async fetchBotMember(guild: Guild): Promise<GuildMember | null> {
    if (guild.members.me) {
      return guild.members.me;
    }

    try {
      return await guild.members.fetchMe();
    } catch (error) {
      logger.warn('Could not fetch bot member, skipping permission setup', {
        guildId: guild.id,
        error: error instanceof Error ? error.message : String(error),
      });
      return null;
    }
  }

  async migrateChannel(
    guild: Guild,
    oldChannelName: string,
    newChannelName: string,
    guildConfigService: GuildConfigService
  ): Promise<MigrateChannelResult> {
    logger.info('Starting bot channel migration', {
      guildId: guild.id,
      oldChannelName,
      newChannelName,
    });

    const oldChannel = this.findChannel(guild, oldChannelName);

    const newChannel = await this.createChannel(guild, newChannelName);

    const roleName = (await guildConfigService.get(
      guild.id,
      ConfigKey.OPENNOTES_ROLE_NAME
    )) as string;
    const openNotesRole = this.findRole(guild, roleName);

    if (openNotesRole) {
      const botMember = await this.fetchBotMember(guild);
      if (botMember) {
        await this.setupPermissions(newChannel, openNotesRole, botMember);
      }
    } else {
      logger.warn('OpenNotes role not found during migration, skipping permission setup', {
        guildId: guild.id,
        roleName,
      });
    }

    let oldChannelDeleted = false;
    if (oldChannel) {
      try {
        await this.deleteChannel(guild, oldChannel);
        oldChannelDeleted = true;
      } catch (error) {
        logger.error('Failed to delete old channel during migration', {
          guildId: guild.id,
          oldChannelId: oldChannel.id,
          oldChannelName,
          newChannelId: newChannel.id,
          newChannelName,
          error: error instanceof Error ? error.message : String(error),
        });
      }
    }

    logger.info('Bot channel migration completed', {
      guildId: guild.id,
      oldChannelName,
      newChannelName,
      newChannelId: newChannel.id,
      oldChannelDeleted,
    });

    return { newChannel, oldChannelDeleted };
  }
}
