import { Factory } from 'fishery';
import { jest } from '@jest/globals';
import { ChannelType, PermissionsBitField, PermissionFlagsBits } from 'discord.js';

export interface MockDiscordChannel {
  id: string;
  name: string;
  type: ChannelType;
  guildId: string | null;
  guild?: unknown;
  isTextBased: ReturnType<typeof jest.fn<() => boolean>>;
  isDMBased: ReturnType<typeof jest.fn<() => boolean>>;
  isThread: ReturnType<typeof jest.fn<() => boolean>>;
  isVoiceBased: ReturnType<typeof jest.fn<() => boolean>>;
  permissionsFor: ReturnType<typeof jest.fn<(userOrRole?: any) => PermissionsBitField | null>>;
  permissionOverwrites: {
    set: ReturnType<typeof jest.fn<(overwrites: unknown[]) => Promise<void>>>;
  };
  send: ReturnType<typeof jest.fn<(content: any) => Promise<any>>>;
  delete: ReturnType<typeof jest.fn<() => Promise<void>>>;
  messages: {
    fetch: ReturnType<typeof jest.fn<(messageId: string) => Promise<any>>>;
  };
  threads: {
    create: ReturnType<typeof jest.fn<(options: any) => Promise<any>>>;
  };
}

export interface DiscordChannelTransientParams {
  isTextChannel?: boolean;
  isDM?: boolean;
  isThread?: boolean;
  hasPermissions?: boolean;
  missingPermissions?: Array<'SendMessages' | 'CreatePublicThreads' | 'ViewChannel'>;
  guild?: unknown;
}

export const discordChannelFactory = Factory.define<MockDiscordChannel, DiscordChannelTransientParams>(
  ({ sequence, transientParams }) => {
    const {
      isTextChannel = true,
      isDM = false,
      isThread = false,
      hasPermissions = true,
      missingPermissions = [],
      guild,
    } = transientParams;

    const channelType = isDM
      ? ChannelType.DM
      : isThread
        ? ChannelType.PublicThread
        : ChannelType.GuildText;

    const basePermissions = PermissionFlagsBits.SendMessages | PermissionFlagsBits.CreatePublicThreads | PermissionFlagsBits.ViewChannel;

    let effectivePermissions = basePermissions;
    for (const missing of missingPermissions) {
      switch (missing) {
        case 'SendMessages':
          effectivePermissions &= ~PermissionFlagsBits.SendMessages;
          break;
        case 'CreatePublicThreads':
          effectivePermissions &= ~PermissionFlagsBits.CreatePublicThreads;
          break;
        case 'ViewChannel':
          effectivePermissions &= ~PermissionFlagsBits.ViewChannel;
          break;
      }
    }

    const permissionsFor = jest.fn<(userOrRole?: any) => PermissionsBitField | null>(() => {
      if (!hasPermissions) {
        return null;
      }
      return new PermissionsBitField(effectivePermissions);
    });

    const mockThread = {
      id: `thread-${sequence}`,
      name: `Thread ${sequence}`,
      send: jest.fn<(content: any) => Promise<any>>().mockResolvedValue({ id: 'thread-message-id' }),
    };

    return {
      id: `channel-${sequence}`,
      name: `channel-${sequence}`,
      type: channelType,
      guildId: isDM ? null : `guild-${sequence}`,
      guild,
      isTextBased: jest.fn<() => boolean>().mockReturnValue(isTextChannel),
      isDMBased: jest.fn<() => boolean>().mockReturnValue(isDM),
      isThread: jest.fn<() => boolean>().mockReturnValue(isThread),
      isVoiceBased: jest.fn<() => boolean>().mockReturnValue(false),
      permissionsFor,
      permissionOverwrites: {
        set: jest.fn<(overwrites: unknown[]) => Promise<void>>().mockResolvedValue(undefined),
      },
      send: jest.fn<(content: any) => Promise<any>>().mockResolvedValue({ id: 'message-id' }),
      delete: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
      messages: {
        fetch: jest.fn<(messageId: string) => Promise<any>>().mockResolvedValue({
          id: 'fetched-message-id',
          content: 'Fetched message content',
        }),
      },
      threads: {
        create: jest.fn<(options: any) => Promise<any>>().mockResolvedValue(mockThread),
      },
    };
  }
);
