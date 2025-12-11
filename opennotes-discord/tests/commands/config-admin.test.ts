import { jest } from '@jest/globals';
import { MessageFlags } from 'discord.js';

const mockLogger = {
  info: jest.fn<(...args: unknown[]) => void>(),
  error: jest.fn<(...args: unknown[]) => void>(),
  warn: jest.fn<(...args: unknown[]) => void>(),
};

const mockApiClient = {
  addCommunityAdmin: jest.fn<(communityServerId: string, userDiscordId: string) => Promise<any>>(),
  removeCommunityAdmin: jest.fn<(communityServerId: string, userDiscordId: string) => Promise<any>>(),
  listCommunityAdmins: jest.fn<(communityServerId: string) => Promise<any[]>>(),
};

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
}));

jest.unstable_mockModule('../../src/api-client.js', () => ({
  apiClient: mockApiClient,
}));

const { execute } = await import('../../src/commands/config.js');

describe('config-admin command', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('set subcommand', () => {
    it('should add a user as community admin', async () => {
      const mockUser = {
        id: 'user123',
        tag: 'TestUser#1234',
        username: 'TestUser',
        displayName: 'Test User Display',
        displayAvatarURL: jest.fn(() => 'https://example.com/avatar.png'),
      };

      const mockAdminResponse = {
        profile_id: 'profile-uuid-123',
        display_name: 'TestUser',
        avatar_url: null,
        discord_id: 'user123',
        admin_sources: ['community_role'],
        is_opennotes_admin: false,
        community_role: 'admin',
      };

      mockApiClient.addCommunityAdmin.mockResolvedValue(mockAdminResponse);

      const mockInteraction = {
        user: { id: 'admin456' },
        guildId: 'guild789',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('admin'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('set'),
          getUser: jest.fn<(name: string, required: boolean) => any>().mockReturnValue(mockUser),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      await execute(mockInteraction as any);

      expect(mockApiClient.addCommunityAdmin).toHaveBeenCalledWith(
        'guild789',
        'user123',
        expect.objectContaining({
          username: expect.any(String),
          display_name: expect.any(String),
          avatar_url: expect.any(String),
        })
      );
      const v2EphemeralFlags = MessageFlags.Ephemeral | MessageFlags.IsComponentsV2;
      expect(mockInteraction.deferReply).toHaveBeenCalledWith({ flags: v2EphemeralFlags });
      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          components: expect.arrayContaining([
            expect.objectContaining({
              type: 17,
              components: expect.arrayContaining([
                expect.objectContaining({
                  type: 10,
                  content: expect.stringContaining('Admin Added'),
                }),
              ]),
            }),
          ]),
        })
      );
    });

    it('should handle 404 error when user not found', async () => {
      const mockUser = {
        id: 'user123',
        tag: 'TestUser#1234',
        username: 'TestUser',
        displayName: 'Test User Display',
        displayAvatarURL: jest.fn(() => 'https://example.com/avatar.png'),
      };

      const mockError: any = new Error('Not found');
      mockError.statusCode = 404;
      mockError.endpoint = '/api/v1/community-servers/guild789/admins';
      mockError.name = 'ApiError';

      mockApiClient.addCommunityAdmin.mockRejectedValue(mockError);

      const mockInteraction = {
        user: { id: 'admin456' },
        guildId: 'guild789',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('admin'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('set'),
          getUser: jest.fn<(name: string, required: boolean) => any>().mockReturnValue(mockUser),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      await execute(mockInteraction as any);

      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('Could not find server or user'),
        })
      );
    });
  });

  describe('remove subcommand', () => {
    it('should remove a user from community admins', async () => {
      const mockUser = {
        id: 'user123',
        tag: 'TestUser#1234',
      };

      const mockRemoveResponse = {
        success: true,
        message: 'Successfully removed admin status',
        profile_id: 'profile-uuid-123',
        previous_role: 'admin',
        new_role: 'member',
      };

      mockApiClient.removeCommunityAdmin.mockResolvedValue(mockRemoveResponse);

      const mockInteraction = {
        user: { id: 'admin456' },
        guildId: 'guild789',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('admin'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('remove'),
          getUser: jest.fn<(name: string, required: boolean) => any>().mockReturnValue(mockUser),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      await execute(mockInteraction as any);

      expect(mockApiClient.removeCommunityAdmin).toHaveBeenCalledWith('guild789', 'user123');
      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          components: expect.arrayContaining([
            expect.objectContaining({
              type: 17,
              components: expect.arrayContaining([
                expect.objectContaining({
                  type: 10,
                  content: expect.stringContaining('Admin Removed'),
                }),
              ]),
            }),
          ]),
        })
      );
    });

    it('should handle 409 error when trying to remove last admin', async () => {
      const mockUser = {
        id: 'user123',
        tag: 'TestUser#1234',
      };

      const mockError = new Error('Conflict');
      Object.assign(mockError, {
        statusCode: 409,
        endpoint: '/api/v1/community-servers/guild789/admins/user123',
      });
      mockError.name = 'ApiError';

      mockApiClient.removeCommunityAdmin.mockRejectedValue(mockError);

      const mockInteraction = {
        user: { id: 'admin456' },
        guildId: 'guild789',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('admin'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('remove'),
          getUser: jest.fn<(name: string, required: boolean) => any>().mockReturnValue(mockUser),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      await execute(mockInteraction as any);

      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('Cannot remove the last admin'),
        })
      );
    });
  });

  describe('list subcommand', () => {
    it('should list all community admins with their sources', async () => {
      const mockAdmins = [
        {
          profile_id: 'profile-1',
          display_name: 'Admin One',
          avatar_url: null,
          discord_id: 'user111',
          admin_sources: ['opennotes_platform', 'community_role'],
          is_opennotes_admin: true,
          community_role: 'admin',
        },
        {
          profile_id: 'profile-2',
          display_name: 'Admin Two',
          avatar_url: null,
          discord_id: 'user222',
          admin_sources: ['discord_manage_server'],
          is_opennotes_admin: false,
          community_role: 'member',
        },
      ];

      mockApiClient.listCommunityAdmins.mockResolvedValue(mockAdmins);

      const mockInteraction = {
        user: { id: 'admin456' },
        guildId: 'guild789',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('admin'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('list'),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      await execute(mockInteraction as any);

      expect(mockApiClient.listCommunityAdmins).toHaveBeenCalledWith('guild789');
      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          components: expect.arrayContaining([
            expect.objectContaining({
              type: 17,
              components: expect.arrayContaining([
                expect.objectContaining({
                  type: 10,
                  content: expect.stringContaining('Open Notes Admins (2)'),
                }),
                expect.objectContaining({
                  type: 10,
                  content: expect.stringContaining('Admin One'),
                }),
                expect.objectContaining({
                  type: 10,
                  content: expect.stringContaining('Platform Admin, Community Admin'),
                }),
                expect.objectContaining({
                  type: 10,
                  content: expect.stringContaining('Admin Two'),
                }),
                expect.objectContaining({
                  type: 10,
                  content: expect.stringContaining('Discord Manage Server'),
                }),
              ]),
            }),
          ]),
        })
      );
    });

    it('should handle empty admin list', async () => {
      mockApiClient.listCommunityAdmins.mockResolvedValue([]);

      const mockInteraction = {
        user: { id: 'admin456' },
        guildId: 'guild789',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('admin'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('list'),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      await execute(mockInteraction as any);

      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: 'No admins found for this server.',
        })
      );
    });
  });

  describe('error handling', () => {
    it('should handle missing guildId', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: null,
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('admin'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('list'),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      await execute(mockInteraction as any);

      expect(mockInteraction.editReply).toHaveBeenCalledWith({
        content: 'This command can only be used in a server.',
      });
    });

    it('should handle API errors gracefully', async () => {
      mockApiClient.listCommunityAdmins.mockRejectedValue(new Error('API error'));

      const mockInteraction = {
        user: { id: 'admin456' },
        guildId: 'guild789',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('admin'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('list'),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      await execute(mockInteraction as any);

      expect(mockLogger.error).toHaveBeenCalled();
      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('Failed to process configuration command'),
        })
      );
    });
  });

  describe('ephemeral responses', () => {
    it('should use ephemeral flags for all responses', async () => {
      mockApiClient.listCommunityAdmins.mockResolvedValue([]);

      const mockInteraction = {
        user: { id: 'admin456' },
        guildId: 'guild789',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('admin'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('list'),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      await execute(mockInteraction as any);

      const v2EphemeralFlags = MessageFlags.Ephemeral | MessageFlags.IsComponentsV2;
      expect(mockInteraction.deferReply).toHaveBeenCalledWith({ flags: v2EphemeralFlags });
    });
  });
});
