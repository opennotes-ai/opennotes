import { describe, it, expect, beforeEach, afterEach, jest } from '@jest/globals';
import { MessageFlags, ContainerBuilder } from 'discord.js';
import { V2_COLORS } from '../../src/utils/v2-components.js';

const mockLogger = {
  info: jest.fn<(...args: unknown[]) => void>(),
  debug: jest.fn<(...args: unknown[]) => void>(),
  error: jest.fn<(...args: unknown[]) => void>(),
  warn: jest.fn<(...args: unknown[]) => void>(),
};

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
}));

const { GuildOnboardingService } = await import('../../src/services/GuildOnboardingService.js');

describe('GuildOnboardingService', () => {
  let service: InstanceType<typeof GuildOnboardingService>;
  let mockChannel: any;
  let mockGuild: any;

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
});
