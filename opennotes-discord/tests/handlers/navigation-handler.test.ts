import { jest, describe, it, expect, beforeEach } from '@jest/globals';
import { loggerFactory } from '../factories/index.js';
import type { ButtonInteraction } from 'discord.js';

const mockLogger = loggerFactory.build();

const mockCacheGet = jest.fn<(...args: any[]) => Promise<any>>();
const mockCacheSet = jest.fn<(...args: any[]) => Promise<boolean>>().mockResolvedValue(true);
const mockCacheDelete = jest.fn<(...args: any[]) => Promise<boolean>>().mockResolvedValue(true);
const mockCacheExpire = jest.fn<(...args: any[]) => Promise<boolean>>().mockResolvedValue(true);

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
}));

jest.unstable_mockModule('../../src/cache.js', () => ({
  cache: {
    get: mockCacheGet,
    set: mockCacheSet,
    delete: mockCacheDelete,
    exists: jest.fn(),
    expire: mockCacheExpire,
    mget: jest.fn(),
    mset: jest.fn(),
    clear: jest.fn(),
    ping: jest.fn(),
    getMetrics: jest.fn(),
    start: jest.fn(),
    stop: jest.fn(),
  },
}));

const mockBuildWelcomeContainer = jest.fn().mockReturnValue({
  addActionRowComponents: jest.fn().mockReturnThis(),
  toJSON: jest.fn().mockReturnValue({ type: 17, components: [] }),
});

jest.unstable_mockModule('../../src/lib/welcome-content.js', () => ({
  buildWelcomeContainer: mockBuildWelcomeContainer,
  WELCOME_MESSAGE_REVISION: '2025-12-24.1',
}));

const mockStatusExecute = jest.fn<(...args: any[]) => Promise<any>>();
const mockGetScoringStatus = jest.fn<(...args: any[]) => Promise<any>>();
const mockListRequestsExecute = jest.fn<(...args: any[]) => Promise<any>>();

const mockServiceProvider = {
  getStatusService: jest.fn().mockReturnValue({ execute: mockStatusExecute }),
  getScoringService: jest.fn().mockReturnValue({
    getScoringStatus: mockGetScoringStatus,
  }),
  getListRequestsService: jest.fn().mockReturnValue({ execute: mockListRequestsExecute }),
};

jest.unstable_mockModule('../../src/services/index.js', () => ({
  serviceProvider: mockServiceProvider,
}));

const mockFormatStatusSuccessV2 = jest.fn().mockReturnValue({
  container: {
    addSeparatorComponents: jest.fn().mockReturnThis(),
    addTextDisplayComponents: jest.fn().mockReturnThis(),
    addActionRowComponents: jest.fn().mockReturnThis(),
    toJSON: jest.fn().mockReturnValue({ type: 17, components: [] }),
  },
  flags: 32768,
});
const mockFormatScoringStatusV2 = jest.fn().mockReturnValue({
  separator: {},
  textDisplay: {},
});
const mockFormatErrorV2 = jest.fn().mockReturnValue({
  components: [{ type: 17, components: [] }],
  flags: 32768,
});
const mockFormatListRequestsSuccessV2 = jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({
  container: {
    addActionRowComponents: jest.fn().mockReturnThis(),
    toJSON: jest.fn().mockReturnValue({ type: 17, components: [] }),
  },
  components: [{ type: 17, components: [] }],
  flags: 32768,
  actionRows: [],
});

jest.unstable_mockModule('../../src/services/DiscordFormatter.js', () => ({
  DiscordFormatter: {
    formatStatusSuccessV2: mockFormatStatusSuccessV2,
    formatScoringStatusV2: mockFormatScoringStatusV2,
    formatErrorV2: mockFormatErrorV2,
    formatListRequestsSuccessV2: mockFormatListRequestsSuccessV2,
  },
}));

const mockResolveUserProfileId = jest.fn<(...args: any[]) => Promise<string>>().mockResolvedValue('profile-uuid-123');

jest.unstable_mockModule('../../src/lib/user-profile-resolver.js', () => ({
  resolveUserProfileId: mockResolveUserProfileId,
}));

