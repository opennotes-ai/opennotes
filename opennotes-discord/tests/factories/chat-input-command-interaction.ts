import { Factory } from 'fishery';
import { jest } from '@jest/globals';
import { ApplicationCommandType } from 'discord.js';
import { discordUserFactory, type MockDiscordUser } from './discord-user.js';
import { discordMemberFactory, type MockDiscordMember } from './discord-member.js';
import { discordGuildFactory, type MockDiscordGuild } from './discord-guild.js';
import { discordChannelFactory, type MockDiscordChannel } from './discord-channel.js';

export interface MockChatInputCommandInteraction {
  id: string;
  commandName: string;
  commandType: ApplicationCommandType.ChatInput;
  user: MockDiscordUser;
  member: MockDiscordMember | null;
  guild: MockDiscordGuild | null;
  guildId: string | null;
  channel: MockDiscordChannel | null;
  channelId: string | null;
  deferred: boolean;
  replied: boolean;
  options: MockCommandInteractionOptions;
  reply: ReturnType<typeof jest.fn<(opts: any) => Promise<any>>>;
  deferReply: ReturnType<typeof jest.fn<(opts?: any) => Promise<void>>>;
  editReply: ReturnType<typeof jest.fn<(opts: any) => Promise<any>>>;
  followUp: ReturnType<typeof jest.fn<(...args: any[]) => Promise<any>>>;
  deleteReply: ReturnType<typeof jest.fn<(...args: any[]) => Promise<void>>>;
  isChatInputCommand: ReturnType<typeof jest.fn<() => boolean>>;
  inGuild: ReturnType<typeof jest.fn<() => boolean>>;
  inCachedGuild: ReturnType<typeof jest.fn<() => boolean>>;
}

export interface MockCommandInteractionOptions {
  getSubcommand: ReturnType<typeof jest.fn<(required?: boolean) => string | null>>;
  getSubcommandGroup: ReturnType<typeof jest.fn<(required?: boolean) => string | null>>;
  getString: ReturnType<typeof jest.fn<(name: string, required?: boolean) => string | null>>;
  getBoolean: ReturnType<typeof jest.fn<(name: string, required?: boolean) => boolean | null>>;
  getInteger: ReturnType<typeof jest.fn<(name: string, required?: boolean) => number | null>>;
  getNumber: ReturnType<typeof jest.fn<(name: string, required?: boolean) => number | null>>;
  getUser: ReturnType<typeof jest.fn<(name: string, required?: boolean) => MockDiscordUser | null>>;
  getMember: ReturnType<typeof jest.fn<(name: string) => MockDiscordMember | null>>;
  getChannel: ReturnType<typeof jest.fn<(name: string, required?: boolean) => MockDiscordChannel | null>>;
  getRole: ReturnType<typeof jest.fn<(name: string, required?: boolean) => any>>;
  getAttachment: ReturnType<typeof jest.fn<(name: string, required?: boolean) => any>>;
  getMentionable: ReturnType<typeof jest.fn<(name: string, required?: boolean) => any>>;
}

export interface ChatInputCommandInteractionTransientParams {
  subcommand?: string | null;
  subcommandGroup?: string | null;
  stringOptions?: Record<string, string | null>;
  booleanOptions?: Record<string, boolean | null>;
  integerOptions?: Record<string, number | null>;
  numberOptions?: Record<string, number | null>;
  userOptions?: Record<string, MockDiscordUser | null>;
  memberOptions?: Record<string, MockDiscordMember | null>;
  channelOptions?: Record<string, MockDiscordChannel | null>;
  roleOptions?: Record<string, any>;
  attachmentOptions?: Record<string, any>;
  isDeferred?: boolean;
  isReplied?: boolean;
  inGuild?: boolean;
}

