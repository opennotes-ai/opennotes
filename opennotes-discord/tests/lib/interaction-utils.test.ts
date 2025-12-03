import { jest } from '@jest/globals';
import { ChatInputCommandInteraction, MessageFlags } from 'discord.js';
import { ConfigKey } from '../../src/lib/config-schema.js';

const mockLogger = {
  warn: jest.fn<(...args: unknown[]) => void>(),
  error: jest.fn<(...args: unknown[]) => void>(),
  info: jest.fn<(...args: unknown[]) => void>(),
  debug: jest.fn<(...args: unknown[]) => void>(),
};

const mockConfigService = {
  get: jest.fn<(guildId: string, key: ConfigKey) => Promise<boolean>>(),
};

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
}));

jest.unstable_mockModule('../../src/services/index.js', () => ({
  serviceProvider: {
    getGuildConfigService: () => mockConfigService,
  },
}));

const { handleEphemeralError } = await import('../../src/lib/interaction-utils.js');

describe('interaction-utils', () => {
  describe('handleEphemeralError', () => {
    let mockInteraction: jest.Mocked<ChatInputCommandInteraction>;
    const errorMessage = { content: 'Error occurred' };
    const guildId = 'guild-123';
    const errorId = 'error-456';

    beforeEach(() => {
      mockInteraction = {
        editReply: jest.fn<() => Promise<unknown>>().mockResolvedValue(undefined),
        followUp: jest.fn<() => Promise<unknown>>().mockResolvedValue(undefined),
        deleteReply: jest.fn<() => Promise<unknown>>().mockResolvedValue(undefined),
      } as unknown as jest.Mocked<ChatInputCommandInteraction>;

      jest.clearAllMocks();
    });

    it('should edit reply when ephemeral config is true', async () => {
      mockConfigService.get.mockResolvedValue(true);

      await handleEphemeralError(
        mockInteraction,
        errorMessage,
        guildId,
        errorId,
        ConfigKey.WRITE_NOTE_EPHEMERAL
      );

      expect(mockConfigService.get).toHaveBeenCalledWith(guildId, ConfigKey.WRITE_NOTE_EPHEMERAL);
      expect(mockInteraction.editReply).toHaveBeenCalledWith(errorMessage);
      expect(mockInteraction.followUp).not.toHaveBeenCalled();
      expect(mockInteraction.deleteReply).not.toHaveBeenCalled();
    });

    it('should follow up and delete when ephemeral config is false', async () => {
      mockConfigService.get.mockResolvedValue(false);

      await handleEphemeralError(
        mockInteraction,
        errorMessage,
        guildId,
        errorId,
        ConfigKey.WRITE_NOTE_EPHEMERAL
      );

      expect(mockConfigService.get).toHaveBeenCalledWith(guildId, ConfigKey.WRITE_NOTE_EPHEMERAL);
      expect(mockInteraction.followUp).toHaveBeenCalledWith({
        ...errorMessage,
        flags: MessageFlags.Ephemeral,
      });
      expect(mockInteraction.deleteReply).toHaveBeenCalled();
      expect(mockInteraction.editReply).not.toHaveBeenCalled();
    });

    it('should default to false when guild ID is null', async () => {
      await handleEphemeralError(
        mockInteraction,
        errorMessage,
        null,
        errorId,
        ConfigKey.WRITE_NOTE_EPHEMERAL
      );

      expect(mockConfigService.get).not.toHaveBeenCalled();
      expect(mockInteraction.followUp).toHaveBeenCalledWith({
        ...errorMessage,
        flags: MessageFlags.Ephemeral,
      });
      expect(mockInteraction.deleteReply).toHaveBeenCalled();
      expect(mockInteraction.editReply).not.toHaveBeenCalled();
    });

    it('should default to false when config fetch fails', async () => {
      mockConfigService.get.mockRejectedValue(new Error('Config fetch failed'));

      await handleEphemeralError(
        mockInteraction,
        errorMessage,
        guildId,
        errorId,
        ConfigKey.WRITE_NOTE_EPHEMERAL
      );

      expect(mockConfigService.get).toHaveBeenCalledWith(guildId, ConfigKey.WRITE_NOTE_EPHEMERAL);
      expect(mockInteraction.followUp).toHaveBeenCalledWith({
        ...errorMessage,
        flags: MessageFlags.Ephemeral,
      });
      expect(mockInteraction.deleteReply).toHaveBeenCalled();
      expect(mockInteraction.editReply).not.toHaveBeenCalled();
    });

    it('should handle editReply errors gracefully', async () => {
      mockConfigService.get.mockResolvedValue(true);
      mockInteraction.editReply.mockRejectedValue(new Error('Edit failed'));

      await expect(
        handleEphemeralError(
          mockInteraction,
          errorMessage,
          guildId,
          errorId,
          ConfigKey.WRITE_NOTE_EPHEMERAL
        )
      ).resolves.not.toThrow();

      expect(mockInteraction.editReply).toHaveBeenCalled();
    });

    it('should handle followUp errors gracefully', async () => {
      mockConfigService.get.mockResolvedValue(false);
      mockInteraction.followUp.mockRejectedValue(new Error('Follow-up failed'));

      await expect(
        handleEphemeralError(
          mockInteraction,
          errorMessage,
          guildId,
          errorId,
          ConfigKey.WRITE_NOTE_EPHEMERAL
        )
      ).resolves.not.toThrow();

      expect(mockInteraction.followUp).toHaveBeenCalled();
    });

    it('should handle deleteReply errors gracefully', async () => {
      mockConfigService.get.mockResolvedValue(false);
      mockInteraction.deleteReply.mockRejectedValue(new Error('Delete failed'));

      await expect(
        handleEphemeralError(
          mockInteraction,
          errorMessage,
          guildId,
          errorId,
          ConfigKey.WRITE_NOTE_EPHEMERAL
        )
      ).resolves.not.toThrow();

      expect(mockInteraction.deleteReply).toHaveBeenCalled();
    });

    it('should work with different config keys', async () => {
      mockConfigService.get.mockResolvedValue(true);

      await handleEphemeralError(
        mockInteraction,
        errorMessage,
        guildId,
        errorId,
        ConfigKey.RATE_NOTE_EPHEMERAL
      );

      expect(mockConfigService.get).toHaveBeenCalledWith(guildId, ConfigKey.RATE_NOTE_EPHEMERAL);
      expect(mockInteraction.editReply).toHaveBeenCalledWith(errorMessage);
    });

    it('should work with REQUEST_NOTE_EPHEMERAL config key', async () => {
      mockConfigService.get.mockResolvedValue(false);

      await handleEphemeralError(
        mockInteraction,
        errorMessage,
        guildId,
        errorId,
        ConfigKey.REQUEST_NOTE_EPHEMERAL
      );

      expect(mockConfigService.get).toHaveBeenCalledWith(guildId, ConfigKey.REQUEST_NOTE_EPHEMERAL);
      expect(mockInteraction.followUp).toHaveBeenCalled();
    });
  });
});
