import { Factory } from 'fishery';
import { jest } from '@jest/globals';
import type { Embed } from 'discord.js';
import { discordUserFactory, type MockDiscordUser } from './discord-user.js';
import { discordChannelFactory, type MockDiscordChannel } from './discord-channel.js';
import { discordGuildFactory, type MockDiscordGuild } from './discord-guild.js';

export interface MockDiscordMessage {
  id: string;
  content: string;
  channelId: string;
  guildId: string | null;
  author: MockDiscordUser;
  channel: MockDiscordChannel;
  guild: MockDiscordGuild | null;
  system: boolean;
  webhookId: string | null;
  createdTimestamp: number;
  embeds: Embed[];
  url: string;
  edit: ReturnType<typeof jest.fn>;
  delete: ReturnType<typeof jest.fn>;
  reply: ReturnType<typeof jest.fn>;
  createMessageComponentCollector: ReturnType<typeof jest.fn>;
}

export interface MessageTransientParams {
  editFn?: ReturnType<typeof jest.fn>;
  deleteFn?: ReturnType<typeof jest.fn>;
  replyFn?: ReturnType<typeof jest.fn>;
  isSystemMessage?: boolean;
  isWebhookMessage?: boolean;
  isDM?: boolean;
}

export const discordMessageFactory = Factory.define<MockDiscordMessage, MessageTransientParams>(
  ({ sequence, transientParams, associations }) => {
    const {
      editFn,
      deleteFn,
      replyFn,
      isSystemMessage = false,
      isWebhookMessage = false,
      isDM = false,
    } = transientParams;

    const author = associations.author ?? discordUserFactory.build();
    const channel = associations.channel ?? discordChannelFactory.transient({ isDM }).build();
    const guild = isDM ? null : (associations.guild ?? discordGuildFactory.build());

    const channelId = channel.id;
    const guildId = guild?.id ?? null;
    const messageId = `message-${sequence}`;

    const mockCollector = {
      on: jest.fn().mockReturnThis(),
      stop: jest.fn(),
      ended: false,
    };

    const replyMessageBuilder = (): MockDiscordMessage => {
      const replyMessage: MockDiscordMessage = {
        id: `reply-${messageId}`,
        content: 'Reply message',
        channelId,
        guildId,
        author,
        channel,
        guild,
        system: false,
        webhookId: null,
        createdTimestamp: Date.now(),
        embeds: [],
        url: `https://discord.com/channels/${guildId ?? '@me'}/${channelId}/reply-${messageId}`,
        edit: jest.fn<() => Promise<MockDiscordMessage>>().mockImplementation(
          async () => replyMessage
        ),
        delete: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
        reply: jest.fn<() => Promise<MockDiscordMessage>>().mockImplementation(
          async () => replyMessageBuilder()
        ),
        createMessageComponentCollector: jest.fn<() => any>().mockReturnValue(mockCollector),
      };
      return replyMessage;
    };

    const message: MockDiscordMessage = {
      id: messageId,
      content: `Test message content ${sequence}`,
      channelId,
      guildId,
      author,
      channel,
      guild,
      system: isSystemMessage,
      webhookId: isWebhookMessage ? `webhook-${sequence}` : null,
      createdTimestamp: Date.now(),
      embeds: [],
      url: `https://discord.com/channels/${guildId ?? '@me'}/${channelId}/${messageId}`,
      edit: editFn ?? jest.fn<() => Promise<MockDiscordMessage>>().mockImplementation(
        async () => message
      ),
      delete: deleteFn ?? jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
      reply: replyFn ?? jest.fn<() => Promise<MockDiscordMessage>>().mockImplementation(
        async () => replyMessageBuilder()
      ),
      createMessageComponentCollector: jest.fn<() => any>().mockReturnValue(mockCollector),
    };

    return message;
  }
);

export const dmMessageFactory = discordMessageFactory.transient({ isDM: true });

export const systemMessageFactory = discordMessageFactory.transient({ isSystemMessage: true });

export const webhookMessageFactory = discordMessageFactory.transient({ isWebhookMessage: true });
