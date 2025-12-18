import { jest, describe, it, expect, beforeEach } from '@jest/globals';
import { MessageFlags, ButtonStyle, ComponentType, type APIButtonComponentWithCustomId } from 'discord.js';
import { VIBE_CHECK_DAYS_OPTIONS } from '../../src/types/bulk-scan.js';

const mockLogger = {
  info: jest.fn<(...args: unknown[]) => void>(),
  error: jest.fn<(...args: unknown[]) => void>(),
  warn: jest.fn<(...args: unknown[]) => void>(),
  debug: jest.fn<(...args: unknown[]) => void>(),
};

const mockApiClient = {
  checkRecentScan: jest.fn<(communityServerId: string) => Promise<boolean>>(),
  initiateBulkScan: jest.fn<(guildId: string, days: number) => Promise<any>>(),
  getBulkScanResults: jest.fn<(scanId: string) => Promise<any>>(),
  createNoteRequestsFromScan: jest.fn<(scanId: string, messageIds: string[], generateAiNotes: boolean) => Promise<any>>(),
};

const mockNatsPublisher = {
  publishBulkScanBatch: jest.fn<(...args: unknown[]) => Promise<void>>().mockResolvedValue(undefined),
  isConnected: jest.fn<() => boolean>().mockReturnValue(true),
};

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
}));

jest.unstable_mockModule('../../src/api-client.js', () => ({
  apiClient: mockApiClient,
}));

jest.unstable_mockModule('../../src/events/NatsPublisher.js', () => ({
  natsPublisher: mockNatsPublisher,
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
    const createMockChannel = (includeTextChannels = false) => {
      const collectHandlers: Map<string, (...args: any[]) => void> = new Map();
      const mockCollector = {
        on: jest.fn<(event: string, handler: (...args: any[]) => void) => any>((event, handler) => {
          collectHandlers.set(event, handler);
          return mockCollector;
        }),
        stop: jest.fn(),
      };

      const mockMessage = {
        id: 'message-123',
        createMessageComponentCollector: jest.fn().mockReturnValue(mockCollector),
        edit: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      const channelsCache = new Map();

      if (includeTextChannels) {
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
      }

      (channelsCache as any).filter = (fn: (ch: any) => boolean) => {
        const result = new Map();
        for (const [k, v] of channelsCache) {
          if (fn(v)) result.set(k, v);
        }
        return result;
      };

      const mockChannel = {
        id: 'channel-123',
        name: 'open-notes',
        guild: {
          id: 'guild-123',
          name: 'Test Guild',
          channels: {
            cache: channelsCache,
          },
        },
        send: jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue(mockMessage),
      };

      return { mockChannel, mockCollector, collectHandlers, mockMessage };
    };

    it('should send an ephemeral message with days select and buttons', async () => {
      const { mockChannel } = createMockChannel();

      await sendVibeCheckPrompt({
        channel: mockChannel as any,
        adminId: 'admin-123',
        guildId: 'guild-123',
      });

      expect(mockChannel.send).toHaveBeenCalledTimes(1);
      const sendCall = mockChannel.send.mock.calls[0][0];

      expect(sendCall.content).toBeDefined();
      expect(sendCall.content).toContain('Vibe Check');
      expect(sendCall.components).toHaveLength(2);
    });

    it('should include introductory text explaining the vibe check feature', async () => {
      const { mockChannel } = createMockChannel();

      await sendVibeCheckPrompt({
        channel: mockChannel as any,
        adminId: 'admin-123',
        guildId: 'guild-123',
      });

      const sendCall = mockChannel.send.mock.calls[0][0];
      expect(sendCall.content.toLowerCase()).toContain('scan');
      expect(sendCall.content.toLowerCase()).toContain('misinformation');
    });

    it('should filter interactions to only the admin who triggered the prompt', async () => {
      const { mockChannel, mockMessage } = createMockChannel();

      await sendVibeCheckPrompt({
        channel: mockChannel as any,
        adminId: 'admin-123',
        guildId: 'guild-123',
      });

      expect(mockMessage.createMessageComponentCollector).toHaveBeenCalledWith(
        expect.objectContaining({
          filter: expect.any(Function),
        })
      );

      const collectorOptions = mockMessage.createMessageComponentCollector.mock.calls[0][0] as { filter: (i: { user: { id: string } }) => boolean };
      const filter = collectorOptions.filter;

      const adminInteraction = { user: { id: 'admin-123' } };
      const otherInteraction = { user: { id: 'other-user' } };

      expect(filter(adminInteraction)).toBe(true);
      expect(filter(otherInteraction)).toBe(false);
    });

    it('should handle No Thanks button click by dismissing the prompt', async () => {
      const { mockChannel, collectHandlers } = createMockChannel();

      await sendVibeCheckPrompt({
        channel: mockChannel as any,
        adminId: 'admin-123',
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
      const { mockChannel, collectHandlers } = createMockChannel();

      await sendVibeCheckPrompt({
        channel: mockChannel as any,
        adminId: 'admin-123',
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
      const { mockChannel, collectHandlers, mockMessage } = createMockChannel(true);

      mockApiClient.initiateBulkScan.mockResolvedValue({
        scan_id: 'scan-123',
        status: 'pending',
        community_server_id: 'guild-123',
        scan_window_days: 7,
      });

      mockApiClient.getBulkScanResults.mockResolvedValue({
        scan_id: 'scan-123',
        status: 'completed',
        messages_scanned: 100,
        flagged_messages: [],
      });

      await sendVibeCheckPrompt({
        channel: mockChannel as any,
        adminId: 'admin-123',
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
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        channel: mockChannel,
        guild: mockChannel.guild,
      };

      if (collectHandler) {
        await collectHandler(mockStartInteraction);
      }

      expect(mockApiClient.initiateBulkScan).toHaveBeenCalledWith('guild-123', 7);
    });

    it('should handle timeout by cleaning up the message', async () => {
      const { mockChannel, collectHandlers, mockMessage } = createMockChannel();

      await sendVibeCheckPrompt({
        channel: mockChannel as any,
        adminId: 'admin-123',
        guildId: 'guild-123',
      });

      const endHandler = collectHandlers.get('end');
      expect(endHandler).toBeDefined();

      const mockEdit = jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({});
      (mockMessage as any).edit = mockEdit;

      if (endHandler) {
        await endHandler(new Map(), 'time');
      }

      expect(mockEdit).toHaveBeenCalledWith(
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
