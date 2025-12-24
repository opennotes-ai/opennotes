import { describe, it, expect, beforeEach, jest } from '@jest/globals';
import {
  discordMessageFactory,
  dmMessageFactory,
  systemMessageFactory,
  webhookMessageFactory,
  type MockDiscordMessage,
} from './discord-message.js';
import { discordUserFactory } from './discord-user.js';
import { discordChannelFactory } from './discord-channel.js';
import { discordGuildFactory } from './discord-guild.js';

describe('discordMessageFactory', () => {
  beforeEach(() => {
    discordMessageFactory.rewindSequence();
    discordUserFactory.rewindSequence();
    discordChannelFactory.rewindSequence();
    discordGuildFactory.rewindSequence();
  });

  describe('basic factory', () => {
    it('should create a message with default values', () => {
      const message = discordMessageFactory.build();

      expect(message.id).toBe('message-1');
      expect(message.content).toBe('Test message content 1');
      expect(message.channelId).toBeDefined();
      expect(message.guildId).toBeDefined();
      expect(message.author).toBeDefined();
      expect(message.channel).toBeDefined();
      expect(message.guild).toBeDefined();
      expect(message.system).toBe(false);
      expect(message.webhookId).toBeNull();
      expect(message.createdTimestamp).toBeDefined();
      expect(message.embeds).toEqual([]);
      expect(message.url).toContain('discord.com/channels');
    });

    it('should create unique messages with sequential IDs', () => {
      const message1 = discordMessageFactory.build();
      const message2 = discordMessageFactory.build();

      expect(message1.id).toBe('message-1');
      expect(message2.id).toBe('message-2');
      expect(message1.content).toBe('Test message content 1');
      expect(message2.content).toBe('Test message content 2');
    });

    it('should allow overriding properties', () => {
      const message = discordMessageFactory.build({
        content: 'Custom content',
        system: true,
        webhookId: 'custom-webhook',
      });

      expect(message.content).toBe('Custom content');
      expect(message.system).toBe(true);
      expect(message.webhookId).toBe('custom-webhook');
    });

    it('should create proper URL for guild messages', () => {
      const message = discordMessageFactory.build();

      expect(message.url).toMatch(/https:\/\/discord\.com\/channels\/guild-\d+\/channel-\d+\/message-\d+/);
    });
  });

  describe('associations', () => {
    it('should use provided author association', () => {
      const customAuthor = discordUserFactory.build({
        username: 'custom-user',
        id: 'custom-author-id',
      });

      const message = discordMessageFactory.build({}, { associations: { author: customAuthor } });

      expect(message.author.id).toBe('custom-author-id');
      expect(message.author.username).toBe('custom-user');
    });

    it('should use provided channel association', () => {
      const customChannel = discordChannelFactory.build({
        id: 'custom-channel-id',
        name: 'custom-channel',
      });

      const message = discordMessageFactory.build({}, { associations: { channel: customChannel } });

      expect(message.channel.id).toBe('custom-channel-id');
      expect(message.channelId).toBe('custom-channel-id');
    });

    it('should use provided guild association', () => {
      const customGuild = discordGuildFactory.build({
        id: 'custom-guild-id',
        name: 'Custom Guild',
      });

      const message = discordMessageFactory.build({}, { associations: { guild: customGuild } });

      expect(message.guild?.id).toBe('custom-guild-id');
      expect(message.guildId).toBe('custom-guild-id');
    });

    it('should support multiple associations at once', () => {
      const customAuthor = discordUserFactory.build({ id: 'author-id' });
      const customChannel = discordChannelFactory.build({ id: 'channel-id' });
      const customGuild = discordGuildFactory.build({ id: 'guild-id' });

      const message = discordMessageFactory.build(
        {},
        {
          associations: {
            author: customAuthor,
            channel: customChannel,
            guild: customGuild,
          },
        }
      );

      expect(message.author.id).toBe('author-id');
      expect(message.channelId).toBe('channel-id');
      expect(message.guildId).toBe('guild-id');
    });
  });

  describe('methods', () => {
    it('should have mockable edit method', async () => {
      const message = discordMessageFactory.build();

      const edited = await message.edit({ content: 'Updated content' });

      expect(message.edit).toHaveBeenCalledWith({ content: 'Updated content' });
      expect(edited.id).toBe(message.id);
    });

    it('should have mockable delete method', async () => {
      const message = discordMessageFactory.build();

      await message.delete();

      expect(message.delete).toHaveBeenCalled();
    });

    it('should have mockable reply method', async () => {
      const message = discordMessageFactory.build();

      const reply = await message.reply({ content: 'Reply content' });

      expect(message.reply).toHaveBeenCalledWith({ content: 'Reply content' });
      expect(reply.id).toContain('reply-');
    });

    it('should have mockable createMessageComponentCollector', () => {
      const message = discordMessageFactory.build();

      const collector = message.createMessageComponentCollector({ time: 60000 });

      expect(message.createMessageComponentCollector).toHaveBeenCalledWith({ time: 60000 });
      expect(collector.on).toBeDefined();
      expect(collector.stop).toBeDefined();
    });

    it('should support chained collector.on calls', () => {
      const message = discordMessageFactory.build();
      const collector = message.createMessageComponentCollector();

      const result = collector.on('collect', () => {}).on('end', () => {});

      expect(result).toBe(collector);
    });
  });

  describe('transient params', () => {
    it('should support custom editFn', async () => {
      const editedResult = { edited: true } as unknown as MockDiscordMessage;
      const customEditFn = jest.fn<() => Promise<MockDiscordMessage>>().mockResolvedValue(editedResult);

      const message = discordMessageFactory.build({}, { transient: { editFn: customEditFn } });

      const result = await message.edit({ content: 'test' });

      expect(customEditFn).toHaveBeenCalledWith({ content: 'test' });
      expect(result).toEqual({ edited: true });
    });

    it('should support custom deleteFn', async () => {
      const customDeleteFn = jest.fn<() => Promise<void>>().mockResolvedValue(undefined);

      const message = discordMessageFactory.build({}, { transient: { deleteFn: customDeleteFn } });

      await message.delete();

      expect(customDeleteFn).toHaveBeenCalled();
    });

    it('should support custom replyFn', async () => {
      const repliedResult = { replied: true } as unknown as MockDiscordMessage;
      const customReplyFn = jest.fn<() => Promise<MockDiscordMessage>>().mockResolvedValue(repliedResult);

      const message = discordMessageFactory.build({}, { transient: { replyFn: customReplyFn } });

      const result = await message.reply({ content: 'test' });

      expect(customReplyFn).toHaveBeenCalledWith({ content: 'test' });
      expect(result).toEqual({ replied: true });
    });
  });

  describe('dmMessageFactory', () => {
    it('should create DM message with null guild', () => {
      const message = dmMessageFactory.build();

      expect(message.guild).toBeNull();
      expect(message.guildId).toBeNull();
    });

    it('should create proper URL for DM messages', () => {
      const message = dmMessageFactory.build();

      expect(message.url).toContain('@me');
    });
  });

  describe('systemMessageFactory', () => {
    it('should create system message', () => {
      const message = systemMessageFactory.build();

      expect(message.system).toBe(true);
    });
  });

  describe('webhookMessageFactory', () => {
    it('should create webhook message', () => {
      const message = webhookMessageFactory.build();

      expect(message.webhookId).toBeDefined();
      expect(message.webhookId).not.toBeNull();
    });
  });

  describe('buildList', () => {
    it('should create multiple messages', () => {
      const messages = discordMessageFactory.buildList(3);

      expect(messages).toHaveLength(3);
      expect(messages[0].id).toBe('message-1');
      expect(messages[1].id).toBe('message-2');
      expect(messages[2].id).toBe('message-3');
    });
  });
});
