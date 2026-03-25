import { jest, describe, it, expect, beforeEach } from '@jest/globals';
import { TextChannel } from 'discord.js';
import { loggerFactory } from '../factories/index.js';

const mockLogger = loggerFactory.build();

const mockCacheGet = jest.fn<(...args: any[]) => Promise<any>>();
const mockCacheSet = jest.fn<(...args: any[]) => Promise<boolean>>().mockResolvedValue(true);
const mockCacheDelete = jest.fn<(...args: any[]) => Promise<boolean>>().mockResolvedValue(true);
const mockCacheExpire = jest.fn<(...args: any[]) => Promise<boolean>>().mockResolvedValue(true);

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
    expire: mockCacheExpire,
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
    DAYS_PREFIX: 'vibecheck_days:',
    START: 'vibecheck_prompt_start',
    NO_THANKS: 'vibecheck_prompt_no_thanks',
  },
  createDaysButtons: jest.fn().mockReturnValue({
    toJSON: () => ({ type: 1, components: [] }),
  }),
  createPromptButtons: jest.fn().mockReturnValue({
    toJSON: () => ({ type: 1, components: [] }),
  }),
}));

jest.unstable_mockModule('../../src/lib/navigation-components.js', () => ({
  buildContextualNav: jest.fn().mockReturnValue({
    toJSON: () => ({ type: 1, components: [] }),
  }),
}));

const {
  isVibecheckPromptInteraction,
  handleVibecheckPromptInteraction,
  getVibecheckPromptState,
  setVibecheckPromptState,
  deleteVibecheckPromptState,
} = await import('../../src/handlers/vibecheck-prompt-handler.js');

function extractTextFromContainer(containerJson: any): string {
  if (!containerJson || !containerJson.components) return '';
  return containerJson.components
    .filter((c: any) => c.type === 10)
    .map((c: any) => c.content || '')
    .join('\n');
}

function getContainerText(callArgs: any): string {
  const components = callArgs?.components;
  if (!components || components.length === 0) return '';
  const first = components[0];
  const json = typeof first?.toJSON === 'function' ? first.toJSON() : first;
  return extractTextFromContainer(json);
}

