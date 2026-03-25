import { jest, describe, it, expect, beforeEach } from '@jest/globals';
import { MessageFlags, ContainerBuilder } from 'discord.js';
import { loggerFactory } from '../factories/index.js';

const mockLogger = loggerFactory.build();

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
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

const { execute, data } = await import('../../src/commands/open-notes.js');
const { v2MessageFlags, V2_COLORS } = await import('../../src/utils/v2-components.js');
const { HUB_ACTIONS } = await import('../../src/lib/navigation-components.js');

describe('open-notes command', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('command data', () => {
    it('should have correct name and description', () => {
      expect(data.name).toBe('open-notes');
      expect(data.description).toBeTruthy();
    });
  });

  describe('successful execution', () => {
    it('should reply with a v2 container with PRIMARY accent color', async () => {
      const mockInteraction = {
        user: { id: 'user-123' },
        guildId: 'guild-456',
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      expect(mockInteraction.reply).toHaveBeenCalledTimes(1);
      const replyCall = mockInteraction.reply.mock.calls[0][0];

      expect(replyCall).toHaveProperty('components');
      expect(replyCall.components).toHaveLength(1);

      const containerBuilder = replyCall.components[0];
      expect(containerBuilder).toBeInstanceOf(ContainerBuilder);

      const container = containerBuilder.toJSON();
      expect(container.type).toBe(17);
      expect(container.accent_color).toBe(V2_COLORS.PRIMARY);
    });

    it('should use ephemeral v2 message flags', async () => {
      const mockInteraction = {
        user: { id: 'user-123' },
        guildId: 'guild-456',
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      const replyCall = mockInteraction.reply.mock.calls[0][0];
      const expectedFlags = v2MessageFlags({ ephemeral: true });

      expect(replyCall.flags & MessageFlags.IsComponentsV2).toBeTruthy();
      expect(replyCall.flags & MessageFlags.Ephemeral).toBeTruthy();
      expect(replyCall.flags).toBe(expectedFlags);
    });

    it('should contain Navigation header text', async () => {
      const mockInteraction = {
        user: { id: 'user-123' },
        guildId: 'guild-456',
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      const replyCall = mockInteraction.reply.mock.calls[0][0];
      const container = replyCall.components[0].toJSON();
      const allContent = JSON.stringify(container.components);

      expect(allContent).toContain('Navigation');
    });

    it('should contain action rows with hub buttons', async () => {
      const mockInteraction = {
        user: { id: 'user-123' },
        guildId: 'guild-456',
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      const replyCall = mockInteraction.reply.mock.calls[0][0];
      const container = replyCall.components[0].toJSON();

      const actionRows = container.components.filter((c: any) => c.type === 1);
      expect(actionRows.length).toBeGreaterThan(0);

      const allButtonLabels = actionRows.flatMap((row: any) =>
        row.components.map((btn: any) => btn.label)
      );
      for (const action of HUB_ACTIONS) {
        expect(allButtonLabels).toContain(action.label);
      }
    });

    it('should contain a divider between text and action rows', async () => {
      const mockInteraction = {
        user: { id: 'user-123' },
        guildId: 'guild-456',
        reply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      const replyCall = mockInteraction.reply.mock.calls[0][0];
      const container = replyCall.components[0].toJSON();

      const separators = container.components.filter((c: any) => c.type === 14);
      expect(separators.length).toBeGreaterThan(0);
    });
  });

  describe('error handling', () => {
    it('should handle reply errors gracefully', async () => {
      const mockInteraction = {
        user: { id: 'user-123' },
        guildId: 'guild-456',
        reply: jest.fn<(opts: any) => Promise<any>>().mockRejectedValue(new Error('Network error')),
        replied: false,
        deferred: false,
        followUp: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      expect(mockLogger.error).toHaveBeenCalled();
    });
  });
});
