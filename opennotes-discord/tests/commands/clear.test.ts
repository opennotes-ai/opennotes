import { jest } from '@jest/globals';
import { MessageFlags, PermissionsBitField } from 'discord.js';
import { loggerFactory, cacheFactory, adminMemberFactory } from '../factories/index.js';

const mockLogger = loggerFactory.build();
const mockCache = cacheFactory.build();

const mockApiClient = {
  getCommunityServerByPlatformId: jest.fn<(guildId: string) => Promise<any>>(),
  getClearPreview: jest.fn<(endpoint: string) => Promise<any>>(),
  executeClear: jest.fn<(endpoint: string) => Promise<any>>(),
};

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
}));

jest.unstable_mockModule('../../src/cache.js', () => ({
  cache: mockCache,
}));

jest.unstable_mockModule('../../src/api-client.js', () => ({
  apiClient: mockApiClient,
}));

jest.unstable_mockModule('../../src/lib/errors.js', () => ({
  generateErrorId: () => 'test-error-id',
  extractErrorDetails: (error: any) => ({
    message: error?.message || 'Unknown error',
    type: error?.constructor?.name || 'Error',
    stack: error?.stack || '',
  }),
  formatErrorForUser: (errorId: string, message: string) => `${message} (Error ID: ${errorId})`,
}));

jest.unstable_mockModule('../../src/lib/permissions.js', () => ({
  hasManageGuildPermission: jest.fn<(member: any) => boolean>(),
}));

const { execute, data } = await import('../../src/commands/clear.js');
const { hasManageGuildPermission } = await import('../../src/lib/permissions.js');
const mockHasManageGuildPermission = hasManageGuildPermission as jest.MockedFunction<typeof hasManageGuildPermission>;

