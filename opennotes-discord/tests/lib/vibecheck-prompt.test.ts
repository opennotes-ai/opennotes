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
  createDaysSelectMenu,
  createPromptButtons,
  VIBECHECK_PROMPT_CUSTOM_IDS,
} = await import('../../src/lib/vibecheck-prompt.js');

describe('vibecheck-prompt', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('createDaysSelectMenu', () => {
    it('should create a select menu with all days options', () => {
      const menu = createDaysSelectMenu();
      const json = menu.toJSON();

      expect(json.type).toBe(ComponentType.StringSelect);
      expect(json.custom_id).toBe(VIBECHECK_PROMPT_CUSTOM_IDS.DAYS_SELECT);
      expect(json.options).toHaveLength(VIBE_CHECK_DAYS_OPTIONS.length);

      VIBE_CHECK_DAYS_OPTIONS.forEach((option, index) => {
        expect(json.options[index].label).toBe(option.name);
        expect(json.options[index].value).toBe(option.value.toString());
      });
    });

    it('should have a placeholder text', () => {
      const menu = createDaysSelectMenu();
      const json = menu.toJSON();

      expect(json.placeholder).toBeDefined();
      expect(json.placeholder).toContain('days');
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

    it('should send message to bot channel (not DM) with days select and buttons', async () => {
      const { mockAdmin, mockBotChannel } = createMockSetup();

      await sendVibeCheckPrompt({
        botChannel: mockBotChannel as any,
        admin: mockAdmin as any,
        guildId: 'guild-123',
      });

      expect(mockAdmin.createDM).not.toHaveBeenCalled();
      expect(mockBotChannel.send).toHaveBeenCalledTimes(1);

      const sendCall = mockBotChannel.send.mock.calls[0][0];
      expect(sendCall.content).toBeDefined();
      expect(sendCall.content).toContain('Vibe Check');
      expect(sendCall.components).toHaveLength(2);
    });

    it('should include @mention of the admin in the message', async () => {
      const { mockAdmin, mockBotChannel } = createMockSetup();

      await sendVibeCheckPrompt({
        botChannel: mockBotChannel as any,
        admin: mockAdmin as any,
        guildId: 'guild-123',
      });

      const sendCall = mockBotChannel.send.mock.calls[0][0];
      expect(sendCall.content).toContain('<@admin-123>');
    });

    it('should include introductory text explaining the vibe check feature', async () => {
      const { mockAdmin, mockBotChannel } = createMockSetup();

      await sendVibeCheckPrompt({
        botChannel: mockBotChannel as any,
        admin: mockAdmin as any,
        guildId: 'guild-123',
      });

      const sendCall = mockBotChannel.send.mock.calls[0][0];
      expect(sendCall.content.toLowerCase()).toContain('scan');
      expect(sendCall.content.toLowerCase()).toContain('misinformation');
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

    it('should edit message to show error when state storage fails', async () => {
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
      expect(mockPromptMessage.edit).toHaveBeenCalledWith({
        content: expect.stringContaining('Failed to set up vibe check prompt'),
        components: [],
      });
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
