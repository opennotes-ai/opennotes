import { describe, it, expect, beforeEach, afterEach, jest } from '@jest/globals';
import { GuildOnboardingService } from '../../src/services/GuildOnboardingService.js';
import type { ApiClient, LLMConfigResponse } from '../../src/lib/api-client.js';

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
  });
});