function createOptionsMock(transientParams: ChatInputCommandInteractionTransientParams): MockCommandInteractionOptions {
  const {
    subcommand = null,
    subcommandGroup = null,
    stringOptions = {},
    booleanOptions = {},
    integerOptions = {},
    numberOptions = {},
    userOptions = {},
    memberOptions = {},
    channelOptions = {},
    roleOptions = {},
    attachmentOptions = {},
  } = transientParams;

  return {
    getSubcommand: jest.fn<(required?: boolean) => string | null>().mockImplementation((required?: boolean) => {
      if (required && subcommand === null) {
        throw new Error('Subcommand is required but not provided');
      }
      return subcommand;
    }),
    getSubcommandGroup: jest.fn<(required?: boolean) => string | null>().mockImplementation((required?: boolean) => {
      if (required && subcommandGroup === null) {
        throw new Error('Subcommand group is required but not provided');
      }
      return subcommandGroup;
    }),
    getString: jest.fn<(name: string, required?: boolean) => string | null>().mockImplementation((name: string, required?: boolean) => {
      const value = stringOptions[name] ?? null;
      if (required && value === null) {
        throw new Error(`String option "${name}" is required but not provided`);
      }
      return value;
    }),
    getBoolean: jest.fn<(name: string, required?: boolean) => boolean | null>().mockImplementation((name: string, required?: boolean) => {
      const value = booleanOptions[name] ?? null;
      if (required && value === null) {
        throw new Error(`Boolean option "${name}" is required but not provided`);
      }
      return value;
    }),
    getInteger: jest.fn<(name: string, required?: boolean) => number | null>().mockImplementation((name: string, required?: boolean) => {
      const value = integerOptions[name] ?? null;
      if (required && value === null) {
        throw new Error(`Integer option "${name}" is required but not provided`);
      }
      return value;
    }),
    getNumber: jest.fn<(name: string, required?: boolean) => number | null>().mockImplementation((name: string, required?: boolean) => {
      const value = numberOptions[name] ?? null;
      if (required && value === null) {
        throw new Error(`Number option "${name}" is required but not provided`);
      }
      return value;
    }),
    getUser: jest.fn<(name: string, required?: boolean) => MockDiscordUser | null>().mockImplementation((name: string, required?: boolean) => {
      const value = userOptions[name] ?? null;
      if (required && value === null) {
        throw new Error(`User option "${name}" is required but not provided`);
      }
      return value;
    }),
    getMember: jest.fn<(name: string) => MockDiscordMember | null>().mockImplementation((name: string) => {
      return memberOptions[name] ?? null;
    }),
    getChannel: jest.fn<(name: string, required?: boolean) => MockDiscordChannel | null>().mockImplementation((name: string, required?: boolean) => {
      const value = channelOptions[name] ?? null;
      if (required && value === null) {
        throw new Error(`Channel option "${name}" is required but not provided`);
      }
      return value;
    }),
    getRole: jest.fn<(name: string, required?: boolean) => any>().mockImplementation((name: string, required?: boolean) => {
      const value = roleOptions[name] ?? null;
      if (required && value === null) {
        throw new Error(`Role option "${name}" is required but not provided`);
      }
      return value;
    }),
    getAttachment: jest.fn<(name: string, required?: boolean) => any>().mockImplementation((name: string, required?: boolean) => {
      const value = attachmentOptions[name] ?? null;
      if (required && value === null) {
        throw new Error(`Attachment option "${name}" is required but not provided`);
      }
      return value;
    }),
    getMentionable: jest.fn<(name: string, required?: boolean) => any>().mockReturnValue(null),
  };
}

export const chatInputCommandInteractionFactory = Factory.define<
  MockChatInputCommandInteraction,
  ChatInputCommandInteractionTransientParams
>(({ sequence, transientParams, associations }) => {
  const {
    isDeferred = false,
    isReplied = false,
    inGuild: inGuildParam = true,
  } = transientParams;

  const user = associations.user ?? discordUserFactory.build();
  const member = inGuildParam
    ? (associations.member ?? discordMemberFactory.build({ user }))
    : null;
  const guild = inGuildParam
    ? (associations.guild ?? discordGuildFactory.build())
    : null;
  const channel = associations.channel ?? discordChannelFactory.build();

  const options = createOptionsMock(transientParams);

  return {
    id: `interaction-${sequence}`,
    commandName: 'test-command',
    commandType: ApplicationCommandType.ChatInput,
    user,
    member,
    guild,
    guildId: guild?.id ?? null,
    channel,
    channelId: channel?.id ?? null,
    deferred: isDeferred,
    replied: isReplied,
    options,
    reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({ id: 'reply-message-id' }),
    deferReply: jest.fn<(opts?: any) => Promise<void>>().mockResolvedValue(undefined),
    editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({ id: 'edit-reply-message-id' }),
    followUp: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({ id: 'followup-message-id' }),
    deleteReply: jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined),
    isChatInputCommand: jest.fn<() => boolean>().mockReturnValue(true),
    inGuild: jest.fn<() => boolean>().mockReturnValue(inGuildParam),
    inCachedGuild: jest.fn<() => boolean>().mockReturnValue(inGuildParam),
  };
});

export const adminInteractionFactory = Factory.define<
  MockChatInputCommandInteraction,
  ChatInputCommandInteractionTransientParams
>(({ sequence, transientParams, associations }) => {
  const adminMember = associations.member ?? discordMemberFactory.build(
    {},
    { transient: { hasManageGuild: true } }
  );

  return chatInputCommandInteractionFactory.build(
    {
      member: adminMember,
      user: adminMember.user,
    },
    { transient: transientParams }
  );
});

export const dmInteractionFactory = Factory.define<
  MockChatInputCommandInteraction,
  ChatInputCommandInteractionTransientParams
>(({ transientParams, associations }) => {
  const channel = associations.channel ?? discordChannelFactory.build(
    {},
    { transient: { isDM: true } }
  );

  return chatInputCommandInteractionFactory.build(
    {
      channel,
      guild: null,
      member: null,
      guildId: null,
    },
    { transient: { ...transientParams, inGuild: false } }
  );
});
