import { jest, describe, it, expect, beforeEach } from '@jest/globals';
import { TextChannel } from 'discord.js';
import { loggerFactory } from '../factories/index.js';

const mockLogger = loggerFactory.build();

const mockCacheGet = jest.fn<(...args: any[]) => Promise<any>>();
const mockCacheSet = jest.fn<(...args: any[]) => Promise<boolean>>().mockResolvedValue(true);
const mockCacheDelete = jest.fn<(...args: any[]) => Promise<boolean>>().mockResolvedValue(true);

const mockExecuteBulkScan = jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({
  scanId: 'scan-123',
  messagesScanned: 100,
  channelsScanned: 5,
  batchesPublished: 1,
  status: 'completed',
  flaggedMessages: [],
});

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
}));

jest.unstable_mockModule('../../src/cache.js', () => ({
  cache: {
    get: mockCacheGet,
    set: mockCacheSet,
    delete: mockCacheDelete,
  },
}));

jest.unstable_mockModule('../../src/lib/bulk-scan-executor.js', () => ({
  executeBulkScan: mockExecuteBulkScan,
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

jest.unstable_mockModule('../../src/lib/vibecheck-prompt.js', () => ({
  VIBECHECK_PROMPT_CUSTOM_IDS: {
    DAYS_SELECT: 'vibecheck_prompt_days',
    START: 'vibecheck_prompt_start',
    NO_THANKS: 'vibecheck_prompt_no_thanks',
  },
  createDaysSelectMenu: jest.fn().mockReturnValue({
    toJSON: () => ({ type: 3, custom_id: 'vibecheck_prompt_days' }),
  }),
  createPromptButtons: jest.fn().mockReturnValue({
    toJSON: () => ({ components: [] }),
  }),
}));

const {
  isVibecheckPromptInteraction,
  handleVibecheckPromptInteraction,
  getVibecheckPromptState,
  setVibecheckPromptState,
  deleteVibecheckPromptState,
} = await import('../../src/handlers/vibecheck-prompt-handler.js');

describe('vibecheck-prompt-handler', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('isVibecheckPromptInteraction', () => {
    it('should return true for days select custom ID', () => {
      expect(isVibecheckPromptInteraction('vibecheck_prompt_days')).toBe(true);
    });

    it('should return true for start button custom ID', () => {
      expect(isVibecheckPromptInteraction('vibecheck_prompt_start')).toBe(true);
    });

    it('should return true for no thanks button custom ID', () => {
      expect(isVibecheckPromptInteraction('vibecheck_prompt_no_thanks')).toBe(true);
    });

    it('should return false for unrelated custom ID', () => {
      expect(isVibecheckPromptInteraction('other_custom_id')).toBe(false);
      expect(isVibecheckPromptInteraction('request_reply:list')).toBe(false);
    });
  });

  describe('state management functions', () => {
    it('should get state from cache', async () => {
      const state = { guildId: 'guild-123', adminId: 'admin-123', botChannelId: 'channel-123', selectedDays: 7 };
      mockCacheGet.mockResolvedValue(state);

      const result = await getVibecheckPromptState('message-123');

      expect(mockCacheGet).toHaveBeenCalledWith('vibecheck_prompt_state:message-123');
      expect(result).toEqual(state);
    });

    it('should return null when state not found', async () => {
      mockCacheGet.mockResolvedValue(null);

      const result = await getVibecheckPromptState('message-123');

      expect(result).toBeNull();
    });

    it('should set state in cache with TTL', async () => {
      const state = { guildId: 'guild-123', adminId: 'admin-123', botChannelId: 'channel-123', selectedDays: null };

      await setVibecheckPromptState('message-123', state);

      expect(mockCacheSet).toHaveBeenCalledWith(
        'vibecheck_prompt_state:message-123',
        state,
        300
      );
    });

    it('should delete state from cache', async () => {
      await deleteVibecheckPromptState('message-123');

      expect(mockCacheDelete).toHaveBeenCalledWith('vibecheck_prompt_state:message-123');
    });
  });

  describe('handleVibecheckPromptInteraction', () => {
    const createMockInteraction = (overrides: any = {}) => ({
      message: { id: 'message-123', edit: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}) },
      user: { id: 'admin-123' },
      customId: 'vibecheck_prompt_days',
      isStringSelectMenu: () => false,
      isButton: () => false,
      update: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}),
      reply: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}),
      followUp: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({}),
      deferred: false,
      replied: false,
      ...overrides,
    });

    it('should handle expired prompt state gracefully', async () => {
      mockCacheGet.mockResolvedValue(null);

      const interaction = createMockInteraction();
      await handleVibecheckPromptInteraction(interaction as any);

      expect(interaction.update).toHaveBeenCalledWith({
        content: expect.stringContaining('expired'),
        components: [],
      });
    });

    it('should reject interaction from non-admin user', async () => {
      mockCacheGet.mockResolvedValue({
        guildId: 'guild-123',
        adminId: 'admin-123',
        botChannelId: 'channel-123',
        selectedDays: null,
      });

      const interaction = createMockInteraction({
        user: { id: 'other-user-456' },
      });
      await handleVibecheckPromptInteraction(interaction as any);

      expect(interaction.reply).toHaveBeenCalledWith({
        content: expect.stringContaining('Only the server admin'),
        ephemeral: true,
      });
    });

    describe('days select interaction', () => {
      it('should update state when days are selected', async () => {
        mockCacheGet.mockResolvedValue({
          guildId: 'guild-123',
          adminId: 'admin-123',
          botChannelId: 'channel-123',
          selectedDays: null,
        });

        const interaction = createMockInteraction({
          customId: 'vibecheck_prompt_days',
          isStringSelectMenu: () => true,
          values: ['7'],
        });
        await handleVibecheckPromptInteraction(interaction as any);

        expect(mockCacheSet).toHaveBeenCalledWith(
          'vibecheck_prompt_state:message-123',
          expect.objectContaining({ selectedDays: 7 }),
          300
        );
        expect(interaction.update).toHaveBeenCalledWith(
          expect.objectContaining({
            content: expect.stringContaining('7 days'),
          })
        );
      });
    });

    describe('no thanks button', () => {
      it('should dismiss prompt and delete state', async () => {
        mockCacheGet.mockResolvedValue({
          guildId: 'guild-123',
          adminId: 'admin-123',
          botChannelId: 'channel-123',
          selectedDays: null,
        });

        const interaction = createMockInteraction({
          customId: 'vibecheck_prompt_no_thanks',
          isButton: () => true,
        });
        await handleVibecheckPromptInteraction(interaction as any);

        expect(mockCacheDelete).toHaveBeenCalledWith('vibecheck_prompt_state:message-123');
        expect(interaction.update).toHaveBeenCalledWith({
          content: expect.stringContaining('dismissed'),
          components: [],
        });
      });
    });

    describe('start button', () => {
      it('should not start scan if no days selected', async () => {
        mockCacheGet.mockResolvedValue({
          guildId: 'guild-123',
          adminId: 'admin-123',
          botChannelId: 'channel-123',
          selectedDays: null,
        });

        const interaction = createMockInteraction({
          customId: 'vibecheck_prompt_start',
          isButton: () => true,
        });
        await handleVibecheckPromptInteraction(interaction as any);

        expect(mockExecuteBulkScan).not.toHaveBeenCalled();
        expect(interaction.reply).toHaveBeenCalledWith({
          content: expect.stringContaining('select the number of days'),
          ephemeral: true,
        });
      });

      it('should start scan when days are selected', async () => {
        mockCacheGet.mockResolvedValue({
          guildId: 'guild-123',
          adminId: 'admin-123',
          botChannelId: 'channel-123',
          selectedDays: 7,
        });

        const mockGuild = {
          id: 'guild-123',
          name: 'Test Guild',
        };

        const mockChannel = Object.assign(Object.create(TextChannel.prototype), {
          guild: mockGuild,
          id: 'channel-123',
          name: 'open-notes',
        });

        const interaction = createMockInteraction({
          customId: 'vibecheck_prompt_start',
          isButton: () => true,
          channel: mockChannel,
        });
        await handleVibecheckPromptInteraction(interaction as any);

        expect(mockCacheDelete).toHaveBeenCalledWith('vibecheck_prompt_state:message-123');
        expect(mockExecuteBulkScan).toHaveBeenCalledWith(
          expect.objectContaining({
            guild: mockGuild,
            days: 7,
            initiatorId: 'admin-123',
          })
        );
      });

      it('should handle scan with no accessible channels', async () => {
        mockCacheGet.mockResolvedValue({
          guildId: 'guild-123',
          adminId: 'admin-123',
          botChannelId: 'channel-123',
          selectedDays: 7,
        });

        mockExecuteBulkScan.mockResolvedValue({
          scanId: 'scan-123',
          messagesScanned: 0,
          channelsScanned: 0,
          batchesPublished: 0,
          status: 'completed',
          flaggedMessages: [],
        });

        const mockGuild = { id: 'guild-123', name: 'Test Guild' };
        const mockChannel = Object.assign(Object.create(TextChannel.prototype), {
          guild: mockGuild,
          id: 'channel-123',
          name: 'open-notes',
        });
        const interaction = createMockInteraction({
          customId: 'vibecheck_prompt_start',
          isButton: () => true,
          channel: mockChannel,
        });

        await handleVibecheckPromptInteraction(interaction as any);

        expect(interaction.message.edit).toHaveBeenCalledWith({
          content: expect.stringContaining('No accessible text channels'),
        });
      });

      it('should handle scan execution failure', async () => {
        mockCacheGet.mockResolvedValue({
          guildId: 'guild-123',
          adminId: 'admin-123',
          botChannelId: 'channel-123',
          selectedDays: 7,
        });

        mockExecuteBulkScan.mockRejectedValue(new Error('NATS connection failed'));

        const mockGuild = { id: 'guild-123', name: 'Test Guild' };
        const mockChannel = Object.assign(Object.create(TextChannel.prototype), {
          guild: mockGuild,
          id: 'channel-123',
          name: 'open-notes',
        });
        const interaction = createMockInteraction({
          customId: 'vibecheck_prompt_start',
          isButton: () => true,
          channel: mockChannel,
        });

        await handleVibecheckPromptInteraction(interaction as any);

        expect(mockLogger.error).toHaveBeenCalledWith(
          'Vibe check scan from prompt failed',
          expect.objectContaining({
            error: 'NATS connection failed',
          })
        );
        expect(interaction.message.edit).toHaveBeenCalledWith({
          content: expect.stringContaining('encountered an error'),
        });
      });

      it('should handle scan with failed status', async () => {
        mockCacheGet.mockResolvedValue({
          guildId: 'guild-123',
          adminId: 'admin-123',
          botChannelId: 'channel-123',
          selectedDays: 7,
        });

        mockExecuteBulkScan.mockResolvedValue({
          scanId: 'scan-456',
          messagesScanned: 100,
          channelsScanned: 5,
          batchesPublished: 1,
          status: 'failed',
          flaggedMessages: [],
        });

        const mockGuild = { id: 'guild-123', name: 'Test Guild' };
        const mockChannel = Object.assign(Object.create(TextChannel.prototype), {
          guild: mockGuild,
          id: 'channel-123',
          name: 'open-notes',
        });
        const interaction = createMockInteraction({
          customId: 'vibecheck_prompt_start',
          isButton: () => true,
          channel: mockChannel,
        });

        await handleVibecheckPromptInteraction(interaction as any);

        expect(interaction.message.edit).toHaveBeenLastCalledWith({
          content: expect.stringContaining('Scan analysis failed'),
        });
      });

      it('should handle scan with timeout status', async () => {
        mockCacheGet.mockResolvedValue({
          guildId: 'guild-123',
          adminId: 'admin-123',
          botChannelId: 'channel-123',
          selectedDays: 7,
        });

        mockExecuteBulkScan.mockResolvedValue({
          scanId: 'scan-789',
          messagesScanned: 100,
          channelsScanned: 5,
          batchesPublished: 1,
          status: 'timeout',
          flaggedMessages: [],
        });

        const mockGuild = { id: 'guild-123', name: 'Test Guild' };
        const mockChannel = Object.assign(Object.create(TextChannel.prototype), {
          guild: mockGuild,
          id: 'channel-123',
          name: 'open-notes',
        });
        const interaction = createMockInteraction({
          customId: 'vibecheck_prompt_start',
          isButton: () => true,
          channel: mockChannel,
        });

        await handleVibecheckPromptInteraction(interaction as any);

        expect(interaction.message.edit).toHaveBeenLastCalledWith({
          content: expect.stringContaining('Scan analysis failed'),
        });
      });

      it('should display flagged messages count when issues found', async () => {
        mockCacheGet.mockResolvedValue({
          guildId: 'guild-123',
          adminId: 'admin-123',
          botChannelId: 'channel-123',
          selectedDays: 7,
        });

        mockExecuteBulkScan.mockResolvedValue({
          scanId: 'scan-999',
          messagesScanned: 500,
          channelsScanned: 10,
          batchesPublished: 2,
          status: 'completed',
          flaggedMessages: [
            { messageId: 'msg-1', content: 'test' },
            { messageId: 'msg-2', content: 'test2' },
            { messageId: 'msg-3', content: 'test3' },
          ],
        });

        const mockGuild = { id: 'guild-123', name: 'Test Guild' };
        const mockChannel = Object.assign(Object.create(TextChannel.prototype), {
          guild: mockGuild,
          id: 'channel-123',
          name: 'open-notes',
        });
        const interaction = createMockInteraction({
          customId: 'vibecheck_prompt_start',
          isButton: () => true,
          channel: mockChannel,
        });

        await handleVibecheckPromptInteraction(interaction as any);

        expect(interaction.message.edit).toHaveBeenLastCalledWith({
          content: expect.stringContaining('Flagged:** 3'),
        });
      });

      it('should reject invalid days selection', async () => {
        mockCacheGet.mockResolvedValue({
          guildId: 'guild-123',
          adminId: 'admin-123',
          botChannelId: 'channel-123',
          selectedDays: null,
        });

        const interaction = createMockInteraction({
          customId: 'vibecheck_prompt_days',
          isStringSelectMenu: () => true,
          values: ['invalid'],
        });

        await handleVibecheckPromptInteraction(interaction as any);

        expect(mockLogger.warn).toHaveBeenCalledWith(
          'Invalid days selection in vibecheck prompt',
          expect.objectContaining({
            raw_value: 'invalid',
          })
        );
        expect(interaction.reply).toHaveBeenCalledWith({
          content: expect.stringContaining('Invalid selection'),
          ephemeral: true,
        });
      });
    });
  });
});
