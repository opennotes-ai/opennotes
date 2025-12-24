import { describe, it, expect, jest, beforeEach } from '@jest/globals';
import { PermissionFlagsBits } from 'discord.js';
import {
  chatInputCommandInteractionFactory,
  adminInteractionFactory,
  dmInteractionFactory,
  discordUserFactory,
  discordMemberFactory,
  discordGuildFactory,
  discordChannelFactory,
} from './index.js';

describe('ChatInputCommandInteraction Factory', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('chatInputCommandInteractionFactory', () => {
    it('should create a basic interaction with default values', () => {
      const interaction = chatInputCommandInteractionFactory.build();

      expect(interaction.id).toBeDefined();
      expect(interaction.commandName).toBe('test-command');
      expect(interaction.user).toBeDefined();
      expect(interaction.user.id).toBeDefined();
      expect(interaction.member).toBeDefined();
      expect(interaction.guild).toBeDefined();
      expect(interaction.guildId).toBeDefined();
      expect(interaction.channel).toBeDefined();
      expect(interaction.deferred).toBe(false);
      expect(interaction.replied).toBe(false);
    });

    it('should create unique IDs for each interaction', () => {
      const interaction1 = chatInputCommandInteractionFactory.build();
      const interaction2 = chatInputCommandInteractionFactory.build();

      expect(interaction1.id).not.toBe(interaction2.id);
      expect(interaction1.user.id).not.toBe(interaction2.user.id);
    });

    it('should support custom commandName', () => {
      const interaction = chatInputCommandInteractionFactory.build({
        commandName: 'custom-command',
      });

      expect(interaction.commandName).toBe('custom-command');
    });

    describe('options transient params', () => {
      it('should support subcommand', () => {
        const interaction = chatInputCommandInteractionFactory.build(
          {},
          { transient: { subcommand: 'request' } }
        );

        expect(interaction.options.getSubcommand()).toBe('request');
      });

      it('should support subcommandGroup', () => {
        const interaction = chatInputCommandInteractionFactory.build(
          {},
          { transient: { subcommandGroup: 'admin' } }
        );

        expect(interaction.options.getSubcommandGroup()).toBe('admin');
      });

      it('should support stringOptions', () => {
        const interaction = chatInputCommandInteractionFactory.build(
          {},
          {
            transient: {
              stringOptions: {
                'message-id': '12345678901234567',
                reason: 'This is misleading',
              },
            },
          }
        );

        expect(interaction.options.getString('message-id')).toBe('12345678901234567');
        expect(interaction.options.getString('reason')).toBe('This is misleading');
        expect(interaction.options.getString('nonexistent')).toBeNull();
      });

      it('should support booleanOptions', () => {
        const interaction = chatInputCommandInteractionFactory.build(
          {},
          {
            transient: {
              booleanOptions: {
                helpful: true,
                anonymous: false,
              },
            },
          }
        );

        expect(interaction.options.getBoolean('helpful')).toBe(true);
        expect(interaction.options.getBoolean('anonymous')).toBe(false);
        expect(interaction.options.getBoolean('nonexistent')).toBeNull();
      });

      it('should support integerOptions', () => {
        const interaction = chatInputCommandInteractionFactory.build(
          {},
          {
            transient: {
              integerOptions: {
                days: 7,
                limit: 10,
              },
            },
          }
        );

        expect(interaction.options.getInteger('days')).toBe(7);
        expect(interaction.options.getInteger('limit')).toBe(10);
      });

      it('should support numberOptions', () => {
        const interaction = chatInputCommandInteractionFactory.build(
          {},
          {
            transient: {
              numberOptions: {
                score: 0.75,
                threshold: 0.5,
              },
            },
          }
        );

        expect(interaction.options.getNumber('score')).toBe(0.75);
        expect(interaction.options.getNumber('threshold')).toBe(0.5);
      });

      it('should support userOptions', () => {
        const targetUser = discordUserFactory.build({ username: 'target' });
        const interaction = chatInputCommandInteractionFactory.build(
          {},
          {
            transient: {
              userOptions: {
                user: targetUser,
              },
            },
          }
        );

        expect(interaction.options.getUser('user')).toBe(targetUser);
        expect(interaction.options.getUser('user')?.username).toBe('target');
      });

      it('should support channelOptions', () => {
        const targetChannel = discordChannelFactory.build({ name: 'target-channel' });
        const interaction = chatInputCommandInteractionFactory.build(
          {},
          {
            transient: {
              channelOptions: {
                channel: targetChannel,
              },
            },
          }
        );

        expect(interaction.options.getChannel('channel')).toBe(targetChannel);
        expect(interaction.options.getChannel('channel')?.name).toBe('target-channel');
      });

      it('should throw for required options when not provided', () => {
        const interaction = chatInputCommandInteractionFactory.build();

        expect(() => interaction.options.getString('required', true)).toThrow();
        expect(() => interaction.options.getBoolean('required', true)).toThrow();
        expect(() => interaction.options.getInteger('required', true)).toThrow();
      });
    });

    describe('associations', () => {
      it('should accept custom user association', () => {
        const customUser = discordUserFactory.build({ username: 'customuser' });
        const interaction = chatInputCommandInteractionFactory.build({
          user: customUser,
        });

        expect(interaction.user.username).toBe('customuser');
      });

      it('should accept custom member association', () => {
        const customMember = discordMemberFactory.build(
          {},
          { transient: { hasManageGuild: true } }
        );
        const interaction = chatInputCommandInteractionFactory.build({
          member: customMember,
        });

        expect(interaction.member?.permissions.has(PermissionFlagsBits.ManageGuild)).toBe(true);
      });

      it('should accept custom guild association', () => {
        const customGuild = discordGuildFactory.build({ name: 'Custom Guild' });
        const interaction = chatInputCommandInteractionFactory.build({
          guild: customGuild,
        });

        expect(interaction.guild?.name).toBe('Custom Guild');
      });

      it('should accept custom channel association', () => {
        const customChannel = discordChannelFactory.build({ name: 'custom-channel' });
        const interaction = chatInputCommandInteractionFactory.build({
          channel: customChannel,
        });

        expect(interaction.channel?.name).toBe('custom-channel');
      });
    });

    describe('reply methods', () => {
      it('should have mockable reply method', async () => {
        const interaction = chatInputCommandInteractionFactory.build();

        await interaction.reply({ content: 'Hello' });

        expect(interaction.reply).toHaveBeenCalledWith({ content: 'Hello' });
      });

      it('should have mockable deferReply method', async () => {
        const interaction = chatInputCommandInteractionFactory.build();

        await interaction.deferReply({ ephemeral: true });

        expect(interaction.deferReply).toHaveBeenCalledWith({ ephemeral: true });
      });

      it('should have mockable editReply method', async () => {
        const interaction = chatInputCommandInteractionFactory.build();

        await interaction.editReply({ content: 'Updated' });

        expect(interaction.editReply).toHaveBeenCalledWith({ content: 'Updated' });
      });

      it('should have mockable followUp method', async () => {
        const interaction = chatInputCommandInteractionFactory.build();

        await interaction.followUp({ content: 'Follow up' });

        expect(interaction.followUp).toHaveBeenCalledWith({ content: 'Follow up' });
      });

      it('should have mockable deleteReply method', async () => {
        const interaction = chatInputCommandInteractionFactory.build();

        await interaction.deleteReply();

        expect(interaction.deleteReply).toHaveBeenCalled();
      });
    });

    describe('deferred and replied states', () => {
      it('should support isDeferred transient param', () => {
        const interaction = chatInputCommandInteractionFactory.build(
          {},
          { transient: { isDeferred: true } }
        );

        expect(interaction.deferred).toBe(true);
      });

      it('should support isReplied transient param', () => {
        const interaction = chatInputCommandInteractionFactory.build(
          {},
          { transient: { isReplied: true } }
        );

        expect(interaction.replied).toBe(true);
      });
    });

    describe('inGuild checks', () => {
      it('should return true for inGuild by default', () => {
        const interaction = chatInputCommandInteractionFactory.build();

        expect(interaction.inGuild()).toBe(true);
        expect(interaction.inCachedGuild()).toBe(true);
      });

      it('should support inGuild: false transient param', () => {
        const interaction = chatInputCommandInteractionFactory.build(
          {},
          { transient: { inGuild: false } }
        );

        expect(interaction.inGuild()).toBe(false);
        expect(interaction.guild).toBeNull();
        expect(interaction.member).toBeNull();
        expect(interaction.guildId).toBeNull();
      });
    });
  });

  describe('adminInteractionFactory', () => {
    it('should create interaction with admin permissions', () => {
      const interaction = adminInteractionFactory.build();

      expect(interaction.member?.permissions.has(PermissionFlagsBits.ManageGuild)).toBe(true);
    });

    it('should pass through transient params', () => {
      const interaction = adminInteractionFactory.build(
        {},
        { transient: { subcommand: 'scan' } }
      );

      expect(interaction.options.getSubcommand()).toBe('scan');
      expect(interaction.member?.permissions.has(PermissionFlagsBits.ManageGuild)).toBe(true);
    });
  });

  describe('dmInteractionFactory', () => {
    it('should create DM interaction without guild/member', () => {
      const interaction = dmInteractionFactory.build();

      expect(interaction.guild).toBeNull();
      expect(interaction.member).toBeNull();
      expect(interaction.guildId).toBeNull();
      expect(interaction.inGuild()).toBe(false);
    });

    it('should have DM channel', () => {
      const interaction = dmInteractionFactory.build();

      expect(interaction.channel?.isDMBased()).toBe(true);
    });
  });

  describe('buildList', () => {
    it('should create multiple unique interactions', () => {
      const interactions = chatInputCommandInteractionFactory.buildList(3);

      expect(interactions).toHaveLength(3);

      const ids = interactions.map((i) => i.id);
      expect(new Set(ids).size).toBe(3);

      const userIds = interactions.map((i) => i.user.id);
      expect(new Set(userIds).size).toBe(3);
    });
  });
});

