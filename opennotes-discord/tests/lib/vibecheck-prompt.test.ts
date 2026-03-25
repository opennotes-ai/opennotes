import { jest, describe, it, expect, beforeEach } from '@jest/globals';
import { ButtonStyle, ComponentType, type APIButtonComponentWithCustomId } from 'discord.js';
import { VIBE_CHECK_DAYS_OPTIONS } from '../../src/types/bulk-scan.js';
import { loggerFactory } from '../factories/index.js';

const mockLogger = loggerFactory.build();

const mockSetVibecheckPromptState = jest.fn<(...args: any[]) => Promise<void>>().mockResolvedValue(undefined);

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
}));

jest.unstable_mockModule('../../src/handlers/vibecheck-prompt-handler.js', () => ({
  setVibecheckPromptState: mockSetVibecheckPromptState,
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

const {
  sendVibeCheckPrompt,
  createDaysButtons,
  createPromptButtons,
  VIBECHECK_PROMPT_CUSTOM_IDS,
} = await import('../../src/lib/vibecheck-prompt.js');

function extractTextFromContainer(containerJson: any): string {
  if (!containerJson || !containerJson.components) return '';
  return containerJson.components
    .filter((c: any) => c.type === 10)
    .map((c: any) => c.content || '')
    .join('\n');
}

describe('vibecheck-prompt', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('createDaysButtons', () => {
    it('should create buttons for all days options', () => {
      const row = createDaysButtons();
      const json = row.toJSON();

      expect(json.type).toBe(ComponentType.ActionRow);
      expect(json.components).toHaveLength(VIBE_CHECK_DAYS_OPTIONS.length);

      VIBE_CHECK_DAYS_OPTIONS.forEach((option, index) => {
        const button = json.components[index] as APIButtonComponentWithCustomId;
        expect(button.label).toBe(option.name);
        expect(button.custom_id).toBe(`${VIBECHECK_PROMPT_CUSTOM_IDS.DAYS_PREFIX}${option.value}`);
        expect(button.style).toBe(ButtonStyle.Secondary);
      });
    });

    it('should highlight the selected day button', () => {
      const row = createDaysButtons(7);
      const json = row.toJSON();

      VIBE_CHECK_DAYS_OPTIONS.forEach((option, index) => {
        const button = json.components[index] as APIButtonComponentWithCustomId;
        if (option.value === 7) {
          expect(button.style).toBe(ButtonStyle.Primary);
        } else {
          expect(button.style).toBe(ButtonStyle.Secondary);
        }
      });
    });

    it('should use Secondary style for all when no selection', () => {
      const row = createDaysButtons(null);
      const json = row.toJSON();

      json.components.forEach((button: any) => {
        expect(button.style).toBe(ButtonStyle.Secondary);
      });
    });
  });

  describe('createPromptButtons', () => {
    it('should create Start and No Thanks buttons', () => {
      const buttons = createPromptButtons();
      const json = buttons.toJSON();

      expect(json.components).toHaveLength(2);

      const startButton = json.components[0] as APIButtonComponentWithCustomId;
      const noThanksButton = json.components[1] as APIButtonComponentWithCustomId;

      expect(startButton.custom_id).toBe(VIBECHECK_PROMPT_CUSTOM_IDS.START);
      expect(startButton.label).toContain('Start');
      expect(startButton.style).toBe(ButtonStyle.Primary);

      expect(noThanksButton.custom_id).toBe(VIBECHECK_PROMPT_CUSTOM_IDS.NO_THANKS);
      expect(noThanksButton.label).toContain('No');
      expect(noThanksButton.style).toBe(ButtonStyle.Secondary);
    });

    it('should have Start button disabled by default', () => {
      const buttons = createPromptButtons();
      const json = buttons.toJSON();

      const startButton = json.components[0] as APIButtonComponentWithCustomId;
      expect(startButton.disabled).toBe(true);
    });

    it('should enable Start button when enabled parameter is true', () => {
      const buttons = createPromptButtons(true);
      const json = buttons.toJSON();

      const startButton = json.components[0] as APIButtonComponentWithCustomId;
      expect(startButton.disabled).toBe(false);
    });
  });

  describe('sendVibeCheckPrompt', () => {
    const createMockSetup = () => {
      const mockPromptMessage = {
        id: 'prompt-message-123',
        edit: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      const mockAdmin = {
        id: 'admin-123',
        username: 'testadmin',
        createDM: jest.fn<() => Promise<any>>(),
      };

      const channelsCache = new Map();
      const textChannel = {
        id: 'text-channel-1',
        name: 'general',
        type: 0,
        viewable: true,
        messages: {
          fetch: jest.fn<(opts: any) => Promise<Map<string, any>>>().mockResolvedValue(new Map()),
        },
      };
      channelsCache.set('text-channel-1', textChannel);

      (channelsCache as any).filter = (fn: (ch: any) => boolean) => {
        const result = new Map();
        for (const [k, v] of channelsCache) {
          if (fn(v)) result.set(k, v);
        }
        return result;
      };

      const mockBotChannel = {
        id: 'bot-channel-123',
        name: 'open-notes',
        send: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue(mockPromptMessage),
        guild: {
          id: 'guild-123',
          name: 'Test Guild',
          channels: {
            cache: channelsCache,
          },
        },
      };

      return {
        mockAdmin,
        mockBotChannel,
        mockPromptMessage,
      };
    };

    it('should send v2 container to bot channel with days buttons and prompt buttons', async () => {
      const { mockAdmin, mockBotChannel } = createMockSetup();

      await sendVibeCheckPrompt({
        botChannel: mockBotChannel as any,
        admin: mockAdmin as any,
        guildId: 'guild-123',
      });

      expect(mockAdmin.createDM).not.toHaveBeenCalled();
      expect(mockBotChannel.send).toHaveBeenCalledTimes(1);

      const sendCall = mockBotChannel.send.mock.calls[0][0];
      expect(sendCall.components).toBeDefined();
      expect(sendCall.flags).toBeDefined();
      const container = sendCall.components[0];
      expect(container.type).toBe(17);
      const text = extractTextFromContainer(container);
      expect(text).toContain('Vibe Check');
    });

    it('should include @mention of the admin in the container text', async () => {
      const { mockAdmin, mockBotChannel } = createMockSetup();

      await sendVibeCheckPrompt({
        botChannel: mockBotChannel as any,
        admin: mockAdmin as any,
        guildId: 'guild-123',
      });

      const sendCall = mockBotChannel.send.mock.calls[0][0];
      const container = sendCall.components[0];
      const text = extractTextFromContainer(container);
      expect(text).toContain('<@admin-123>');
    });

    it('should include introductory text explaining the vibe check feature', async () => {
      const { mockAdmin, mockBotChannel } = createMockSetup();

      await sendVibeCheckPrompt({
        botChannel: mockBotChannel as any,
        admin: mockAdmin as any,
        guildId: 'guild-123',
      });

      const sendCall = mockBotChannel.send.mock.calls[0][0];
      const container = sendCall.components[0];
      const text = extractTextFromContainer(container);
      expect(text.toLowerCase()).toContain('scan');
      expect(text.toLowerCase()).toContain('misinformation');
    });

    it('should store prompt state in Redis after sending message', async () => {
      const { mockAdmin, mockBotChannel, mockPromptMessage } = createMockSetup();

      await sendVibeCheckPrompt({
        botChannel: mockBotChannel as any,
        admin: mockAdmin as any,
        guildId: 'guild-123',
      });

      expect(mockSetVibecheckPromptState).toHaveBeenCalledWith(
        mockPromptMessage.id,
        {
          guildId: 'guild-123',
          adminId: 'admin-123',
          botChannelId: 'bot-channel-123',
          selectedDays: null,
        }
      );
    });

    it('should handle send failure gracefully', async () => {
      const { mockAdmin, mockBotChannel } = createMockSetup();
      mockBotChannel.send.mockRejectedValue(new Error('Send failed'));

      await sendVibeCheckPrompt({
        botChannel: mockBotChannel as any,
        admin: mockAdmin as any,
        guildId: 'guild-123',
      });

      expect(mockSetVibecheckPromptState).not.toHaveBeenCalled();
      expect(mockLogger.warn).toHaveBeenCalledWith(
        'Failed to send vibe check prompt in bot channel',
        expect.objectContaining({
          error: 'Send failed',
        })
      );
    });

    it('should edit message to show error container when state storage fails', async () => {
      const { mockAdmin, mockBotChannel, mockPromptMessage } = createMockSetup();
      mockSetVibecheckPromptState.mockRejectedValue(new Error('Redis error'));

      await sendVibeCheckPrompt({
        botChannel: mockBotChannel as any,
        admin: mockAdmin as any,
        guildId: 'guild-123',
      });

      expect(mockBotChannel.send).toHaveBeenCalled();
      expect(mockLogger.error).toHaveBeenCalledWith(
        'Failed to store vibecheck prompt state in Redis',
        expect.objectContaining({
          error: 'Redis error',
        })
      );
      expect(mockPromptMessage.edit).toHaveBeenCalled();
      const editCall = mockPromptMessage.edit.mock.calls[0][0];
      expect(editCall.components).toBeDefined();
      expect(editCall.flags).toBeDefined();
      const container = editCall.components[0];
      const text = extractTextFromContainer(container);
      expect(text).toContain('Failed to set up vibe check prompt');
    });

    it('should handle message edit failure after state storage failure gracefully', async () => {
      const { mockAdmin, mockBotChannel, mockPromptMessage } = createMockSetup();
      mockSetVibecheckPromptState.mockRejectedValue(new Error('Redis error'));
      mockPromptMessage.edit.mockRejectedValue(new Error('Edit failed'));

      await sendVibeCheckPrompt({
        botChannel: mockBotChannel as any,
        admin: mockAdmin as any,
        guildId: 'guild-123',
      });

      expect(mockBotChannel.send).toHaveBeenCalled();
      expect(mockLogger.error).toHaveBeenCalledWith(
        'Failed to store vibecheck prompt state in Redis',
        expect.any(Object)
      );
      expect(mockPromptMessage.edit).toHaveBeenCalled();
      expect(mockLogger.debug).toHaveBeenCalledWith(
        'Failed to edit message after state storage failure',
        expect.objectContaining({
          error: 'Edit failed',
        })
      );
    });
  });

  describe('custom ID constants', () => {
    it('should have unique custom IDs for all components', () => {
      const ids = Object.values(VIBECHECK_PROMPT_CUSTOM_IDS);
      const uniqueIds = new Set(ids);

      expect(uniqueIds.size).toBe(ids.length);
    });

    it('should have custom IDs under 100 characters', () => {
      Object.values(VIBECHECK_PROMPT_CUSTOM_IDS).forEach((id: string) => {
        expect(id.length).toBeLessThan(100);
      });
    });
  });
});
