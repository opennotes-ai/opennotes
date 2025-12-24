import { jest, describe, it, expect, beforeEach } from '@jest/globals';
import { ButtonStyle, ComponentType, type APIButtonComponentWithCustomId } from 'discord.js';
import { VIBE_CHECK_DAYS_OPTIONS } from '../../src/types/bulk-scan.js';
import { loggerFactory } from '../factories/index.js';

const mockLogger = loggerFactory.build();

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
      const collectHandlers: Map<string, (...args: any[]) => void> = new Map();
      const mockCollector = {
        on: jest.fn<(event: string, handler: (...args: any[]) => void) => any>((event, handler) => {
          collectHandlers.set(event, handler);
          return mockCollector;
        }),
        stop: jest.fn(),
      };

      const mockPromptMessage = {
        id: 'prompt-message-123',
        createMessageComponentCollector: jest.fn().mockReturnValue(mockCollector),
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
        mockCollector,
        collectHandlers,
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

    it('should filter interactions to only the admin who triggered the prompt', async () => {
      const { mockAdmin, mockBotChannel, mockPromptMessage } = createMockSetup();

      await sendVibeCheckPrompt({
        botChannel: mockBotChannel as any,
        admin: mockAdmin as any,
        guildId: 'guild-123',
      });

      expect(mockPromptMessage.createMessageComponentCollector).toHaveBeenCalledWith(
        expect.objectContaining({
          filter: expect.any(Function),
        })
      );

      const collectorOptions = mockPromptMessage.createMessageComponentCollector.mock.calls[0][0] as { filter: (i: { user: { id: string } }) => boolean };
      const filter = collectorOptions.filter;

      const adminInteraction = { user: { id: 'admin-123' } };
      const otherInteraction = { user: { id: 'other-user' } };

      expect(filter(adminInteraction)).toBe(true);
      expect(filter(otherInteraction)).toBe(false);
    });

    it('should handle No Thanks button click by dismissing the prompt', async () => {
      const { mockAdmin, mockBotChannel, collectHandlers } = createMockSetup();

      await sendVibeCheckPrompt({
        botChannel: mockBotChannel as any,
        admin: mockAdmin as any,
        guildId: 'guild-123',
      });

      const mockButtonInteraction = {
        customId: VIBECHECK_PROMPT_CUSTOM_IDS.NO_THANKS,
        user: { id: 'admin-123' },
        isButton: () => true,
        isStringSelectMenu: () => false,
        update: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      const collectHandler = collectHandlers.get('collect');
      expect(collectHandler).toBeDefined();

      if (collectHandler) {
        await collectHandler(mockButtonInteraction);
      }

      expect(mockButtonInteraction.update).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('dismissed'),
          components: [],
        })
      );
    });

    it('should update buttons when days are selected from dropdown', async () => {
      const { mockAdmin, mockBotChannel, collectHandlers } = createMockSetup();

      await sendVibeCheckPrompt({
        botChannel: mockBotChannel as any,
        admin: mockAdmin as any,
        guildId: 'guild-123',
      });

      const mockSelectInteraction = {
        customId: VIBECHECK_PROMPT_CUSTOM_IDS.DAYS_SELECT,
        user: { id: 'admin-123' },
        isButton: () => false,
        isStringSelectMenu: () => true,
        values: ['7'],
        update: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      const collectHandler = collectHandlers.get('collect');
      if (collectHandler) {
        await collectHandler(mockSelectInteraction);
      }

      expect(mockSelectInteraction.update).toHaveBeenCalledWith(
        expect.objectContaining({
          components: expect.arrayContaining([
            expect.anything(),
            expect.objectContaining({
              components: expect.arrayContaining([
                expect.objectContaining({
                  data: expect.objectContaining({
                    disabled: false,
                  }),
                }),
              ]),
            }),
          ]),
        })
      );
    });

    it('should trigger vibecheck scan when Start button is clicked after selecting days', async () => {
      const { mockAdmin, mockBotChannel, collectHandlers } = createMockSetup();

      await sendVibeCheckPrompt({
        botChannel: mockBotChannel as any,
        admin: mockAdmin as any,
        guildId: 'guild-123',
      });

      const mockSelectInteraction = {
        customId: VIBECHECK_PROMPT_CUSTOM_IDS.DAYS_SELECT,
        user: { id: 'admin-123' },
        isButton: () => false,
        isStringSelectMenu: () => true,
        values: ['7'],
        update: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      const collectHandler = collectHandlers.get('collect');
      if (collectHandler) {
        await collectHandler(mockSelectInteraction);
      }

      const mockStartInteraction = {
        customId: VIBECHECK_PROMPT_CUSTOM_IDS.START,
        user: { id: 'admin-123' },
        isButton: () => true,
        isStringSelectMenu: () => false,
        update: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      if (collectHandler) {
        await collectHandler(mockStartInteraction);
      }

      expect(mockExecuteBulkScan).toHaveBeenCalledWith(
        expect.objectContaining({
          guild: mockBotChannel.guild,
          days: 7,
          initiatorId: 'admin-123',
        })
      );
    });

    it('should handle timeout by cleaning up the prompt message', async () => {
      const { mockAdmin, mockBotChannel, collectHandlers, mockPromptMessage } = createMockSetup();

      await sendVibeCheckPrompt({
        botChannel: mockBotChannel as any,
        admin: mockAdmin as any,
        guildId: 'guild-123',
      });

      const endHandler = collectHandlers.get('end');
      expect(endHandler).toBeDefined();

      if (endHandler) {
        await endHandler(new Map(), 'time');
      }

      expect(mockPromptMessage.edit).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('expired'),
          components: [],
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