describe('vibecheck-prompt-handler', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('isVibecheckPromptInteraction', () => {
    it('should return true for days button custom IDs', () => {
      expect(isVibecheckPromptInteraction('vibecheck_days:1')).toBe(true);
      expect(isVibecheckPromptInteraction('vibecheck_days:7')).toBe(true);
      expect(isVibecheckPromptInteraction('vibecheck_days:30')).toBe(true);
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
        900
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
      customId: 'vibecheck_days:7',
      isStringSelectMenu: () => false,
      isButton: () => true,
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

      expect(interaction.update).toHaveBeenCalled();
      const callArgs = interaction.update.mock.calls[0][0];
      const text = getContainerText(callArgs);
      expect(text).toContain('expired');
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

      expect(interaction.reply).toHaveBeenCalled();
      const callArgs = interaction.reply.mock.calls[0][0];
      const text = getContainerText(callArgs);
      expect(text).toContain('Only the server admin');
      expect(callArgs.flags).toBeTruthy();
    });

    describe('days button interaction', () => {
      it('should update state when days are selected', async () => {
        mockCacheGet.mockResolvedValue({
          guildId: 'guild-123',
          adminId: 'admin-123',
          botChannelId: 'channel-123',
          selectedDays: null,
        });

        const interaction = createMockInteraction({
          customId: 'vibecheck_days:7',
          isButton: () => true,
        });
        await handleVibecheckPromptInteraction(interaction as any);

        expect(mockCacheExpire).toHaveBeenCalledWith(
          'vibecheck_prompt_state:message-123',
          900
        );
        expect(mockCacheSet).toHaveBeenCalledWith(
          'vibecheck_prompt_state:message-123',
          expect.objectContaining({ selectedDays: 7 }),
          900
        );
        expect(interaction.update).toHaveBeenCalled();
        const callArgs = interaction.update.mock.calls[0][0];
        const text = getContainerText(callArgs);
        expect(text).toContain('7 days');
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
        expect(interaction.update).toHaveBeenCalled();
        const callArgs = interaction.update.mock.calls[0][0];
        const text = getContainerText(callArgs);
        expect(text).toContain('dismissed');
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
        expect(interaction.reply).toHaveBeenCalled();
        const callArgs = interaction.reply.mock.calls[0][0];
        const text = getContainerText(callArgs);
        expect(text).toContain('select the number of days');
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

        expect(interaction.message.edit).toHaveBeenCalled();
        const lastCall = interaction.message.edit.mock.calls.at(-1)?.[0];
        const text = extractTextFromContainer(lastCall.components[0]);
        expect(text).toContain('No accessible text channels');
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
        expect(interaction.message.edit).toHaveBeenCalled();
        const lastCall = interaction.message.edit.mock.calls.at(-1)?.[0];
        const text = extractTextFromContainer(lastCall.components[0]);
        expect(text).toContain('encountered an error');
      });

      it('should handle zero-message scan with failed status', async () => {
        mockCacheGet.mockResolvedValue({
          guildId: 'guild-123',
          adminId: 'admin-123',
          botChannelId: 'channel-123',
          selectedDays: 7,
        });

        mockExecuteBulkScan.mockResolvedValue({
          scanId: 'scan-456',
          messagesScanned: 0,
          channelsScanned: 5,
          batchesPublished: 1,
          failedBatches: 0,
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

        const lastCall = interaction.message.edit.mock.calls.at(-1)?.[0];
        const text = extractTextFromContainer(lastCall.components[0]);
        expect(text).toContain('Scan analysis failed');
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

        const lastCall = interaction.message.edit.mock.calls.at(-1)?.[0];
        const text = extractTextFromContainer(lastCall.components[0]);
        expect(text).toContain('may still be running');
      });

      it('freezes the prompt message after a stall warning and records cache metadata', async () => {
        mockCacheGet.mockResolvedValue({
          guildId: 'guild-123',
          adminId: 'admin-123',
          botChannelId: 'channel-123',
          selectedDays: 7,
        });

        mockExecuteBulkScan.mockImplementationOnce(async ({ stallWarningCallback }) => {
          expect(stallWarningCallback).toBeDefined();
          await stallWarningCallback?.('scan-prompt-123');
          return {
            scanId: 'scan-prompt-123',
            messagesScanned: 100,
            channelsScanned: 5,
            batchesPublished: 1,
            status: 'completed',
            flaggedMessages: [],
          };
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

        const lastCall = interaction.message.edit.mock.calls.at(-1)?.[0];
        const text = extractTextFromContainer(lastCall.components[0]);
        expect(text).toContain('scan-prompt-123');
        expect(text).toContain('taking longer than we can keep updated');
        expect(text).toContain('scan_id:scan-prompt-123');
        expect(mockCacheSet).toHaveBeenCalledWith(
          'vibecheck:stalled:scan-prompt-123',
          expect.objectContaining({
            scanId: 'scan-prompt-123',
            initiatorId: 'admin-123',
            guildId: 'guild-123',
            days: 7,
            source: 'prompt',
          }),
          7 * 24 * 60 * 60
        );
      });

      it('falls back to the terminal prompt message when stalled scan persistence fails', async () => {
        mockCacheGet.mockResolvedValue({
          guildId: 'guild-123',
          adminId: 'admin-123',
          botChannelId: 'channel-123',
          selectedDays: 7,
        });
        mockCacheSet.mockRejectedValueOnce(new Error('redis unavailable'));

        mockExecuteBulkScan.mockImplementationOnce(async ({ stallWarningCallback }) => {
          await stallWarningCallback?.('scan-prompt-123').catch(() => undefined);
          return {
            scanId: 'scan-prompt-123',
            messagesScanned: 100,
            channelsScanned: 5,
            batchesPublished: 1,
            status: 'completed',
            flaggedMessages: [],
          };
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

        const editContents = interaction.message.edit.mock.calls.map(([arg]: any[]) => {
          return extractTextFromContainer(arg.components?.[0] ?? {});
        });
        expect(editContents.some((content: string) => content.includes('**Scan Complete**'))).toBe(true);
        expect(editContents.at(-1)).not.toContain('taking longer than we can keep updated');
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

        const lastCall = interaction.message.edit.mock.calls.at(-1)?.[0];
        const text = extractTextFromContainer(lastCall.components[0]);
        expect(text).toContain('Flagged:** 3');
      });

      it('should reject invalid days selection', async () => {
        mockCacheGet.mockResolvedValue({
          guildId: 'guild-123',
          adminId: 'admin-123',
          botChannelId: 'channel-123',
          selectedDays: null,
        });

        const interaction = createMockInteraction({
          customId: 'vibecheck_days:invalid',
          isButton: () => true,
        });

        await handleVibecheckPromptInteraction(interaction as any);

        expect(mockLogger.warn).toHaveBeenCalledWith(
          'Invalid days selection in vibecheck prompt',
          expect.objectContaining({
            raw_value: 'invalid',
          })
        );
        expect(interaction.reply).toHaveBeenCalled();
        const callArgs = interaction.reply.mock.calls[0][0];
        const text = getContainerText(callArgs);
        expect(text).toContain('Invalid selection');
      });
    });
  });
});
