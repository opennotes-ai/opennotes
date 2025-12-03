import { jest } from '@jest/globals';
import { MessageFlags } from 'discord.js';
import { createMockLogger } from '../utils/service-mocks.js';

const mockLogger = createMockLogger();

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
    it('should send informative embed about OpenNotes', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      expect(mockInteraction.deferReply).toHaveBeenCalledWith({
        flags: MessageFlags.Ephemeral,
      });

      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          embeds: expect.arrayContaining([
            expect.objectContaining({
              data: expect.objectContaining({
                title: 'About OpenNotes',
                description: expect.stringContaining('community moderation tool'),
              }),
            }),
          ]),
        })
      );
    });

    it('should include all required information sections', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      const editReplyCall = mockInteraction.editReply.mock.calls[0][0];
      const embed = editReplyCall.embeds[0];
      const fieldNames = embed.data.fields.map((f: any) => f.name);

      expect(fieldNames).toContain('📝 How It Works');
      expect(fieldNames).toContain('⭐ Note Submission');
      expect(fieldNames).toContain('🎯 Scoring System');
      expect(fieldNames).toContain('🛡️ Community Moderation');
    });

    it('should mention note submission in the content', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      const editReplyCall = mockInteraction.editReply.mock.calls[0][0];
      const embed = editReplyCall.embeds[0];
      const fields = embed.data.fields;

      const noteSubmissionField = fields.find((f: any) => f.name === '⭐ Note Submission');
      expect(noteSubmissionField).toBeDefined();
      expect(noteSubmissionField.value).toContain('/note write');
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
      const embed = editReplyCall.embeds[0];
      const fields = embed.data.fields;

      const scoringField = fields.find((f: any) => f.name === '🎯 Scoring System');
      expect(scoringField).toBeDefined();
      expect(scoringField.value).toContain('rate notes');
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
      const embed = editReplyCall.embeds[0];
      const fields = embed.data.fields;

      const moderationField = fields.find((f: any) => f.name === '🛡️ Community Moderation');
      expect(moderationField).toBeDefined();
      expect(moderationField.value).toContain('self-moderate');
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
          community_server_id: 'guild456',
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
