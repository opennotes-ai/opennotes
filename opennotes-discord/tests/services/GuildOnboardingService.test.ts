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
  checkRecentScan: jest.fn<(communityServerId: string) => Promise<any>>(),
  updateWelcomeMessageId: jest.fn<(platformId: string, welcomeMessageId: string | null) => Promise<any>>(),
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

    const mockMessage = {
      id: 'message-456',
      pin: jest.fn<() => Promise<any>>().mockResolvedValue(undefined),
    };

    mockChannel = {
      id: 'channel-123',
      name: 'open-notes',
      guild: mockGuild,
      send: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue(mockMessage),
      messages: {
        fetchPinned: jest.fn<() => Promise<any>>().mockResolvedValue(new Map()),
        fetch: jest.fn<(id: string) => Promise<any>>(),
      },
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
        data: {
          type: 'community-servers',
          id: 'community-server-123',
          attributes: {
            platform: 'discord',
            platform_id: 'guild-123',
            name: 'Test Guild',
            is_active: true,
            is_public: true,
          },
        },
        jsonapi: { version: '1.1' },
      });
      mockApiClient.checkRecentScan.mockResolvedValue({
        data: {
          type: 'bulk-scan-status',
          id: 'status-123',
          attributes: { has_recent_scan: false },
        },
        jsonapi: { version: '1.1' },
      });

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
        data: {
          type: 'community-servers',
          id: 'community-server-123',
          attributes: {
            platform: 'discord',
            platform_id: 'guild-123',
            name: 'Test Guild',
            is_active: true,
            is_public: true,
          },
        },
        jsonapi: { version: '1.1' },
      });
      mockApiClient.checkRecentScan.mockResolvedValue({
        data: {
          type: 'bulk-scan-status',
          id: 'status-123',
          attributes: { has_recent_scan: true },
        },
        jsonapi: { version: '1.1' },
      });

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
        data: {
          type: 'community-servers',
          id: 'community-server-123',
          attributes: {
            platform: 'discord',
            platform_id: 'guild-123',
            name: 'Test Guild',
            is_active: true,
            is_public: true,
          },
        },
        jsonapi: { version: '1.1' },
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
        data: {
          type: 'community-servers',
          id: 'community-server-123',
          attributes: {
            platform: 'discord',
            platform_id: 'guild-123',
            name: 'Test Guild',
            is_active: true,
            is_public: true,
          },
        },
        jsonapi: { version: '1.1' },
      });
      mockApiClient.checkRecentScan.mockResolvedValue({
        data: {
          type: 'bulk-scan-status',
          id: 'status-123',
          attributes: { has_recent_scan: false },
        },
        jsonapi: { version: '1.1' },
      });
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
        data: {
          type: 'community-servers',
          id: 'community-server-123',
          attributes: {
            platform: 'discord',
            platform_id: 'guild-123',
            name: 'Test Guild',
            is_active: true,
            is_public: true,
          },
        },
        jsonapi: { version: '1.1' },
      });
      mockApiClient.checkRecentScan.mockResolvedValue({
        data: {
          type: 'bulk-scan-status',
          id: 'status-123',
          attributes: { has_recent_scan: false },
        },
        jsonapi: { version: '1.1' },
      });

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

  describe('Welcome Message Persistence (AC#3-5)', () => {
    let mockMessage: any;

    beforeEach(() => {
      mockMessage = {
        id: 'message-456',
        pin: jest.fn<() => Promise<any>>().mockResolvedValue(undefined),
      };
      mockChannel.send.mockResolvedValue(mockMessage);
      mockApiClient.getCommunityServerByPlatformId.mockReset();
      mockApiClient.updateWelcomeMessageId.mockReset();
      mockApiClient.updateWelcomeMessageId.mockResolvedValue({
        id: 'community-server-123',
        platform_id: 'guild-123',
        welcome_message_id: 'message-456',
      });
    });

    it('should pin the welcome message after posting (AC#3)', async () => {
      mockApiClient.getCommunityServerByPlatformId.mockResolvedValue({
        data: {
          type: 'community-servers',
          id: 'community-server-123',
          attributes: {
            platform: 'discord',
            platform_id: 'guild-123',
            name: 'Test Guild',
            is_active: true,
            is_public: true,
            welcome_message_id: null,
          },
        },
        jsonapi: { version: '1.1' },
      });

      await service.postWelcomeToChannel(mockChannel);

      expect(mockMessage.pin).toHaveBeenCalled();
    });

    it('should update welcome_message_id in database after posting and pinning (AC#5)', async () => {
      mockApiClient.getCommunityServerByPlatformId.mockResolvedValue({
        data: {
          type: 'community-servers',
          id: 'community-server-123',
          attributes: {
            platform: 'discord',
            platform_id: 'guild-123',
            name: 'Test Guild',
            is_active: true,
            is_public: true,
            welcome_message_id: null,
          },
        },
        jsonapi: { version: '1.1' },
      });

      await service.postWelcomeToChannel(mockChannel);

      expect(mockApiClient.updateWelcomeMessageId).toHaveBeenCalledWith('guild-123', 'message-456');
    });

    it('should skip posting if welcome message already exists in channel pins (AC#4)', async () => {
      const existingWelcomeMessageId = 'existing-welcome-123';
      const existingMessage = {
        id: existingWelcomeMessageId,
        pin: jest.fn(),
      };
      const pinnedMessages = new Map([[existingWelcomeMessageId, existingMessage]]);
      mockChannel.messages.fetchPinned.mockResolvedValue(pinnedMessages);

      mockApiClient.getCommunityServerByPlatformId.mockResolvedValue({
        data: {
          type: 'community-servers',
          id: 'community-server-123',
          attributes: {
            platform: 'discord',
            platform_id: 'guild-123',
            name: 'Test Guild',
            is_active: true,
            is_public: true,
            welcome_message_id: existingWelcomeMessageId,
          },
        },
        jsonapi: { version: '1.1' },
      });

      await service.postWelcomeToChannel(mockChannel);

      expect(mockChannel.send).not.toHaveBeenCalled();
      expect(mockLogger.debug).toHaveBeenCalledWith(
        'Welcome message already exists in channel pins',
        expect.objectContaining({
          guildId: 'guild-123',
          welcomeMessageId: existingWelcomeMessageId,
        })
      );
    });

    it('should post new welcome message if stored message is not found in pins (AC#5)', async () => {
      const staleWelcomeMessageId = 'deleted-message-123';
      const pinnedMessages = new Map(); // Empty - message was deleted
      mockChannel.messages.fetchPinned.mockResolvedValue(pinnedMessages);

      mockApiClient.getCommunityServerByPlatformId.mockResolvedValue({
        data: {
          type: 'community-servers',
          id: 'community-server-123',
          attributes: {
            platform: 'discord',
            platform_id: 'guild-123',
            name: 'Test Guild',
            is_active: true,
            is_public: true,
            welcome_message_id: staleWelcomeMessageId,
          },
        },
        jsonapi: { version: '1.1' },
      });

      await service.postWelcomeToChannel(mockChannel);

      expect(mockChannel.send).toHaveBeenCalledTimes(1);
      expect(mockMessage.pin).toHaveBeenCalled();
      expect(mockApiClient.updateWelcomeMessageId).toHaveBeenCalledWith('guild-123', 'message-456');
    });

    it('should log when reposting welcome message due to missing pin', async () => {
      const staleWelcomeMessageId = 'deleted-message-123';
      const pinnedMessages = new Map();
      mockChannel.messages.fetchPinned.mockResolvedValue(pinnedMessages);

      mockApiClient.getCommunityServerByPlatformId.mockResolvedValue({
        data: {
          type: 'community-servers',
          id: 'community-server-123',
          attributes: {
            platform: 'discord',
            platform_id: 'guild-123',
            name: 'Test Guild',
            is_active: true,
            is_public: true,
            welcome_message_id: staleWelcomeMessageId,
          },
        },
        jsonapi: { version: '1.1' },
      });

      await service.postWelcomeToChannel(mockChannel);

      expect(mockLogger.info).toHaveBeenCalledWith(
        'Stored welcome message not found in pins, posting new one',
        expect.objectContaining({
          guildId: 'guild-123',
          staleWelcomeMessageId: staleWelcomeMessageId,
        })
      );
    });

    it('should handle pin failure gracefully', async () => {
      mockMessage.pin.mockRejectedValue(new Error('Missing pin permissions'));
      mockApiClient.getCommunityServerByPlatformId.mockResolvedValue({
        data: {
          type: 'community-servers',
          id: 'community-server-123',
          attributes: {
            platform: 'discord',
            platform_id: 'guild-123',
            name: 'Test Guild',
            is_active: true,
            is_public: true,
            welcome_message_id: null,
          },
        },
        jsonapi: { version: '1.1' },
      });

      await expect(service.postWelcomeToChannel(mockChannel)).resolves.not.toThrow();

      expect(mockLogger.warn).toHaveBeenCalledWith(
        'Failed to pin welcome message',
        expect.objectContaining({
          guildId: 'guild-123',
          error: 'Missing pin permissions',
        })
      );
    });

    it('should handle updateWelcomeMessageId API failure gracefully', async () => {
      mockApiClient.getCommunityServerByPlatformId.mockResolvedValue({
        data: {
          type: 'community-servers',
          id: 'community-server-123',
          attributes: {
            platform: 'discord',
            platform_id: 'guild-123',
            name: 'Test Guild',
            is_active: true,
            is_public: true,
            welcome_message_id: null,
          },
        },
        jsonapi: { version: '1.1' },
      });
      mockApiClient.updateWelcomeMessageId.mockRejectedValue(new Error('API error'));

      await expect(service.postWelcomeToChannel(mockChannel)).resolves.not.toThrow();

      expect(mockLogger.warn).toHaveBeenCalledWith(
        'Failed to update welcome_message_id in database',
        expect.objectContaining({
          guildId: 'guild-123',
          error: 'API error',
        })
      );
    });
  });
});