describe('clear command', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockHasManageGuildPermission.mockReturnValue(true);
  });

  describe('command definition', () => {
    it('should have correct name', () => {
      expect(data.name).toBe('clear');
    });

    it('should have requests and notes subcommands', () => {
      const json = data.toJSON();
      expect(json.options).toHaveLength(2);
      const subcommandNames = json.options!.map((opt: any) => opt.name);
      expect(subcommandNames).toContain('requests');
      expect(subcommandNames).toContain('notes');
    });

    it('should require ManageGuild permission', () => {
      const json = data.toJSON();
      expect(json.default_member_permissions).toBe(PermissionsBitField.Flags.ManageGuild.toString());
    });

    it('should not allow DM usage', () => {
      const json = data.toJSON();
      expect(json.dm_permission).toBe(false);
    });
  });

  describe('execute', () => {
    describe('guild checks', () => {
      it('should reject DM usage', async () => {
        const mockInteraction = {
          user: { id: 'user123' },
          guildId: null,
          guild: null,
          reply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        };

        await execute(mockInteraction as any);

        expect(mockInteraction.reply).toHaveBeenCalledWith({
          content: 'This command can only be used in a server.',
          flags: MessageFlags.Ephemeral,
        });
      });
    });

    describe('permission checks', () => {
      it('should reject users without ManageGuild permission', async () => {
        mockHasManageGuildPermission.mockReturnValue(false);

        const mockInteraction = {
          user: { id: 'user123' },
          guildId: 'guild456',
          guild: { name: 'Test Guild' },
          member: { permissions: new PermissionsBitField() },
          reply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        };

        await execute(mockInteraction as any);

        expect(mockInteraction.reply).toHaveBeenCalledWith({
          content: 'You need the "Manage Server" permission to use this command.',
          flags: MessageFlags.Ephemeral,
        });
      });
    });

    describe('mode validation', () => {
      it('should reject invalid mode', async () => {
        const mockInteraction = {
          user: { id: 'user123' },
          guildId: 'guild456',
          guild: { name: 'Test Guild' },
          member: adminMemberFactory.build(),
          options: {
            getSubcommand: jest.fn<() => string>().mockReturnValue('requests'),
            getString: jest.fn<(name: string, required: boolean) => string>().mockReturnValue('invalid'),
          },
          reply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        };

        await execute(mockInteraction as any);

        expect(mockInteraction.reply).toHaveBeenCalledWith({
          content: "Invalid mode. Please use 'all' or a positive number of days (e.g., '30').",
          flags: MessageFlags.Ephemeral,
        });
      });

      it('should reject negative days', async () => {
        const mockInteraction = {
          user: { id: 'user123' },
          guildId: 'guild456',
          guild: { name: 'Test Guild' },
          member: adminMemberFactory.build(),
          options: {
            getSubcommand: jest.fn<() => string>().mockReturnValue('requests'),
            getString: jest.fn<(name: string, required: boolean) => string>().mockReturnValue('-5'),
          },
          reply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        };

        await execute(mockInteraction as any);

        expect(mockInteraction.reply).toHaveBeenCalledWith({
          content: "Invalid mode. Please use 'all' or a positive number of days (e.g., '30').",
          flags: MessageFlags.Ephemeral,
        });
      });

      it('should accept "all" mode', async () => {
        mockApiClient.getCommunityServerByPlatformId.mockResolvedValue({
          data: { id: 'community-uuid' },
        });
        mockApiClient.getClearPreview.mockResolvedValue({
          wouldDeleteCount: 0,
          message: 'Would delete 0 requests',
        });

        const mockInteraction = {
          user: { id: 'user123' },
          guildId: 'guild456',
          guild: { name: 'Test Guild' },
          member: adminMemberFactory.build(),
          options: {
            getSubcommand: jest.fn<() => string>().mockReturnValue('requests'),
            getString: jest.fn<(name: string, required: boolean) => string>().mockReturnValue('all'),
          },
          deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
          editReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        };

        await execute(mockInteraction as any);

        expect(mockInteraction.deferReply).toHaveBeenCalled();
        expect(mockApiClient.getCommunityServerByPlatformId).toHaveBeenCalledWith('guild456');
      });

      it('should accept numeric days mode', async () => {
        mockApiClient.getCommunityServerByPlatformId.mockResolvedValue({
          data: { id: 'community-uuid' },
        });
        mockApiClient.getClearPreview.mockResolvedValue({
          wouldDeleteCount: 0,
          message: 'Would delete 0 requests',
        });

        const mockInteraction = {
          user: { id: 'user123' },
          guildId: 'guild456',
          guild: { name: 'Test Guild' },
          member: adminMemberFactory.build(),
          options: {
            getSubcommand: jest.fn<() => string>().mockReturnValue('requests'),
            getString: jest.fn<(name: string, required: boolean) => string>().mockReturnValue('30'),
          },
          deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
          editReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        };

        await execute(mockInteraction as any);

        expect(mockInteraction.deferReply).toHaveBeenCalled();
        expect(mockApiClient.getClearPreview).toHaveBeenCalled();
      });
    });

    describe('no items to delete', () => {
      it('should report no requests found for all mode', async () => {
        mockApiClient.getCommunityServerByPlatformId.mockResolvedValue({
          data: { id: 'community-uuid' },
        });
        mockApiClient.getClearPreview.mockResolvedValue({
          wouldDeleteCount: 0,
          message: 'Would delete 0 requests',
        });

        const mockInteraction = {
          user: { id: 'user123' },
          guildId: 'guild456',
          guild: { name: 'Test Guild' },
          member: adminMemberFactory.build(),
          options: {
            getSubcommand: jest.fn<() => string>().mockReturnValue('requests'),
            getString: jest.fn<(name: string, required: boolean) => string>().mockReturnValue('all'),
          },
          deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
          editReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        };

        await execute(mockInteraction as any);

        expect(mockInteraction.editReply).toHaveBeenCalledWith({
          content: 'No requests found to delete.',
        });
      });

      it('should report no notes found with days filter', async () => {
        mockApiClient.getCommunityServerByPlatformId.mockResolvedValue({
          data: { id: 'community-uuid' },
        });
        mockApiClient.getClearPreview.mockResolvedValue({
          wouldDeleteCount: 0,
          message: 'Would delete 0 notes',
        });

        const mockInteraction = {
          user: { id: 'user123' },
          guildId: 'guild456',
          guild: { name: 'Test Guild' },
          member: adminMemberFactory.build(),
          options: {
            getSubcommand: jest.fn<() => string>().mockReturnValue('notes'),
            getString: jest.fn<(name: string, required: boolean) => string>().mockReturnValue('30'),
          },
          deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
          editReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        };

        await execute(mockInteraction as any);

        expect(mockInteraction.editReply).toHaveBeenCalledWith({
          content: 'No unpublished notes older than 30 days found to delete.',
        });
      });
    });

    describe('error handling', () => {
      it('should handle API errors gracefully', async () => {
        mockApiClient.getCommunityServerByPlatformId.mockRejectedValue(new Error('API Error'));

        const mockInteraction = {
          user: { id: 'user123' },
          guildId: 'guild456',
          guild: { name: 'Test Guild' },
          member: adminMemberFactory.build(),
          options: {
            getSubcommand: jest.fn<() => string>().mockReturnValue('requests'),
            getString: jest.fn<(name: string, required: boolean) => string>().mockReturnValue('all'),
          },
          deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
          editReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        };

        await execute(mockInteraction as any);

        expect(mockLogger.error).toHaveBeenCalledWith(
          'Clear command failed',
          expect.objectContaining({
            error: 'API Error',
          })
        );
        expect(mockInteraction.editReply).toHaveBeenCalledWith({
          content: expect.stringContaining('Failed to process clear request'),
        });
      });
    });

    describe('confirmation flow', () => {
      it('should show confirmation when items would be deleted', async () => {
        mockApiClient.getCommunityServerByPlatformId.mockResolvedValue({
          data: { id: 'community-uuid' },
        });
        mockApiClient.getClearPreview.mockResolvedValue({
          wouldDeleteCount: 15,
          message: 'Would delete 15 requests',
        });

        const mockCollector = {
          on: jest.fn<(event: string, handler: any) => any>(),
        };

        const mockReply = {
          createMessageComponentCollector: jest.fn<() => any>().mockReturnValue(mockCollector),
        };

        const mockInteraction = {
          user: { id: 'user123' },
          guildId: 'guild456',
          guild: { name: 'Test Guild' },
          member: adminMemberFactory.build(),
          options: {
            getSubcommand: jest.fn<() => string>().mockReturnValue('requests'),
            getString: jest.fn<(name: string, required: boolean) => string>().mockReturnValue('all'),
          },
          deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
          editReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
          fetchReply: jest.fn<() => Promise<any>>().mockResolvedValue(mockReply),
        };

        await execute(mockInteraction as any);

        expect(mockInteraction.editReply).toHaveBeenCalledWith(
          expect.objectContaining({
            content: expect.stringContaining('15'),
            components: expect.any(Array),
          })
        );
        expect(mockCache.set).toHaveBeenCalledWith(
          expect.stringMatching(/^clear:confirmation:/),
          expect.objectContaining({
            type: 'requests',
            mode: 'all',
            wouldDeleteCount: 15,
          }),
          300
        );
      });
    });
  });
});
