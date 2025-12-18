import { describe, it, expect, beforeEach, afterEach, jest } from '@jest/globals';
import { ChannelType, Collection, PermissionFlagsBits } from 'discord.js';

const mockLogger = {
  info: jest.fn<(...args: unknown[]) => void>(),
  debug: jest.fn<(...args: unknown[]) => void>(),
  error: jest.fn<(...args: unknown[]) => void>(),
  warn: jest.fn<(...args: unknown[]) => void>(),
};

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
}));

const { BotChannelService } = await import('../../src/services/BotChannelService.js');

describe('BotChannelService', () => {
  let service: InstanceType<typeof BotChannelService>;
  let mockGuild: any;
  let mockChannel: any;
  let mockRole: any;
  let mockBotMember: any;

  beforeEach(() => {
    service = new BotChannelService();

    mockRole = {
      id: 'role-123',
      name: 'OpenNotes',
    };

    mockBotMember = {
      id: 'bot-123',
      user: {
        id: 'bot-user-123',
      },
    };

    mockGuild = {
      id: 'guild-123',
      name: 'Test Guild',
      roles: {
        everyone: { id: 'everyone-role-id' },
        cache: new Collection([['role-123', mockRole]]),
      },
      channels: {
        cache: new Collection<string, any>(),
        create: jest.fn<(...args: any[]) => Promise<any>>(),
      },
      members: {
        me: mockBotMember,
      },
    };

    mockChannel = {
      id: 'channel-123',
      name: 'open-notes',
      type: ChannelType.GuildText,
      guild: mockGuild,
      delete: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue(undefined),
      permissionOverwrites: {
        set: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue(undefined),
      },
    };

    mockGuild.channels.cache.set('channel-123', mockChannel);
    mockGuild.channels.create.mockResolvedValue(mockChannel);
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe('findChannel', () => {
    it('should find channel by name', () => {
      const result = service.findChannel(mockGuild, 'open-notes');

      expect(result).toBe(mockChannel);
    });

    it('should return undefined if channel not found', () => {
      const result = service.findChannel(mockGuild, 'nonexistent-channel');

      expect(result).toBeUndefined();
    });

    it('should only find text channels', () => {
      const voiceChannel = {
        id: 'voice-123',
        name: 'open-notes',
        type: ChannelType.GuildVoice,
      };
      mockGuild.channels.cache = new Collection([['voice-123', voiceChannel]]);

      const result = service.findChannel(mockGuild, 'open-notes');

      expect(result).toBeUndefined();
    });

    it('should be case-insensitive', () => {
      const result = service.findChannel(mockGuild, 'Open-Notes');

      expect(result).toBe(mockChannel);
    });
  });

  describe('createChannel', () => {
    it('should create channel with correct name', async () => {
      const result = await service.createChannel(mockGuild, 'open-notes');

      expect(mockGuild.channels.create).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'open-notes',
          type: ChannelType.GuildText,
        })
      );
      expect(result).toBe(mockChannel);
    });

    it('should set topic describing the channel purpose', async () => {
      await service.createChannel(mockGuild, 'open-notes');

      expect(mockGuild.channels.create).toHaveBeenCalledWith(
        expect.objectContaining({
          topic: expect.stringContaining('OpenNotes'),
        })
      );
    });

    it('should log channel creation', async () => {
      await service.createChannel(mockGuild, 'open-notes');

      expect(mockLogger.info).toHaveBeenCalledWith(
        expect.stringContaining('Created bot channel'),
        expect.objectContaining({
          guildId: 'guild-123',
          channelName: 'open-notes',
        })
      );
    });

    it('should throw error if creation fails', async () => {
      mockGuild.channels.create.mockRejectedValue(new Error('Permission denied'));

      await expect(service.createChannel(mockGuild, 'open-notes')).rejects.toThrow(
        'Permission denied'
      );

      expect(mockLogger.error).toHaveBeenCalled();
    });
  });

  describe('deleteChannel', () => {
    it('should delete the specified channel', async () => {
      await service.deleteChannel(mockGuild, mockChannel);

      expect(mockChannel.delete).toHaveBeenCalled();
    });

    it('should log channel deletion', async () => {
      await service.deleteChannel(mockGuild, mockChannel);

      expect(mockLogger.info).toHaveBeenCalledWith(
        expect.stringContaining('Deleted bot channel'),
        expect.objectContaining({
          guildId: 'guild-123',
          channelId: 'channel-123',
        })
      );
    });

    it('should throw error if deletion fails', async () => {
      mockChannel.delete.mockRejectedValue(new Error('Missing permissions'));

      await expect(service.deleteChannel(mockGuild, mockChannel)).rejects.toThrow(
        'Missing permissions'
      );

      expect(mockLogger.error).toHaveBeenCalled();
    });
  });

  describe('setupPermissions', () => {
    it('should set up permissions for @everyone role', async () => {
      await service.setupPermissions(mockChannel, mockRole, mockBotMember);

      expect(mockChannel.permissionOverwrites.set).toHaveBeenCalledWith(
        expect.arrayContaining([
          expect.objectContaining({
            id: 'everyone-role-id',
            allow: expect.arrayContaining([
              PermissionFlagsBits.ViewChannel,
              PermissionFlagsBits.UseApplicationCommands,
              PermissionFlagsBits.ReadMessageHistory,
            ]),
            deny: expect.arrayContaining([PermissionFlagsBits.SendMessages]),
          }),
        ])
      );
    });

    it('should set up permissions for OpenNotes role', async () => {
      await service.setupPermissions(mockChannel, mockRole, mockBotMember);

      expect(mockChannel.permissionOverwrites.set).toHaveBeenCalledWith(
        expect.arrayContaining([
          expect.objectContaining({
            id: 'role-123',
            allow: expect.arrayContaining([
              PermissionFlagsBits.ViewChannel,
              PermissionFlagsBits.SendMessages,
              PermissionFlagsBits.UseApplicationCommands,
              PermissionFlagsBits.ReadMessageHistory,
            ]),
          }),
        ])
      );
    });

    it('should set up permissions for the bot', async () => {
      await service.setupPermissions(mockChannel, mockRole, mockBotMember);

      expect(mockChannel.permissionOverwrites.set).toHaveBeenCalledWith(
        expect.arrayContaining([
          expect.objectContaining({
            id: 'bot-123',
            allow: expect.arrayContaining([
              PermissionFlagsBits.ViewChannel,
              PermissionFlagsBits.ManageChannels,
              PermissionFlagsBits.SendMessages,
              PermissionFlagsBits.ManageMessages,
              PermissionFlagsBits.EmbedLinks,
              PermissionFlagsBits.AttachFiles,
              PermissionFlagsBits.ReadMessageHistory,
              PermissionFlagsBits.UseApplicationCommands,
            ]),
          }),
        ])
      );
    });

    it('should log permission setup', async () => {
      await service.setupPermissions(mockChannel, mockRole, mockBotMember);

      expect(mockLogger.info).toHaveBeenCalledWith(
        expect.stringContaining('Set up bot channel permissions'),
        expect.objectContaining({
          channelId: 'channel-123',
          roleId: 'role-123',
        })
      );
    });

    it('should throw error if permission setup fails', async () => {
      mockChannel.permissionOverwrites.set.mockRejectedValue(
        new Error('Missing permissions')
      );

      await expect(
        service.setupPermissions(mockChannel, mockRole, mockBotMember)
      ).rejects.toThrow('Missing permissions');

      expect(mockLogger.error).toHaveBeenCalled();
    });
  });

  describe('ensureChannelExists', () => {
    let mockGuildConfigService: any;

    beforeEach(() => {
      mockGuildConfigService = {
        get: jest.fn<(...args: any[]) => Promise<any>>(),
      };
    });

    it('should return existing channel with wasCreated=false', async () => {
      mockGuildConfigService.get.mockResolvedValue('open-notes');

      const result = await service.ensureChannelExists(mockGuild, mockGuildConfigService);

      expect(result.channel).toBe(mockChannel);
      expect(result.wasCreated).toBe(false);
      expect(mockGuild.channels.create).not.toHaveBeenCalled();
    });

    it('should create channel if not found and return wasCreated=true', async () => {
      mockGuildConfigService.get.mockResolvedValue('new-channel');
      mockGuild.channels.cache = new Collection();

      const newChannel = {
        id: 'new-channel-123',
        name: 'new-channel',
        type: ChannelType.GuildText,
        permissionOverwrites: {
          set: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue(undefined),
        },
        guild: mockGuild,
      };
      mockGuild.channels.create.mockResolvedValue(newChannel);

      const result = await service.ensureChannelExists(mockGuild, mockGuildConfigService);

      expect(result.channel).toBe(newChannel);
      expect(result.wasCreated).toBe(true);
      expect(mockGuild.channels.create).toHaveBeenCalled();
    });

    it('should use config value for channel name', async () => {
      mockGuildConfigService.get.mockResolvedValue('custom-channel-name');
      mockGuild.channels.cache = new Collection();

      const customChannel = {
        id: 'custom-channel-123',
        name: 'custom-channel-name',
        type: ChannelType.GuildText,
        permissionOverwrites: {
          set: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue(undefined),
        },
        guild: mockGuild,
      };
      mockGuild.channels.create.mockResolvedValue(customChannel);

      await service.ensureChannelExists(mockGuild, mockGuildConfigService);

      expect(mockGuild.channels.create).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'custom-channel-name',
        })
      );
    });

    it('should set up permissions on newly created channel', async () => {
      mockGuildConfigService.get
        .mockResolvedValueOnce('new-channel')
        .mockResolvedValueOnce('OpenNotes');
      mockGuild.channels.cache = new Collection();

      const newChannel = {
        id: 'new-channel-123',
        name: 'new-channel',
        type: ChannelType.GuildText,
        permissionOverwrites: {
          set: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue(undefined),
        },
        guild: mockGuild,
      };
      mockGuild.channels.create.mockResolvedValue(newChannel);

      await service.ensureChannelExists(mockGuild, mockGuildConfigService);

      expect(newChannel.permissionOverwrites.set).toHaveBeenCalled();
    });

    it('should log when channel already exists', async () => {
      mockGuildConfigService.get.mockResolvedValue('open-notes');

      await service.ensureChannelExists(mockGuild, mockGuildConfigService);

      expect(mockLogger.debug).toHaveBeenCalledWith(
        expect.stringContaining('Bot channel already exists'),
        expect.objectContaining({
          guildId: 'guild-123',
          channelId: 'channel-123',
        })
      );
    });

    it('should log when creating new channel', async () => {
      mockGuildConfigService.get
        .mockResolvedValueOnce('new-channel')
        .mockResolvedValueOnce('OpenNotes');
      mockGuild.channels.cache = new Collection();

      const newChannel = {
        id: 'new-channel-123',
        name: 'new-channel',
        type: ChannelType.GuildText,
        permissionOverwrites: {
          set: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue(undefined),
        },
        guild: mockGuild,
      };
      mockGuild.channels.create.mockResolvedValue(newChannel);

      await service.ensureChannelExists(mockGuild, mockGuildConfigService);

      expect(mockLogger.info).toHaveBeenCalledWith(
        expect.stringContaining('Created bot channel'),
        expect.any(Object)
      );
    });

    it('should handle missing OpenNotes role gracefully', async () => {
      mockGuildConfigService.get
        .mockResolvedValueOnce('new-channel')
        .mockResolvedValueOnce('NonexistentRole');
      mockGuild.channels.cache = new Collection();
      mockGuild.roles.cache = new Collection();

      const newChannel = {
        id: 'new-channel-123',
        name: 'new-channel',
        type: ChannelType.GuildText,
        permissionOverwrites: {
          set: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue(undefined),
        },
        guild: mockGuild,
      };
      mockGuild.channels.create.mockResolvedValue(newChannel);

      const result = await service.ensureChannelExists(mockGuild, mockGuildConfigService);

      expect(result.channel).toBe(newChannel);
      expect(result.wasCreated).toBe(true);
      expect(mockLogger.warn).toHaveBeenCalledWith(
        expect.stringContaining('OpenNotes role not found'),
        expect.any(Object)
      );
    });

    it('should handle race condition when channel is created by another process (AC1)', async () => {
      mockGuildConfigService.get
        .mockResolvedValueOnce('new-channel')
        .mockResolvedValueOnce('OpenNotes');
      mockGuild.channels.cache = new Collection();

      const duplicateError = new Error('Duplicate channel') as Error & { code: number };
      duplicateError.code = 50035;
      mockGuild.channels.create.mockRejectedValue(duplicateError);

      const existingChannel = {
        id: 'existing-channel-123',
        name: 'new-channel',
        type: ChannelType.GuildText,
        permissionOverwrites: {
          set: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue(undefined),
        },
        guild: mockGuild,
      };

      const findChannelSpy = jest.spyOn(service, 'findChannel');
      findChannelSpy
        .mockReturnValueOnce(undefined)
        .mockReturnValueOnce(existingChannel as any);

      const result = await service.ensureChannelExists(mockGuild, mockGuildConfigService);

      expect(result.channel).toBe(existingChannel);
      expect(result.wasCreated).toBe(false);
      expect(findChannelSpy).toHaveBeenCalledTimes(2);
    });

    it('should rethrow non-duplicate errors during channel creation (AC1)', async () => {
      mockGuildConfigService.get.mockResolvedValue('new-channel');
      mockGuild.channels.cache = new Collection();

      const otherError = new Error('Permission denied') as Error & { code: number };
      otherError.code = 50013;
      mockGuild.channels.create.mockRejectedValue(otherError);

      await expect(
        service.ensureChannelExists(mockGuild, mockGuildConfigService)
      ).rejects.toThrow('Permission denied');
    });

    it('should use fetchMe when guild.members.me is null (AC2)', async () => {
      mockGuildConfigService.get
        .mockResolvedValueOnce('new-channel')
        .mockResolvedValueOnce('OpenNotes');
      mockGuild.channels.cache = new Collection();
      mockGuild.members.me = null;
      mockGuild.members.fetchMe = jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue(mockBotMember);

      const newChannel = {
        id: 'new-channel-123',
        name: 'new-channel',
        type: ChannelType.GuildText,
        permissionOverwrites: {
          set: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue(undefined),
        },
        guild: mockGuild,
      };
      mockGuild.channels.create.mockResolvedValue(newChannel);

      const result = await service.ensureChannelExists(mockGuild, mockGuildConfigService);

      expect(result.channel).toBe(newChannel);
      expect(result.wasCreated).toBe(true);
      expect(mockGuild.members.fetchMe).toHaveBeenCalled();
      expect(newChannel.permissionOverwrites.set).toHaveBeenCalled();
    });

    it('should skip permissions when fetchMe fails (AC2)', async () => {
      mockGuildConfigService.get
        .mockResolvedValueOnce('new-channel')
        .mockResolvedValueOnce('OpenNotes');
      mockGuild.channels.cache = new Collection();
      mockGuild.members.me = null;
      mockGuild.members.fetchMe = jest.fn<(...args: any[]) => Promise<any>>().mockRejectedValue(new Error('Fetch failed'));

      const newChannel = {
        id: 'new-channel-123',
        name: 'new-channel',
        type: ChannelType.GuildText,
        permissionOverwrites: {
          set: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue(undefined),
        },
        guild: mockGuild,
      };
      mockGuild.channels.create.mockResolvedValue(newChannel);

      const result = await service.ensureChannelExists(mockGuild, mockGuildConfigService);

      expect(result.channel).toBe(newChannel);
      expect(result.wasCreated).toBe(true);
      expect(mockGuild.members.fetchMe).toHaveBeenCalled();
      expect(newChannel.permissionOverwrites.set).not.toHaveBeenCalled();
      expect(mockLogger.warn).toHaveBeenCalledWith(
        expect.stringContaining('Could not fetch bot member'),
        expect.any(Object)
      );
    });
  });

  describe('findRole', () => {
    it('should find role by name', () => {
      const result = service.findRole(mockGuild, 'OpenNotes');

      expect(result).toBe(mockRole);
    });

    it('should return undefined if role not found', () => {
      const result = service.findRole(mockGuild, 'NonexistentRole');

      expect(result).toBeUndefined();
    });

    it('should be case-insensitive', () => {
      const result = service.findRole(mockGuild, 'opennotes');

      expect(result).toBe(mockRole);
    });
  });

  describe('migrateChannel', () => {
    let mockGuildConfigService: any;
    let newMockChannel: any;
    let oldMockChannel: any;

    beforeEach(() => {
      mockGuildConfigService = {
        get: jest.fn<(...args: any[]) => Promise<any>>(),
      };

      oldMockChannel = {
        id: 'old-channel-123',
        name: 'old-channel',
        type: ChannelType.GuildText,
        guild: mockGuild,
        delete: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue(undefined),
        permissionOverwrites: {
          set: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue(undefined),
        },
      };

      newMockChannel = {
        id: 'new-channel-123',
        name: 'new-channel',
        type: ChannelType.GuildText,
        guild: mockGuild,
        delete: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue(undefined),
        permissionOverwrites: {
          set: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue(undefined),
        },
      };

      mockGuild.channels.cache = new Collection([['old-channel-123', oldMockChannel]]);
      mockGuild.channels.create.mockResolvedValue(newMockChannel);
      mockGuildConfigService.get.mockResolvedValue('OpenNotes');
    });

    it('should create new channel with new name', async () => {
      const result = await service.migrateChannel(
        mockGuild,
        'old-channel',
        'new-channel',
        mockGuildConfigService
      );

      expect(mockGuild.channels.create).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'new-channel',
        })
      );
      expect(result.newChannel).toBe(newMockChannel);
    });

    it('should delete old channel after creating new one', async () => {
      const result = await service.migrateChannel(
        mockGuild,
        'old-channel',
        'new-channel',
        mockGuildConfigService
      );

      expect(oldMockChannel.delete).toHaveBeenCalled();
      expect(result.oldChannelDeleted).toBe(true);
    });

    it('should set up permissions on new channel', async () => {
      await service.migrateChannel(
        mockGuild,
        'old-channel',
        'new-channel',
        mockGuildConfigService
      );

      expect(newMockChannel.permissionOverwrites.set).toHaveBeenCalled();
    });

    it('should handle missing old channel gracefully', async () => {
      mockGuild.channels.cache = new Collection();

      const result = await service.migrateChannel(
        mockGuild,
        'nonexistent-channel',
        'new-channel',
        mockGuildConfigService
      );

      expect(result.newChannel).toBe(newMockChannel);
      expect(result.oldChannelDeleted).toBe(false);
    });

    it('should continue if old channel deletion fails', async () => {
      oldMockChannel.delete.mockRejectedValue(new Error('Permission denied'));

      const result = await service.migrateChannel(
        mockGuild,
        'old-channel',
        'new-channel',
        mockGuildConfigService
      );

      expect(result.newChannel).toBe(newMockChannel);
      expect(result.oldChannelDeleted).toBe(false);
      expect(mockLogger.error).toHaveBeenCalledWith(
        expect.stringContaining('Failed to delete old channel'),
        expect.any(Object)
      );
    });

    it('should throw if new channel creation fails', async () => {
      mockGuild.channels.create.mockRejectedValue(new Error('Cannot create channel'));

      await expect(
        service.migrateChannel(
          mockGuild,
          'old-channel',
          'new-channel',
          mockGuildConfigService
        )
      ).rejects.toThrow('Cannot create channel');

      expect(oldMockChannel.delete).not.toHaveBeenCalled();
    });

    it('should log migration start and completion', async () => {
      await service.migrateChannel(
        mockGuild,
        'old-channel',
        'new-channel',
        mockGuildConfigService
      );

      expect(mockLogger.info).toHaveBeenCalledWith(
        expect.stringContaining('Starting bot channel migration'),
        expect.objectContaining({
          guildId: 'guild-123',
          oldChannelName: 'old-channel',
          newChannelName: 'new-channel',
        })
      );

      expect(mockLogger.info).toHaveBeenCalledWith(
        expect.stringContaining('Bot channel migration completed'),
        expect.objectContaining({
          guildId: 'guild-123',
          newChannelId: 'new-channel-123',
          oldChannelDeleted: true,
        })
      );
    });

    it('should handle missing OpenNotes role during migration', async () => {
      mockGuildConfigService.get.mockResolvedValue('NonexistentRole');
      mockGuild.roles.cache = new Collection();

      const result = await service.migrateChannel(
        mockGuild,
        'old-channel',
        'new-channel',
        mockGuildConfigService
      );

      expect(result.newChannel).toBe(newMockChannel);
      expect(mockLogger.warn).toHaveBeenCalledWith(
        expect.stringContaining('OpenNotes role not found during migration'),
        expect.any(Object)
      );
    });

    it('should use fetchMe when guild.members.me is null during migration (AC2)', async () => {
      mockGuildConfigService.get.mockResolvedValue('OpenNotes');
      mockGuild.members.me = null;
      mockGuild.members.fetchMe = jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue(mockBotMember);

      const result = await service.migrateChannel(
        mockGuild,
        'old-channel',
        'new-channel',
        mockGuildConfigService
      );

      expect(result.newChannel).toBe(newMockChannel);
      expect(mockGuild.members.fetchMe).toHaveBeenCalled();
      expect(newMockChannel.permissionOverwrites.set).toHaveBeenCalled();
    });

    it('should skip permissions when fetchMe fails during migration (AC2)', async () => {
      mockGuildConfigService.get.mockResolvedValue('OpenNotes');
      mockGuild.members.me = null;
      mockGuild.members.fetchMe = jest.fn<(...args: any[]) => Promise<any>>().mockRejectedValue(new Error('Fetch failed'));

      const result = await service.migrateChannel(
        mockGuild,
        'old-channel',
        'new-channel',
        mockGuildConfigService
      );

      expect(result.newChannel).toBe(newMockChannel);
      expect(mockGuild.members.fetchMe).toHaveBeenCalled();
      expect(newMockChannel.permissionOverwrites.set).not.toHaveBeenCalled();
      expect(mockLogger.warn).toHaveBeenCalledWith(
        expect.stringContaining('Could not fetch bot member'),
        expect.any(Object)
      );
    });
  });

  describe('validateChannelName (AC9)', () => {
    it('should accept valid channel names', () => {
      const validNames = [
        'open-notes',
        'bot-channel',
        'test_channel',
        'channel123',
        'a',
        'a'.repeat(100),
      ];

      for (const name of validNames) {
        expect(() => service.validateChannelName(name)).not.toThrow();
      }
    });

    it('should reject empty channel name', () => {
      expect(() => service.validateChannelName('')).toThrow(
        'Channel name must be 1-100 characters'
      );
    });

    it('should reject channel name longer than 100 characters', () => {
      const longName = 'a'.repeat(101);

      expect(() => service.validateChannelName(longName)).toThrow(
        'Channel name must be 1-100 characters'
      );
    });

    it('should reject channel name with uppercase letters', () => {
      expect(() => service.validateChannelName('Open-Notes')).toThrow(
        'Channel name can only contain lowercase letters, numbers, hyphens, and underscores'
      );
    });

    it('should reject channel name with spaces', () => {
      expect(() => service.validateChannelName('open notes')).toThrow(
        'Channel name can only contain lowercase letters, numbers, hyphens, and underscores'
      );
    });

    it('should reject channel name with special characters', () => {
      const invalidNames = ['open@notes', 'open!notes', 'open#notes', 'open$notes'];

      for (const name of invalidNames) {
        expect(() => service.validateChannelName(name)).toThrow(
          'Channel name can only contain lowercase letters, numbers, hyphens, and underscores'
        );
      }
    });
  });

  describe('createChannel with validation (AC9)', () => {
    it('should validate channel name before creating', async () => {
      await expect(service.createChannel(mockGuild, 'Invalid Name')).rejects.toThrow(
        'Channel name can only contain lowercase letters, numbers, hyphens, and underscores'
      );

      expect(mockGuild.channels.create).not.toHaveBeenCalled();
    });

    it('should create channel when name is valid', async () => {
      const result = await service.createChannel(mockGuild, 'valid-name');

      expect(mockGuild.channels.create).toHaveBeenCalled();
      expect(result).toBe(mockChannel);
    });
  });
});