describe('Supporting Factories', () => {
  describe('discordUserFactory', () => {
    it('should create a user with default values', () => {
      const user = discordUserFactory.build();

      expect(user.id).toBeDefined();
      expect(user.username).toBeDefined();
      expect(user.displayName).toBeDefined();
      expect(user.bot).toBe(false);
      expect(user.displayAvatarURL()).toBeDefined();
    });

    it('should support custom avatarUrl', () => {
      const user = discordUserFactory.build(
        {},
        { transient: { avatarUrl: 'https://custom.url/avatar.png' } }
      );

      expect(user.displayAvatarURL()).toBe('https://custom.url/avatar.png');
    });
  });

  describe('discordMemberFactory', () => {
    it('should create a member with default permissions (no admin)', () => {
      const member = discordMemberFactory.build();

      expect(member.permissions.has(PermissionFlagsBits.ManageGuild)).toBe(false);
    });

    it('should support hasManageGuild transient param', () => {
      const member = discordMemberFactory.build(
        {},
        { transient: { hasManageGuild: true } }
      );

      expect(member.permissions.has(PermissionFlagsBits.ManageGuild)).toBe(true);
    });

    it('should support hasAdministrator transient param', () => {
      const member = discordMemberFactory.build(
        {},
        { transient: { hasAdministrator: true } }
      );

      expect(member.permissions.has(PermissionFlagsBits.Administrator)).toBe(true);
      expect(member.permissions.has(PermissionFlagsBits.ManageGuild)).toBe(true);
    });
  });

  describe('discordGuildFactory', () => {
    it('should create a guild with channels and members caches', () => {
      const guild = discordGuildFactory.build();

      expect(guild.id).toBeDefined();
      expect(guild.name).toBeDefined();
      expect(guild.channels.cache).toBeDefined();
      expect(guild.members.cache).toBeDefined();
    });
  });

  describe('discordChannelFactory', () => {
    it('should create a text channel by default', () => {
      const channel = discordChannelFactory.build();

      expect(channel.isTextBased()).toBe(true);
      expect(channel.isDMBased()).toBe(false);
    });

    it('should support isDM transient param', () => {
      const channel = discordChannelFactory.build(
        {},
        { transient: { isDM: true } }
      );

      expect(channel.isDMBased()).toBe(true);
    });

    it('should support missingPermissions transient param', () => {
      const channel = discordChannelFactory.build(
        {},
        { transient: { missingPermissions: ['SendMessages'] } }
      );

      const permissions = channel.permissionsFor();
      expect(permissions?.has(PermissionFlagsBits.SendMessages)).toBe(false);
      expect(permissions?.has(PermissionFlagsBits.CreatePublicThreads)).toBe(true);
    });
  });
});
