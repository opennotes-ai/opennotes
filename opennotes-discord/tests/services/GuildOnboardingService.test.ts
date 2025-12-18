import { describe, it, expect, beforeEach, afterEach, jest } from '@jest/globals';
import { MessageFlags, ContainerBuilder } from 'discord.js';
import { V2_COLORS } from '../../src/utils/v2-components.js';

const mockLogger = {
  info: jest.fn<(...args: unknown[]) => void>(),
  debug: jest.fn<(...args: unknown[]) => void>(),
  error: jest.fn<(...args: unknown[]) => void>(),
  warn: jest.fn<(...args: unknown[]) => void>(),
};

const mockApiClient = {
  getCommunityServerByPlatformId: jest.fn<(platformId: string, platform?: string) => Promise<any>>(),
  checkRecentScan: jest.fn<(communityServerId: string) => Promise<boolean>>(),
};

const mockSendVibeCheckPrompt = jest.fn<(options: any) => Promise<void>>().mockResolvedValue(undefined);

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
}));

jest.unstable_mockModule('../../src/api-client.js', () => ({
  apiClient: mockApiClient,
}));

jest.unstable_mockModule('../../src/lib/vibecheck-prompt.js', () => ({
  sendVibeCheckPrompt: mockSendVibeCheckPrompt,
}));

const { GuildOnboardingService } = await import('../../src/services/GuildOnboardingService.js');

