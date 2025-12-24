import { describe, it, expect, beforeEach, afterEach, jest } from '@jest/globals';
import { MessageFlags, ContainerBuilder, Collection, MessageType } from 'discord.js';
import { V2_COLORS } from '../../src/utils/v2-components.js';
import { buildWelcomeContainer } from '../../src/lib/welcome-content.js';

// Helper to create a Collection from entries (mimics Discord.js Collection)
function createMockCollection<K, V>(entries: [K, V][]): Collection<K, V> {
  return new Collection(entries);
}

// Get the actual welcome content signature for content comparison tests
function getActualWelcomeContentSignature(): object {
  return buildWelcomeContainer().toJSON();
}

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

    const mockBotUser = {
      id: 'bot-user-123',
      username: 'OpenNotes',
      bot: true,
    };

    mockChannel = {
      id: 'channel-123',
      name: 'open-notes',
      guild: mockGuild,
      client: {
        user: mockBotUser,
      },
      send: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue(mockMessage),
      messages: {
        fetchPinned: jest.fn<() => Promise<any>>().mockResolvedValue(createMockCollection([])),
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
      // Mock message must have author matching bot user and actual welcome content
      const actualWelcomeContent = getActualWelcomeContentSignature();
      const existingMessage = {
        id: existingWelcomeMessageId,
        author: { id: 'bot-user-123' },
        components: [{ type: 17, toJSON: () => actualWelcomeContent }],
        pin: jest.fn(),
      };
      const pinnedMessages = createMockCollection([[existingWelcomeMessageId, existingMessage]]);
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
        'Welcome message with same content already exists',
        expect.objectContaining({
          guildId: 'guild-123',
          messageId: existingWelcomeMessageId,
        })
      );
    });

    it('should post new welcome message if stored message is not found in pins (AC#5)', async () => {
      const staleWelcomeMessageId = 'deleted-message-123';
      const pinnedMessages = createMockCollection([]); // Empty - message was deleted
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
      const pinnedMessages = createMockCollection([]);
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

  describe('Welcome Message Idempotency - Content-Based (task-870)', () => {
    let mockMessage: any;
    let mockBotUser: any;

    beforeEach(() => {
      mockMessage = {
        id: 'message-456',
        pin: jest.fn<() => Promise<any>>().mockResolvedValue(undefined),
      };
      mockChannel.send.mockResolvedValue(mockMessage);

      mockBotUser = {
        id: 'bot-user-123',
        username: 'OpenNotes',
        bot: true,
      };

      // Add bot user to channel's client
      mockChannel.client = {
        user: mockBotUser,
      };

      mockApiClient.getCommunityServerByPlatformId.mockReset();
      mockApiClient.updateWelcomeMessageId.mockReset();
      mockApiClient.updateWelcomeMessageId.mockResolvedValue({
        id: 'community-server-123',
        platform_id: 'guild-123',
        welcome_message_id: 'message-456',
      });
    });

    describe('AC#1: Search by bot author instead of stored message ID', () => {
      it('should find existing welcome message by bot author when stored ID is missing', async () => {
        // Existing welcome message from the bot (not tracked in DB)
        // Must use actual welcome content for content comparison to match
        const actualWelcomeContent = getActualWelcomeContentSignature();
        const existingBotMessage = {
          id: 'untracked-welcome-123',
          author: mockBotUser,
          components: [{ type: 17, toJSON: () => actualWelcomeContent }],
          delete: jest.fn<() => Promise<any>>().mockResolvedValue(undefined),
        };
        const pinnedMessages = createMockCollection([['untracked-welcome-123', existingBotMessage]]);
        mockChannel.messages.fetchPinned.mockResolvedValue(pinnedMessages);

        // DB has no welcome_message_id stored
        mockApiClient.getCommunityServerByPlatformId.mockResolvedValue({
          data: {
            type: 'community-servers',
            id: 'community-server-123',
            attributes: {
              platform: 'discord',
              platform_id: 'guild-123',
              name: 'Test Guild',
              welcome_message_id: null, // Not tracked
            },
          },
          jsonapi: { version: '1.1' },
        });

        await service.postWelcomeToChannel(mockChannel);

        // Should NOT post a new message since bot's welcome already exists
        expect(mockChannel.send).not.toHaveBeenCalled();
      });
    });

    describe('AC#2-3: Content comparison', () => {
      it('should not repost if existing welcome has same content', async () => {
        // Create a mock existing message with actual welcome content
        const actualWelcomeContent = getActualWelcomeContentSignature();
        const existingBotMessage = {
          id: 'existing-welcome-123',
          author: mockBotUser,
          components: [{ type: 17, toJSON: () => actualWelcomeContent }],
          delete: jest.fn<() => Promise<any>>().mockResolvedValue(undefined),
        };
        const pinnedMessages = createMockCollection([['existing-welcome-123', existingBotMessage]]);
        mockChannel.messages.fetchPinned.mockResolvedValue(pinnedMessages);

        mockApiClient.getCommunityServerByPlatformId.mockResolvedValue({
          data: {
            type: 'community-servers',
            id: 'community-server-123',
            attributes: {
              platform: 'discord',
              platform_id: 'guild-123',
              name: 'Test Guild',
              welcome_message_id: 'existing-welcome-123',
            },
          },
          jsonapi: { version: '1.1' },
        });

        await service.postWelcomeToChannel(mockChannel);

        // Should not send new message - content is same
        expect(mockChannel.send).not.toHaveBeenCalled();
        // Should not delete old message
        expect(existingBotMessage.delete).not.toHaveBeenCalled();
      });
    });

    describe('AC#4: Delete old message when content changes', () => {
      it('should delete old welcome and post new when content differs', async () => {
        // Existing welcome with DIFFERENT content (e.g., old version)
        // toJSON returns different structure so content comparison fails
        const existingBotMessage = {
          id: 'old-welcome-123',
          author: mockBotUser,
          components: [{ type: 17, toJSON: () => ({ type: 17, content: 'Old welcome text' }) }],
          delete: jest.fn<() => Promise<any>>().mockResolvedValue(undefined),
        };
        const pinnedMessages = createMockCollection([['old-welcome-123', existingBotMessage]]);
        mockChannel.messages.fetchPinned.mockResolvedValue(pinnedMessages);

        mockApiClient.getCommunityServerByPlatformId.mockResolvedValue({
          data: {
            type: 'community-servers',
            id: 'community-server-123',
            attributes: {
              platform: 'discord',
              platform_id: 'guild-123',
              name: 'Test Guild',
              welcome_message_id: 'old-welcome-123',
            },
          },
          jsonapi: { version: '1.1' },
        });

        await service.postWelcomeToChannel(mockChannel);

        // Should delete the old message
        expect(existingBotMessage.delete).toHaveBeenCalled();
        // Should post new message
        expect(mockChannel.send).toHaveBeenCalledTimes(1);
      });
    });

    describe('AC#8: Handle multiple identical pinned messages', () => {
      it('should delete duplicate welcome messages keeping only one', async () => {
        // Three identical welcome messages pinned (duplicates from bug)
        // All have same content as current welcome
        const actualWelcomeContent = getActualWelcomeContentSignature();
        const welcomeMessage1 = {
          id: 'welcome-1',
          author: mockBotUser,
          components: [{ type: 17, toJSON: () => actualWelcomeContent }],
          delete: jest.fn<() => Promise<any>>().mockResolvedValue(undefined),
        };
        const welcomeMessage2 = {
          id: 'welcome-2',
          author: mockBotUser,
          components: [{ type: 17, toJSON: () => actualWelcomeContent }],
          delete: jest.fn<() => Promise<any>>().mockResolvedValue(undefined),
        };
        const welcomeMessage3 = {
          id: 'welcome-3',
          author: mockBotUser,
          components: [{ type: 17, toJSON: () => actualWelcomeContent }],
          delete: jest.fn<() => Promise<any>>().mockResolvedValue(undefined),
        };
        const pinnedMessages = createMockCollection([
          ['welcome-1', welcomeMessage1],
          ['welcome-2', welcomeMessage2],
          ['welcome-3', welcomeMessage3],
        ]);
        mockChannel.messages.fetchPinned.mockResolvedValue(pinnedMessages);

        mockApiClient.getCommunityServerByPlatformId.mockResolvedValue({
          data: {
            type: 'community-servers',
            id: 'community-server-123',
            attributes: {
              platform: 'discord',
              platform_id: 'guild-123',
              name: 'Test Guild',
              welcome_message_id: 'welcome-1',
            },
          },
          jsonapi: { version: '1.1' },
        });

        await service.postWelcomeToChannel(mockChannel);

        // Should delete 2 duplicates, keep 1
        const deleteCalls = [
          welcomeMessage1.delete.mock.calls.length,
          welcomeMessage2.delete.mock.calls.length,
          welcomeMessage3.delete.mock.calls.length,
        ].reduce((sum, count) => sum + count, 0);
        expect(deleteCalls).toBe(2);

        // Should not post new message (one already exists)
        expect(mockChannel.send).not.toHaveBeenCalled();
      });
    });

    describe('AC#6: Handle API failures gracefully', () => {
      it('should not post if Discord fetchPinned fails', async () => {
        // Can't verify Discord state - don't post to avoid duplicates
        mockChannel.messages.fetchPinned.mockRejectedValue(
          new Error('Missing permissions')
        );

        await service.postWelcomeToChannel(mockChannel);

        // Should NOT post when we can't check Discord pins
        expect(mockChannel.send).not.toHaveBeenCalled();
        expect(mockLogger.warn).toHaveBeenCalledWith(
          expect.stringContaining('Cannot verify welcome message state'),
          expect.objectContaining({
            guildId: 'guild-123',
          })
        );
      });

      it('should still post if API fails but Discord shows no welcome message', async () => {
        // Discord (source of truth) shows no welcome messages
        mockChannel.messages.fetchPinned.mockResolvedValue(createMockCollection([]));
        // API fails
        mockApiClient.getCommunityServerByPlatformId.mockRejectedValue(
          new Error('500 Internal Server Error')
        );

        await service.postWelcomeToChannel(mockChannel);

        // Should still post - Discord is the source of truth
        expect(mockChannel.send).toHaveBeenCalledTimes(1);
        expect(mockLogger.debug).toHaveBeenCalledWith(
          'API unavailable, proceeding based on Discord state',
          expect.objectContaining({
            guildId: 'guild-123',
          })
        );
      });

      it('should update DB with found message ID if DB record is stale', async () => {
        // Bot's welcome exists but DB has wrong/missing ID
        // Must use actual welcome content for content comparison to match
        const actualWelcomeContent = getActualWelcomeContentSignature();
        const existingBotMessage = {
          id: 'found-welcome-123',
          author: mockBotUser,
          components: [{ type: 17, toJSON: () => actualWelcomeContent }],
          delete: jest.fn<() => Promise<any>>().mockResolvedValue(undefined),
        };
        const pinnedMessages = createMockCollection([['found-welcome-123', existingBotMessage]]);
        mockChannel.messages.fetchPinned.mockResolvedValue(pinnedMessages);

        mockApiClient.getCommunityServerByPlatformId.mockResolvedValue({
          data: {
            type: 'community-servers',
            id: 'community-server-123',
            attributes: {
              platform: 'discord',
              platform_id: 'guild-123',
              name: 'Test Guild',
              welcome_message_id: 'wrong-old-id', // Stale ID
            },
          },
          jsonapi: { version: '1.1' },
        });

        await service.postWelcomeToChannel(mockChannel);

        // Should update DB with correct message ID
        expect(mockApiClient.updateWelcomeMessageId).toHaveBeenCalledWith(
          'guild-123',
          'found-welcome-123'
        );
        // Should not post new message
        expect(mockChannel.send).not.toHaveBeenCalled();
      });
    });
  });

  describe('Pin Notification Cleanup (task-875)', () => {
    let mockMessage: any;
    let mockBotUser: any;

    beforeEach(() => {
      mockMessage = {
        id: 'message-456',
        pinned: false,
        pin: jest.fn<() => Promise<any>>().mockResolvedValue(undefined),
      };
      mockChannel.send.mockResolvedValue(mockMessage);

      mockBotUser = {
        id: 'bot-user-123',
        username: 'OpenNotes',
        bot: true,
      };

      mockChannel.client = {
        user: mockBotUser,
      };

      mockApiClient.getCommunityServerByPlatformId.mockReset();
      mockApiClient.updateWelcomeMessageId.mockReset();
      mockApiClient.updateWelcomeMessageId.mockResolvedValue({
        id: 'community-server-123',
        platform_id: 'guild-123',
        welcome_message_id: 'message-456',
      });
    });

    describe('AC#1: Check if message is already pinned', () => {
      it('should skip pinning if message is already pinned', async () => {
        const alreadyPinnedMessage = {
          id: 'message-456',
          pinned: true,
          pin: jest.fn<() => Promise<any>>().mockResolvedValue(undefined),
        };
        mockChannel.send.mockResolvedValue(alreadyPinnedMessage);

        await service.postWelcomeToChannel(mockChannel);

        expect(alreadyPinnedMessage.pin).not.toHaveBeenCalled();
        expect(mockLogger.debug).toHaveBeenCalledWith(
          'Message already pinned, skipping',
          expect.objectContaining({
            guildId: 'guild-123',
            messageId: 'message-456',
          })
        );
      });

      it('should pin message if not already pinned', async () => {
        const unpinnedMessage = {
          id: 'message-456',
          pinned: false,
          pin: jest.fn<() => Promise<any>>().mockResolvedValue(undefined),
        };
        mockChannel.send.mockResolvedValue(unpinnedMessage);

        await service.postWelcomeToChannel(mockChannel);

        expect(unpinnedMessage.pin).toHaveBeenCalled();
      });
    });

    describe('AC#3: Delete pin notification after pinning', () => {
      it('should delete pin notification system message after pinning', async () => {
        const pinnedMessage = {
          id: 'message-456',
          pinned: false,
          pin: jest.fn<() => Promise<any>>().mockResolvedValue(undefined),
          channel: mockChannel,
        };
        mockChannel.send.mockResolvedValue(pinnedMessage);

        const pinNotificationMessage = {
          id: 'notification-789',
          type: MessageType.ChannelPinnedMessage,
          delete: jest.fn<() => Promise<any>>().mockResolvedValue(undefined),
        };

        const regularMessage = {
          id: 'regular-123',
          type: MessageType.Default,
          delete: jest.fn<() => Promise<any>>().mockResolvedValue(undefined),
        };

        const fetchedMessages = createMockCollection([
          ['notification-789', pinNotificationMessage],
          ['regular-123', regularMessage],
        ]);
        mockChannel.messages.fetch.mockResolvedValue(fetchedMessages);

        await service.postWelcomeToChannel(mockChannel);

        expect(mockChannel.messages.fetch).toHaveBeenCalledWith(
          expect.objectContaining({
            limit: 5,
            after: 'message-456',
          })
        );
        expect(pinNotificationMessage.delete).toHaveBeenCalled();
        expect(regularMessage.delete).not.toHaveBeenCalled();
      });

      it('should handle pin notification deletion failure gracefully', async () => {
        const pinnedMessage = {
          id: 'message-456',
          pinned: false,
          pin: jest.fn<() => Promise<any>>().mockResolvedValue(undefined),
          channel: mockChannel,
        };
        mockChannel.send.mockResolvedValue(pinnedMessage);

        const pinNotificationMessage = {
          id: 'notification-789',
          type: MessageType.ChannelPinnedMessage,
          delete: jest.fn<() => Promise<any>>().mockRejectedValue(new Error('Missing permissions')),
        };

        const fetchedMessages = createMockCollection([
          ['notification-789', pinNotificationMessage],
        ]);
        mockChannel.messages.fetch.mockResolvedValue(fetchedMessages);

        await expect(service.postWelcomeToChannel(mockChannel)).resolves.not.toThrow();

        expect(mockLogger.debug).toHaveBeenCalledWith(
          'Could not delete pin notification',
          expect.objectContaining({
            messageId: 'message-456',
          })
        );
      });

      it('should handle message fetch failure gracefully', async () => {
        const pinnedMessage = {
          id: 'message-456',
          pinned: false,
          pin: jest.fn<() => Promise<any>>().mockResolvedValue(undefined),
          channel: mockChannel,
        };
        mockChannel.send.mockResolvedValue(pinnedMessage);

        mockChannel.messages.fetch.mockRejectedValue(new Error('API error'));

        await expect(service.postWelcomeToChannel(mockChannel)).resolves.not.toThrow();
      });
    });
  });
});