const mockGetCommunityServerByPlatformId = jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({
  data: { id: 'community-server-uuid-456' },
});
const mockListNotesWithStatus = jest.fn<(...args: any[]) => Promise<any>>().mockResolvedValue({
  data: [],
  total: 0,
});

jest.unstable_mockModule('../../src/api-client.js', () => ({
  apiClient: {
    getCommunityServerByPlatformId: mockGetCommunityServerByPlatformId,
    listNotesWithStatus: mockListNotesWithStatus,
  },
}));

const { handleNavInteraction } = await import('../../src/handlers/navigation-handler.js');

function buildMockInteraction(overrides: Record<string, any> = {}): ButtonInteraction {
  return {
    customId: 'nav:menu',
    user: { id: 'user-123' },
    message: {
      id: 'msg-456',
      content: '',
      components: [
        { toJSON: () => ({ type: 1, components: [{ type: 2, label: 'Old Button' }] }) },
      ],
      flags: { bitfield: 32768 },
    },
    update: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
    reply: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
    editReply: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
    deferReply: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
    guildId: 'guild-789',
    client: { guilds: { cache: { size: 5 } } },
    isButton: () => true,
    ...overrides,
  } as unknown as ButtonInteraction;
}

describe('navigation-handler', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockCacheGet.mockResolvedValue(null);
    mockCacheSet.mockResolvedValue(true);
    mockCacheDelete.mockResolvedValue(true);

    mockBuildWelcomeContainer.mockReturnValue({
      addActionRowComponents: jest.fn().mockReturnThis(),
      toJSON: jest.fn().mockReturnValue({ type: 17, components: [] }),
    });

    mockServiceProvider.getStatusService.mockReturnValue({ execute: mockStatusExecute });
    mockServiceProvider.getScoringService.mockReturnValue({
      getScoringStatus: mockGetScoringStatus,
    });
    mockServiceProvider.getListRequestsService.mockReturnValue({ execute: mockListRequestsExecute });

    mockStatusExecute.mockResolvedValue({
      success: true,
      data: { status: 'ok' },
    });
    mockGetScoringStatus.mockResolvedValue({
      success: true,
      data: { scoring: 'ok' },
    });
    mockListRequestsExecute.mockResolvedValue({
      success: true,
      data: { requests: [], total: 0, page: 1, size: 20 },
    });

    mockFormatStatusSuccessV2.mockReturnValue({
      container: {
        addSeparatorComponents: jest.fn().mockReturnThis(),
        addTextDisplayComponents: jest.fn().mockReturnThis(),
        addActionRowComponents: jest.fn().mockReturnThis(),
        toJSON: jest.fn().mockReturnValue({ type: 17, components: [] }),
      },
      flags: 32768,
    });
    mockFormatScoringStatusV2.mockReturnValue({
      separator: {},
      textDisplay: {},
    });
    mockFormatErrorV2.mockReturnValue({
      components: [{ type: 17, components: [] }],
      flags: 32768,
    });
    mockFormatListRequestsSuccessV2.mockResolvedValue({
      container: {
        addActionRowComponents: jest.fn().mockReturnThis(),
        toJSON: jest.fn().mockReturnValue({ type: 17, components: [] }),
      },
      components: [{ type: 17, components: [] }],
      flags: 32768,
      actionRows: [],
    });

    mockResolveUserProfileId.mockResolvedValue('profile-uuid-123');
    mockGetCommunityServerByPlatformId.mockResolvedValue({
      data: { id: 'community-server-uuid-456' },
    });
    mockListNotesWithStatus.mockResolvedValue({
      data: [],
      total: 0,
    });
  });

  describe('nav:menu', () => {
    it('should push current screen state to nav stack', async () => {
      const interaction = buildMockInteraction({ customId: 'nav:menu' });

      await handleNavInteraction(interaction);

      expect(mockCacheGet).toHaveBeenCalledWith(
        expect.stringContaining('nav_state:user-123:msg-456')
      );
      expect(mockCacheSet).toHaveBeenCalledWith(
        expect.stringContaining('nav_state:user-123:msg-456'),
        expect.arrayContaining([
          expect.objectContaining({
            components: expect.any(Array),
            flags: expect.any(Number),
          }),
        ]),
        900,
      );
    });

    it('should capture message components via toJSON()', async () => {
      const interaction = buildMockInteraction({ customId: 'nav:menu' });

      await handleNavInteraction(interaction);

      const setCalls = mockCacheSet.mock.calls;
      expect(setCalls.length).toBe(1);
      const savedStack = setCalls[0][1] as any[];
      const savedState = savedStack[0];
      expect(savedState.components).toEqual([
        { type: 1, components: [{ type: 2, label: 'Old Button' }] },
      ]);
    });

    it('should capture message flags bitfield', async () => {
      const interaction = buildMockInteraction({ customId: 'nav:menu' });

      await handleNavInteraction(interaction);

      const setCalls = mockCacheSet.mock.calls;
      const savedStack = setCalls[0][1] as any[];
      const savedState = savedStack[0];
      expect(savedState.flags).toBe(32768);
    });

    it('should capture message content when non-empty', async () => {
      const interaction = buildMockInteraction({
        customId: 'nav:menu',
        message: {
          id: 'msg-456',
          content: 'Some vibecheck result text',
          components: [
            { toJSON: () => ({ type: 1, components: [{ type: 2, label: 'Old Button' }] }) },
          ],
          flags: { bitfield: 32768 },
        },
      });

      await handleNavInteraction(interaction);

      const setCalls = mockCacheSet.mock.calls;
      const savedStack = setCalls[0][1] as any[];
      const savedState = savedStack[0];
      expect(savedState.content).toBe('Some vibecheck result text');
    });

    it('should not store content when message content is empty', async () => {
      const interaction = buildMockInteraction({ customId: 'nav:menu' });

      await handleNavInteraction(interaction);

      const setCalls = mockCacheSet.mock.calls;
      const savedStack = setCalls[0][1] as any[];
      const savedState = savedStack[0];
      expect(savedState.content).toBeUndefined();
    });

    it('should update the message with contextual hub content', async () => {
      const interaction = buildMockInteraction({ customId: 'nav:menu' });

      await handleNavInteraction(interaction);

      expect(interaction.update).toHaveBeenCalledTimes(1);
      const updateCall = (interaction.update as any).mock.calls[0][0] as Record<string, any>;
      expect(updateCall).toHaveProperty('components');
      expect(updateCall.components.length).toBeGreaterThan(0);
    });
  });

  describe('nav:back', () => {
    it('should restore previous screen state when stack has entries', async () => {
      const savedState = {
        commandContext: 'list:notes',
        components: [{ type: 1, components: [{ type: 2, label: 'Restored Button' }] }],
        flags: 32768,
      };
      mockCacheGet.mockResolvedValueOnce([savedState]);

      const interaction = buildMockInteraction({ customId: 'nav:back' });

      await handleNavInteraction(interaction);

      expect(interaction.update).toHaveBeenCalledTimes(1);
      const updateCall = (interaction.update as any).mock.calls[0][0] as Record<string, any>;
      expect(updateCall.components).toEqual(savedState.components);
      expect(updateCall.flags).toBe(savedState.flags);
    });

    it('should update the cache after popping state', async () => {
      const savedState = {
        commandContext: 'list:notes',
        components: [{ type: 1, components: [] }],
        flags: 32768,
      };
      mockCacheGet.mockResolvedValueOnce([savedState]);

      const interaction = buildMockInteraction({ customId: 'nav:back' });

      await handleNavInteraction(interaction);

      expect(mockCacheSet).toHaveBeenCalledWith(
        expect.stringContaining('nav_state:user-123:msg-456'),
        [],
        900,
      );
    });

    it('should restore content when present in saved state', async () => {
      const savedState = {
        commandContext: 'vibecheck:status',
        content: 'Vibecheck scan completed with 3 flagged messages.',
        components: [{ type: 1, components: [{ type: 2, label: 'Restored Button' }] }],
        flags: 32768,
      };
      mockCacheGet.mockResolvedValueOnce([savedState]);

      const interaction = buildMockInteraction({ customId: 'nav:back' });

      await handleNavInteraction(interaction);

      expect(interaction.update).toHaveBeenCalledTimes(1);
      const updateCall = (interaction.update as any).mock.calls[0][0] as Record<string, any>;
      expect(updateCall.content).toBe('Vibecheck scan completed with 3 flagged messages.');
    });

    it('should restore empty string content when state has no content', async () => {
      const savedState = {
        commandContext: 'list:notes',
        components: [{ type: 1, components: [] }],
        flags: 32768,
      };
      mockCacheGet.mockResolvedValueOnce([savedState]);

      const interaction = buildMockInteraction({ customId: 'nav:back' });

      await handleNavInteraction(interaction);

      expect(interaction.update).toHaveBeenCalledTimes(1);
      const updateCall = (interaction.update as any).mock.calls[0][0] as Record<string, any>;
      expect(updateCall.content).toBe('');
    });

    it('should reply with "Nothing to go back to" when stack is empty', async () => {
      mockCacheGet.mockResolvedValueOnce(null);

      const interaction = buildMockInteraction({ customId: 'nav:back' });

      await handleNavInteraction(interaction);

      expect(interaction.reply).toHaveBeenCalledTimes(1);
      const replyCall = (interaction.reply as any).mock.calls[0][0] as Record<string, any>;
      expect(replyCall.content).toContain('Nothing to go back to');
      expect(replyCall.flags).toBeTruthy();
    });
  });

  describe('nav:hub', () => {
    it('should navigate to the full static hub', async () => {
      const interaction = buildMockInteraction({ customId: 'nav:hub' });

      await handleNavInteraction(interaction);

      expect(interaction.update).toHaveBeenCalledTimes(1);
      const updateCall = (interaction.update as any).mock.calls[0][0] as Record<string, any>;
      expect(updateCall).toHaveProperty('components');
      expect(updateCall.components.length).toBeGreaterThan(0);
    });

    it('should clear the nav stack', async () => {
      const interaction = buildMockInteraction({ customId: 'nav:hub' });

      await handleNavInteraction(interaction);

      expect(mockCacheDelete).toHaveBeenCalledWith(
        expect.stringContaining('nav_state:user-123:msg-456')
      );
    });
  });

  describe('nav:{action} dispatch routing', () => {
    it('should dispatch about-opennotes to welcome container', async () => {
      const interaction = buildMockInteraction({ customId: 'nav:about-opennotes' });

      await handleNavInteraction(interaction);

      expect(interaction.deferReply).toHaveBeenCalledTimes(1);
      expect(mockBuildWelcomeContainer).toHaveBeenCalledTimes(1);
      expect(interaction.editReply).toHaveBeenCalledTimes(1);
    });

    it('should dispatch status-bot to status service', async () => {
      const interaction = buildMockInteraction({ customId: 'nav:status-bot' });

      await handleNavInteraction(interaction);

      expect(interaction.deferReply).toHaveBeenCalledTimes(1);
      expect(mockStatusExecute).toHaveBeenCalledWith(5);
      expect(mockGetScoringStatus).toHaveBeenCalledTimes(1);
      expect(mockFormatStatusSuccessV2).toHaveBeenCalled();
      expect(interaction.editReply).toHaveBeenCalledTimes(1);
    });

    it('should dispatch list:requests to list requests service', async () => {
      const interaction = buildMockInteraction({ customId: 'nav:list:requests' });

      await handleNavInteraction(interaction);

      expect(interaction.deferReply).toHaveBeenCalledTimes(1);
      expect(mockListRequestsExecute).toHaveBeenCalledWith(
        expect.objectContaining({
          userId: 'user-123',
          page: 1,
          size: 4,
        })
      );
      expect(interaction.editReply).toHaveBeenCalledTimes(1);
    });

    it('should dispatch list:notes with deferReply and editReply', async () => {
      const interaction = buildMockInteraction({ customId: 'nav:list:notes' });

      await handleNavInteraction(interaction);

      expect(interaction.deferReply).toHaveBeenCalledTimes(1);
      expect(interaction.editReply).toHaveBeenCalledTimes(1);
    });

    it('should show redirect message for note:write', async () => {
      const interaction = buildMockInteraction({ customId: 'nav:note:write' });

      await handleNavInteraction(interaction);

      expect(interaction.deferReply).toHaveBeenCalledTimes(1);
      expect(interaction.editReply).toHaveBeenCalledTimes(1);
      const editCall = (interaction.editReply as any).mock.calls[0][0] as Record<string, any>;
      expect(editCall.content).toContain('/note write');
    });

    it('should show redirect message for vibecheck:scan', async () => {
      const interaction = buildMockInteraction({ customId: 'nav:vibecheck:scan' });

      await handleNavInteraction(interaction);

      expect(interaction.deferReply).toHaveBeenCalledTimes(1);
      expect(interaction.editReply).toHaveBeenCalledTimes(1);
      const editCall = (interaction.editReply as any).mock.calls[0][0] as Record<string, any>;
      expect(editCall.content).toContain('/vibecheck scan');
    });

    it('should show redirect for contextual actions without context', async () => {
      const contextualActions = [
        { action: 'note:rate', command: '/note rate' },
        { action: 'note:view', command: '/note view' },
        { action: 'note:request', command: '/note request' },
        { action: 'note:score', command: '/note score' },
        { action: 'vibecheck:status', command: '/vibecheck' },
        { action: 'vibecheck:create-requests', command: '/vibecheck' },
        { action: 'clear:notes', command: '/clear' },
        { action: 'clear:requests', command: '/clear' },
        { action: 'config', command: '/config' },
        { action: 'note-request-context', command: 'Apps' },
      ];

      for (const { action, command } of contextualActions) {
        jest.clearAllMocks();
        const interaction = buildMockInteraction({ customId: `nav:${action}` });

        await handleNavInteraction(interaction);

        expect(interaction.deferReply).toHaveBeenCalledTimes(1);
        expect(interaction.editReply).toHaveBeenCalledTimes(1);
        const editCall = (interaction.editReply as any).mock.calls[0][0] as Record<string, any>;
        expect(editCall.content).toContain(command);
      }
    });

    it('should fall back to hub for completely unknown actions', async () => {
      const interaction = buildMockInteraction({ customId: 'nav:unknown:action' });

      await handleNavInteraction(interaction);

      expect(interaction.update).toHaveBeenCalledTimes(1);
      expect(interaction.deferReply).not.toHaveBeenCalled();
    });

    it('should handle status service errors gracefully', async () => {
      mockStatusExecute.mockResolvedValueOnce({
        success: false,
        error: { code: 'API_ERROR', message: 'Service unavailable' },
      });

      const interaction = buildMockInteraction({ customId: 'nav:status-bot' });

      await handleNavInteraction(interaction);

      expect(interaction.deferReply).toHaveBeenCalledTimes(1);
      expect(mockFormatErrorV2).toHaveBeenCalled();
      expect(interaction.editReply).toHaveBeenCalledTimes(1);
    });

    it('should handle list requests service errors gracefully', async () => {
      mockListRequestsExecute.mockResolvedValueOnce({
        success: false,
        error: { code: 'API_ERROR', message: 'Service unavailable' },
      });

      const interaction = buildMockInteraction({ customId: 'nav:list:requests' });

      await handleNavInteraction(interaction);

      expect(interaction.deferReply).toHaveBeenCalledTimes(1);
      expect(mockFormatErrorV2).toHaveBeenCalled();
      expect(interaction.editReply).toHaveBeenCalledTimes(1);
    });

    it('should add scoring status to status-bot when available', async () => {
      const interaction = buildMockInteraction({ customId: 'nav:status-bot' });

      await handleNavInteraction(interaction);

      expect(mockGetScoringStatus).toHaveBeenCalledTimes(1);
      expect(mockFormatScoringStatusV2).toHaveBeenCalled();
    });

    it('should not add scoring section when scoring status fails', async () => {
      mockGetScoringStatus.mockResolvedValueOnce({
        success: false,
        error: { code: 'API_ERROR', message: 'Failed' },
      });

      const interaction = buildMockInteraction({ customId: 'nav:status-bot' });

      await handleNavInteraction(interaction);

      expect(mockFormatScoringStatusV2).not.toHaveBeenCalled();
    });
  });
});
