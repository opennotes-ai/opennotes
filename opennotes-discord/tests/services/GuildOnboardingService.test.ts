import { describe, it, expect, beforeEach, afterEach, jest } from '@jest/globals';
import { MessageFlags } from 'discord.js';
import { GuildOnboardingService } from '../../src/services/GuildOnboardingService.js';
import type { ApiClient, LLMConfigResponse } from '../../src/lib/api-client.js';
import { V2_COLORS } from '../../src/utils/v2-components.js';

describe('GuildOnboardingService', () => {
  let service: GuildOnboardingService;
  let mockApiClient: any;
  let mockGuild: any;
  let mockOwner: any;
  let mockUser: any;

  beforeEach(() => {
    mockApiClient = {
      listLLMConfigs: jest.fn<(guildId: string) => Promise<LLMConfigResponse[]>>(),
    };

    mockUser = {
      id: 'owner-user-id',
      send: jest.fn<(...args: any[]) => Promise<any>>(),
    };

    mockOwner = {
      user: mockUser,
    };

    mockGuild = {
      id: 'test-guild-id',
      name: 'Test Guild',
      ownerId: 'owner-user-id',
      fetchOwner: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue(mockOwner),
    };

    service = new GuildOnboardingService(mockApiClient as ApiClient);
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe('checkAndNotifyMissingOpenAIKey', () => {
    it('should not send DM if OpenAI key is configured', async () => {
      const mockConfig: Partial<LLMConfigResponse> = {
        provider: 'openai',
        enabled: true,
      };

      mockApiClient.listLLMConfigs.mockResolvedValue([mockConfig]);

      await service.checkAndNotifyMissingOpenAIKey(mockGuild);

      expect(mockApiClient.listLLMConfigs).toHaveBeenCalledWith('test-guild-id');
      expect(mockGuild.fetchOwner).not.toHaveBeenCalled();
      expect(mockUser.send).not.toHaveBeenCalled();
    });

    it('should send DM to owner if OpenAI key is missing', async () => {
      mockApiClient.listLLMConfigs.mockResolvedValue([]);

      await service.checkAndNotifyMissingOpenAIKey(mockGuild);

      expect(mockApiClient.listLLMConfigs).toHaveBeenCalledWith('test-guild-id');
      expect(mockGuild.fetchOwner).toHaveBeenCalled();
      expect(mockUser.send).toHaveBeenCalled();
    });

    it('should send DM if OpenAI config exists but is disabled', async () => {
      const mockConfig: Partial<LLMConfigResponse> = {
        provider: 'openai',
        enabled: false,
      };

      mockApiClient.listLLMConfigs.mockResolvedValue([mockConfig]);

      await service.checkAndNotifyMissingOpenAIKey(mockGuild);

      expect(mockGuild.fetchOwner).toHaveBeenCalled();
      expect(mockUser.send).toHaveBeenCalled();
    });

    it('should handle DMs disabled error gracefully', async () => {
      mockApiClient.listLLMConfigs.mockResolvedValue([]);

      const dmError: any = new Error('Cannot send messages to this user');
      dmError.code = 50007;
      mockUser.send.mockRejectedValue(dmError);

      await expect(
        service.checkAndNotifyMissingOpenAIKey(mockGuild)
      ).resolves.not.toThrow();

      expect(mockUser.send).toHaveBeenCalled();
    });

    it('should handle owner fetch failure gracefully', async () => {
      mockApiClient.listLLMConfigs.mockResolvedValue([]);
      mockGuild.fetchOwner.mockRejectedValue(new Error('Failed to fetch owner'));

      await expect(
        service.checkAndNotifyMissingOpenAIKey(mockGuild)
      ).resolves.not.toThrow();

      expect(mockGuild.fetchOwner).toHaveBeenCalled();
      expect(mockUser.send).not.toHaveBeenCalled();
    });

    it('should handle API failure gracefully by assuming no key', async () => {
      mockApiClient.listLLMConfigs.mockRejectedValue(new Error('API error'));

      await expect(
        service.checkAndNotifyMissingOpenAIKey(mockGuild)
      ).resolves.not.toThrow();

      expect(mockGuild.fetchOwner).toHaveBeenCalled();
    });

    describe('Components v2 notification format', () => {
      beforeEach(() => {
        mockApiClient.listLLMConfigs.mockResolvedValue([]);
      });

      it('should send message with IsComponentsV2 flag', async () => {
        await service.checkAndNotifyMissingOpenAIKey(mockGuild);

        expect(mockUser.send).toHaveBeenCalledWith(
          expect.objectContaining({
            flags: expect.any(Number),
          })
        );

        const sendCall = mockUser.send.mock.calls[0][0];
        expect(sendCall.flags & MessageFlags.IsComponentsV2).toBeTruthy();
      });

      it('should use ContainerBuilder with brand accent color', async () => {
        await service.checkAndNotifyMissingOpenAIKey(mockGuild);

        const sendCall = mockUser.send.mock.calls[0][0];
        expect(sendCall.components).toBeDefined();
        expect(sendCall.components).toHaveLength(1);

        const container = sendCall.components[0];
        expect(container.data.accent_color).toBe(V2_COLORS.PRIMARY);
      });

      it('should include welcome title with guild name', async () => {
        await service.checkAndNotifyMissingOpenAIKey(mockGuild);

        const sendCall = mockUser.send.mock.calls[0][0];
        const container = sendCall.components[0];

        const welcomeTextComponent = container.components.find(
          (c: any) => c.data?.content?.includes('Welcome to Open Notes')
        );
        expect(welcomeTextComponent).toBeDefined();
      });

      it('should include guild name in message', async () => {
        await service.checkAndNotifyMissingOpenAIKey(mockGuild);

        const sendCall = mockUser.send.mock.calls[0][0];
        const container = sendCall.components[0];

        const guildNameComponent = container.components.find(
          (c: any) => c.data?.content?.includes('Test Guild')
        );
        expect(guildNameComponent).toBeDefined();
      });

      it('should have separator components between sections', async () => {
        await service.checkAndNotifyMissingOpenAIKey(mockGuild);

        const sendCall = mockUser.send.mock.calls[0][0];
        const container = sendCall.components[0];

        const separators = container.components.filter((c: any) =>
          c.constructor.name === 'SeparatorBuilder'
        );
        expect(separators.length).toBeGreaterThanOrEqual(2);
      });

      it('should include feature highlights section', async () => {
        await service.checkAndNotifyMissingOpenAIKey(mockGuild);

        const sendCall = mockUser.send.mock.calls[0][0];
        const container = sendCall.components[0];

        const allTextContent = container.components
          .flatMap((c: any) => {
            if (c.data?.content) return [c.data.content];
            if (c.components) {
              return c.components.map((inner: any) => inner.data?.content || '');
            }
            return [];
          })
          .join(' ');

        expect(allTextContent).toContain('fact-checking');
        expect(allTextContent).toContain('AI-assisted');
        expect(allTextContent).toContain('Embedding');
      });

      it('should include setup instructions section', async () => {
        await service.checkAndNotifyMissingOpenAIKey(mockGuild);

        const sendCall = mockUser.send.mock.calls[0][0];
        const container = sendCall.components[0];

        const allTextContent = container.components
          .flatMap((c: any) => {
            if (c.data?.content) return [c.data.content];
            if (c.components) {
              return c.components.map((inner: any) => inner.data?.content || '');
            }
            return [];
          })
          .join(' ');

        expect(allTextContent).toContain('OpenAI Platform');
        expect(allTextContent).toContain('/config-opennotes');
      });

      it('should include features that work without API key', async () => {
        await service.checkAndNotifyMissingOpenAIKey(mockGuild);

        const sendCall = mockUser.send.mock.calls[0][0];
        const container = sendCall.components[0];

        const allTextContent = container.components
          .flatMap((c: any) => {
            if (c.data?.content) return [c.data.content];
            if (c.components) {
              return c.components.map((inner: any) => inner.data?.content || '');
            }
            return [];
          })
          .join(' ');

        expect(allTextContent).toContain('Request community notes');
        expect(allTextContent).toContain('Write notes manually');
      });

      it('should not include embeds (using v2 components instead)', async () => {
        await service.checkAndNotifyMissingOpenAIKey(mockGuild);

        const sendCall = mockUser.send.mock.calls[0][0];
        expect(sendCall.embeds).toBeUndefined();
      });
    });
  });
});