describe('GuildOnboardingService', () => {
  let service: InstanceType<typeof GuildOnboardingService>;
  let mockChannel: any;
  let mockGuild: any;
  let mockAdmin: any;

  beforeEach(() => {
    mockGuild = {
      id: 'guild-123',
      name: 'Test Guild',
    };

    mockChannel = {
      id: 'channel-123',
      name: 'open-notes',
      guild: mockGuild,
      send: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}),
    };

    mockAdmin = {
      id: 'admin-123',
      username: 'testadmin',
      createDM: jest.fn<() => Promise<any>>().mockResolvedValue({
        send: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}),
      }),
    };

    service = new GuildOnboardingService();
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe('postWelcomeToChannel', () => {
    it('should send welcome message to channel', async () => {
      await service.postWelcomeToChannel(mockChannel);

      expect(mockChannel.send).toHaveBeenCalledTimes(1);
    });

    it('should send Components v2 message with container', async () => {
      await service.postWelcomeToChannel(mockChannel);

      const sendCall = mockChannel.send.mock.calls[0][0];
      expect(sendCall).toHaveProperty('components');
      expect(sendCall.components).toHaveLength(1);
      expect(sendCall.components[0]).toBeInstanceOf(ContainerBuilder);
    });

    it('should use IsComponentsV2 flag without ephemeral', async () => {
      await service.postWelcomeToChannel(mockChannel);

      const sendCall = mockChannel.send.mock.calls[0][0];
      expect(sendCall.flags & MessageFlags.IsComponentsV2).toBeTruthy();
      expect(sendCall.flags & MessageFlags.Ephemeral).toBeFalsy();
    });

    it('should use PRIMARY accent color on container', async () => {
      await service.postWelcomeToChannel(mockChannel);

      const sendCall = mockChannel.send.mock.calls[0][0];
      const container = sendCall.components[0];
      expect(container.data.accent_color).toBe(V2_COLORS.PRIMARY);
    });

    it('should include About OpenNotes header', async () => {
      await service.postWelcomeToChannel(mockChannel);

      const sendCall = mockChannel.send.mock.calls[0][0];
      const container = sendCall.components[0];
      const allContent = JSON.stringify(container.toJSON().components);

      expect(allContent).toContain('About OpenNotes');
    });

    it('should include all information sections', async () => {
      await service.postWelcomeToChannel(mockChannel);

      const sendCall = mockChannel.send.mock.calls[0][0];
      const container = sendCall.components[0];
      const allContent = JSON.stringify(container.toJSON().components);

      expect(allContent).toContain('How It Works');
      expect(allContent).toContain('Note Submission');
      expect(allContent).toContain('Commands');
      expect(allContent).toContain('Scoring System');
      expect(allContent).toContain('Community Moderation');
    });

    it('should log successful message posting', async () => {
      await service.postWelcomeToChannel(mockChannel);

      expect(mockLogger.info).toHaveBeenCalledWith(
        'Posted welcome message to bot channel',
        expect.objectContaining({
          channelId: 'channel-123',
          guildId: 'guild-123',
          channelName: 'open-notes',
        })
      );
    });

    it('should handle send errors gracefully without throwing', async () => {
      mockChannel.send.mockRejectedValue(new Error('Missing permissions'));

      await expect(service.postWelcomeToChannel(mockChannel)).resolves.not.toThrow();
    });

    it('should log errors when send fails', async () => {
      mockChannel.send.mockRejectedValue(new Error('Missing permissions'));

      await service.postWelcomeToChannel(mockChannel);

      expect(mockLogger.error).toHaveBeenCalledWith(
        'Failed to post welcome message to bot channel',
        expect.objectContaining({
          channelId: 'channel-123',
          guildId: 'guild-123',
          error: 'Missing permissions',
        })
      );
    });

    it('should not include embeds (using v2 components instead)', async () => {
      await service.postWelcomeToChannel(mockChannel);

      const sendCall = mockChannel.send.mock.calls[0][0];
      expect(sendCall.embeds).toBeUndefined();
    });
  });

  describe('Vibe Check Prompt', () => {
    beforeEach(() => {
      mockApiClient.getCommunityServerByPlatformId.mockReset();
      mockApiClient.checkRecentScan.mockReset();
      mockSendVibeCheckPrompt.mockReset();
      mockSendVibeCheckPrompt.mockResolvedValue(undefined);
    });

    it('should send vibe check prompt when admin is provided and no recent scan exists', async () => {
      mockApiClient.getCommunityServerByPlatformId.mockResolvedValue({
        id: 'community-server-123',
        platform: 'discord',
        platform_id: 'guild-123',
        name: 'Test Guild',
        is_active: true,
      });
      mockApiClient.checkRecentScan.mockResolvedValue(false);

      await service.postWelcomeToChannel(mockChannel, { admin: mockAdmin });

      expect(mockSendVibeCheckPrompt).toHaveBeenCalledWith({
        botChannel: mockChannel,
        admin: mockAdmin,
        guildId: 'guild-123',
      });
    });

    it('should not send vibe check prompt when admin is not provided', async () => {
      await service.postWelcomeToChannel(mockChannel);

      expect(mockSendVibeCheckPrompt).not.toHaveBeenCalled();
    });

    it('should not send vibe check prompt when skipVibeCheckPrompt is true', async () => {
      await service.postWelcomeToChannel(mockChannel, {
        admin: mockAdmin,
        skipVibeCheckPrompt: true,
      });

      expect(mockSendVibeCheckPrompt).not.toHaveBeenCalled();
    });

    it('should not send vibe check prompt when community has recent scan', async () => {
      mockApiClient.getCommunityServerByPlatformId.mockResolvedValue({
        id: 'community-server-123',
        platform: 'discord',
        platform_id: 'guild-123',
        name: 'Test Guild',
        is_active: true,
      });
      mockApiClient.checkRecentScan.mockResolvedValue(true);

      await service.postWelcomeToChannel(mockChannel, { admin: mockAdmin });

      expect(mockSendVibeCheckPrompt).not.toHaveBeenCalled();
    });

    it('should not send vibe check prompt when community server lookup fails', async () => {
      mockApiClient.getCommunityServerByPlatformId.mockRejectedValue(new Error('Not found'));

      await service.postWelcomeToChannel(mockChannel, { admin: mockAdmin });

      expect(mockSendVibeCheckPrompt).not.toHaveBeenCalled();
      expect(mockLogger.debug).toHaveBeenCalledWith(
        'Community server not found, skipping vibe check prompt',
        expect.objectContaining({ guildId: 'guild-123' })
      );
    });

    it('should send vibe check prompt even if recent scan check fails', async () => {
      mockApiClient.getCommunityServerByPlatformId.mockResolvedValue({
        id: 'community-server-123',
        platform: 'discord',
        platform_id: 'guild-123',
        name: 'Test Guild',
        is_active: true,
      });
      mockApiClient.checkRecentScan.mockRejectedValue(new Error('API error'));

      await service.postWelcomeToChannel(mockChannel, { admin: mockAdmin });

      expect(mockSendVibeCheckPrompt).toHaveBeenCalledWith({
        botChannel: mockChannel,
        admin: mockAdmin,
        guildId: 'guild-123',
      });
      expect(mockLogger.debug).toHaveBeenCalledWith(
        'Failed to check recent scan, will show prompt anyway',
        expect.objectContaining({
          guildId: 'guild-123',
          communityServerId: 'community-server-123',
        })
      );
    });

    it('should handle vibe check prompt errors gracefully', async () => {
      mockApiClient.getCommunityServerByPlatformId.mockResolvedValue({
        id: 'community-server-123',
        platform: 'discord',
        platform_id: 'guild-123',
        name: 'Test Guild',
        is_active: true,
      });
      mockApiClient.checkRecentScan.mockResolvedValue(false);
      mockSendVibeCheckPrompt.mockRejectedValue(new Error('Discord API error'));

      await expect(
        service.postWelcomeToChannel(mockChannel, { admin: mockAdmin })
      ).resolves.not.toThrow();

      expect(mockLogger.error).toHaveBeenCalledWith(
        'Failed to send vibe check prompt',
        expect.objectContaining({
          channelId: 'channel-123',
          guildId: 'guild-123',
          adminId: 'admin-123',
        })
      );
    });

    it('should log successful vibe check prompt send', async () => {
      mockApiClient.getCommunityServerByPlatformId.mockResolvedValue({
        id: 'community-server-123',
        platform: 'discord',
        platform_id: 'guild-123',
        name: 'Test Guild',
        is_active: true,
      });
      mockApiClient.checkRecentScan.mockResolvedValue(false);

      await service.postWelcomeToChannel(mockChannel, { admin: mockAdmin });

      expect(mockLogger.info).toHaveBeenCalledWith(
        'Sent vibe check prompt to admin in bot channel',
        expect.objectContaining({
          channelId: 'channel-123',
          guildId: 'guild-123',
          adminId: 'admin-123',
        })
      );
    });
  });
});
