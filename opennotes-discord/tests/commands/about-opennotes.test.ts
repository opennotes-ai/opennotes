import { jest } from '@jest/globals';
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
  ApiError: class ApiError extends Error {
    constructor(message: string, public endpoint?: string, public statusCode?: number, public responseBody?: any) {
      super(message);
    }
  },
}));

const { execute, data } = await import('../../src/commands/about-opennotes.js');
const { v2MessageFlags, V2_COLORS } = await import('../../src/utils/v2-components.js');

describe('about-opennotes command', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('command data', () => {
    it('should have correct name and description', () => {
      expect(data.name).toBe('about-opennotes');
      expect(data.description).toBe('Learn about Open Notes and how it works');
    });
  });

  describe('successful execution', () => {
    it('should send Components v2 container about OpenNotes', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      expect(mockInteraction.deferReply).toHaveBeenCalledWith({
        flags: v2MessageFlags({ ephemeral: true }),
      });

      const editReplyCall = mockInteraction.editReply.mock.calls[0][0];

      expect(editReplyCall).not.toHaveProperty('embeds');
      expect(editReplyCall).toHaveProperty('components');
      expect(editReplyCall.components).toHaveLength(1);

      const containerBuilder = editReplyCall.components[0];
      expect(containerBuilder).toBeInstanceOf(ContainerBuilder);

      const container = containerBuilder.toJSON();
      expect(container.type).toBe(17);
      expect(container.accent_color).toBe(V2_COLORS.PRIMARY);
    });

    it('should include all required information sections in container', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      const editReplyCall = mockInteraction.editReply.mock.calls[0][0];
      const containerBuilder = editReplyCall.components[0];
      const container = containerBuilder.toJSON();
      const allContent = JSON.stringify(container.components);

      expect(allContent).toContain('How It Works');
      expect(allContent).toContain('Note Submission');
      expect(allContent).toContain('Commands');
      expect(allContent).toContain('Scoring System');
      expect(allContent).toContain('Community Moderation');
    });

    it('should include title and description in container', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      const editReplyCall = mockInteraction.editReply.mock.calls[0][0];
      const containerBuilder = editReplyCall.components[0];
      const container = containerBuilder.toJSON();
      const allContent = JSON.stringify(container.components);

      expect(allContent).toContain('About OpenNotes');
      expect(allContent).toContain('community moderation tool');
    });

    it('should mention note submission commands', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      const editReplyCall = mockInteraction.editReply.mock.calls[0][0];
      const containerBuilder = editReplyCall.components[0];
      const container = containerBuilder.toJSON();
      const allContent = JSON.stringify(container.components);

      expect(allContent).toContain('/note write');
    });

    it('should mention scoring system', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      const editReplyCall = mockInteraction.editReply.mock.calls[0][0];
      const containerBuilder = editReplyCall.components[0];
      const container = containerBuilder.toJSON();
      const allContent = JSON.stringify(container.components);

      expect(allContent).toContain('rate notes');
    });

    it('should mention community moderation features', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      const editReplyCall = mockInteraction.editReply.mock.calls[0][0];
      const containerBuilder = editReplyCall.components[0];
      const container = containerBuilder.toJSON();
      const allContent = JSON.stringify(container.components);

      expect(allContent).toContain('self-moderate');
    });

    it('should include footer text', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      const editReplyCall = mockInteraction.editReply.mock.calls[0][0];
      const containerBuilder = editReplyCall.components[0];
      const container = containerBuilder.toJSON();
      const allContent = JSON.stringify(container.components);

      expect(allContent).toContain('Community-powered context');
    });

    it('should use separators between sections', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      const editReplyCall = mockInteraction.editReply.mock.calls[0][0];
      const containerBuilder = editReplyCall.components[0];
      const container = containerBuilder.toJSON();

      const separators = container.components.filter((c: any) => c.type === 14);
      expect(separators.length).toBeGreaterThan(0);
    });

    it('should use TextDisplayBuilder components for information sections', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      const editReplyCall = mockInteraction.editReply.mock.calls[0][0];
      const containerBuilder = editReplyCall.components[0];
      const container = containerBuilder.toJSON();

      const textDisplays = container.components.filter((c: any) => c.type === 10);
      expect(textDisplays.length).toBeGreaterThanOrEqual(5);
    });
  });

  describe('Components v2 flags', () => {
    it('should use v2MessageFlags with ephemeral option', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      const deferReplyCall = mockInteraction.deferReply.mock.calls[0][0];
      const expectedFlags = v2MessageFlags({ ephemeral: true });

      expect(deferReplyCall.flags & MessageFlags.IsComponentsV2).toBeTruthy();
      expect(deferReplyCall.flags & MessageFlags.Ephemeral).toBeTruthy();
      expect(deferReplyCall.flags).toBe(expectedFlags);
    });
  });

  describe('error handling', () => {
    it('should handle unexpected errors gracefully', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockRejectedValue(new Error('Network error')),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      expect(mockLogger.error).toHaveBeenCalledWith(
        'Unexpected error in about-opennotes command',
        expect.objectContaining({
          error_id: 'test-error-id',
          command: 'about-opennotes',
          user_id: 'user123',
          error: 'Network error',
        })
      );

      expect(mockInteraction.editReply).toHaveBeenCalledWith({
        content: expect.stringContaining('Failed to display information about OpenNotes'),
      });
    });
  });

  describe('logging', () => {
    it('should log command execution start', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      expect(mockLogger.info).toHaveBeenCalledWith(
        'Executing about-opennotes command',
        expect.objectContaining({
          error_id: 'test-error-id',
          command: 'about-opennotes',
          user_id: 'user123',
          guild_id: 'guild456',
        })
      );
    });

    it('should log successful completion', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      expect(mockLogger.info).toHaveBeenCalledWith(
        'About command completed successfully',
        expect.objectContaining({
          error_id: 'test-error-id',
          command: 'about-opennotes',
          user_id: 'user123',
        })
      );
    });
  });
});
