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

const { handleNavInteraction } = await import('../../src/handlers/navigation-handler.js');

function buildMockInteraction(overrides: Record<string, any> = {}): ButtonInteraction {
  return {
    customId: 'nav:menu',
    user: { id: 'user-123' },
    message: {
      id: 'msg-456',
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
    isButton: () => true,
    ...overrides,
  } as unknown as ButtonInteraction;
}

describe('navigation-handler', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockCacheGet.mockResolvedValue(null);
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

  describe('nav:{action} routes', () => {
    it('should show the full hub for unrecognized nav actions', async () => {
      const interaction = buildMockInteraction({ customId: 'nav:list:notes' });

      await handleNavInteraction(interaction);

      expect(interaction.update).toHaveBeenCalledTimes(1);
      const updateCall = (interaction.update as any).mock.calls[0][0] as Record<string, any>;
      expect(updateCall).toHaveProperty('components');
    });
  });
});
