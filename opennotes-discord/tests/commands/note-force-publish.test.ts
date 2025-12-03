import { jest } from '@jest/globals';
import { MessageFlags } from 'discord.js';
import { createMockLogger } from '../utils/service-mocks.js';

const mockLogger = createMockLogger();

const mockApiClient = {
  forcePublishNote: jest.fn<(noteId: string, userContext?: any) => Promise<any>>(),
  healthCheck: jest.fn<() => Promise<any>>(),
};

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
}));

jest.unstable_mockModule('../../src/api-client.js', () => ({
  apiClient: mockApiClient,
}));

jest.unstable_mockModule('../../src/lib/user-context.js', () => ({
  extractUserContext: () => ({
    userId: 'test-user-id',
    username: 'testuser',
    displayName: 'Test User',
    avatarUrl: 'https://example.com/avatar.png',
    guildId: 'test-guild-id',
  }),
}));

class MockApiError extends Error {
  statusCode?: number;
  endpoint?: string;
  responseBody?: any;

  constructor(message: string, endpoint?: string, statusCode?: number, responseBody?: any) {
    super(message);
    this.endpoint = endpoint;
    this.statusCode = statusCode;
    this.responseBody = responseBody;
  }
}

jest.unstable_mockModule('../../src/lib/errors.js', () => ({
  generateErrorId: () => 'test-error-id',
  extractErrorDetails: (error: any) => ({
    message: error?.message || 'Unknown error',
    type: error?.constructor?.name || 'Error',
    stack: error?.stack || '',
  }),
  formatErrorForUser: (errorId: string, message: string) => `${message} (Error ID: ${errorId})`,
  ApiError: MockApiError,
}));

const { execute } = await import('../../src/commands/note.js');

const TEST_UUID = '550e8400-e29b-41d4-a716-446655440000';

describe('note-force-publish command', () => {
  let mockInteraction: any;

  beforeEach(() => {
    jest.clearAllMocks();

    mockInteraction = {
      options: {
        getSubcommand: jest.fn<() => string>().mockReturnValue('force-publish'),
        getString: jest.fn<(name: string) => string | null>().mockReturnValue(TEST_UUID),
      },
      user: { id: 'test-user-id' },
      guildId: 'test-guild-id',
      member: {
        permissions: {
          has: jest.fn<(permission: any) => boolean>().mockReturnValue(true),
        },
      },
      reply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
      deferReply: jest.fn<(opts?: any) => Promise<void>>().mockResolvedValue(undefined),
      editReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
      followUp: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
      deleteReply: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
    };
  });

  describe('successful execution', () => {
    it('should force-publish a note successfully', async () => {
      const mockNote = {
        id: TEST_UUID,
        note_id: TEST_UUID,
        summary: 'This is a test note',
        status: 'PUBLISHED',
        force_published: true,
        force_published_at: new Date().toISOString(),
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };

      mockApiClient.forcePublishNote.mockResolvedValue(mockNote);

      await execute(mockInteraction);

      expect(mockInteraction.deferReply).toHaveBeenCalledWith({ flags: MessageFlags.Ephemeral });
      expect(mockApiClient.forcePublishNote).toHaveBeenCalledWith(TEST_UUID, expect.any(Object));
      expect(mockInteraction.editReply).toHaveBeenCalled();

      const editReplyCall = mockInteraction.editReply.mock.calls[0][0];
      expect(editReplyCall.content).toContain(`Note #${TEST_UUID} has been force-published`);
      expect(editReplyCall.content).toContain('Admin Published');
    });
  });

  describe('validation', () => {
    it('should reject invalid note ID', async () => {
      mockInteraction.options.getString.mockReturnValue('invalid');

      await execute(mockInteraction);

      expect(mockInteraction.reply).toHaveBeenCalledWith({
        content: expect.stringContaining('Invalid note ID'),
        flags: MessageFlags.Ephemeral,
      });
      expect(mockApiClient.forcePublishNote).not.toHaveBeenCalled();
    });

    it('should reject numeric note ID (legacy format)', async () => {
      mockInteraction.options.getString.mockReturnValue('12345');

      await execute(mockInteraction);

      expect(mockInteraction.reply).toHaveBeenCalledWith({
        content: expect.stringContaining('Note ID must be a valid UUID format'),
        flags: MessageFlags.Ephemeral,
      });
      expect(mockApiClient.forcePublishNote).not.toHaveBeenCalled();
    });

    it('should reject if not in a guild', async () => {
      mockInteraction.guildId = null;

      await execute(mockInteraction);

      expect(mockInteraction.reply).toHaveBeenCalledWith({
        content: 'This command can only be used in a server.',
        flags: MessageFlags.Ephemeral,
      });
      expect(mockApiClient.forcePublishNote).not.toHaveBeenCalled();
    });
  });

  describe('error handling', () => {
    it('should handle 403 permission denied', async () => {
      const error = new MockApiError(
        'Forbidden',
        `/api/v1/notes/${TEST_UUID}/force-publish`,
        403
      );
      mockApiClient.forcePublishNote.mockRejectedValue(error);

      await execute(mockInteraction);

      expect(mockInteraction.editReply).toHaveBeenCalled();
      const editReplyCall = mockInteraction.editReply.mock.calls[0][0];
      expect(editReplyCall.content).toContain('Permission Denied');
      expect(editReplyCall.content).toContain('Manage Server');
    });

    it('should handle 404 note not found', async () => {
      const nonExistentUuid = '00000000-0000-0000-0000-000000000000';
      mockInteraction.options.getString.mockReturnValue(nonExistentUuid);
      const error = new MockApiError(
        'Not Found',
        `/api/v1/notes/${nonExistentUuid}/force-publish`,
        404
      );
      mockApiClient.forcePublishNote.mockRejectedValue(error);

      await execute(mockInteraction);

      expect(mockInteraction.editReply).toHaveBeenCalled();
      const editReplyCall = mockInteraction.editReply.mock.calls[0][0];
      expect(editReplyCall.content).toContain('Note Not Found');
    });

    it('should handle 400 invalid request', async () => {
      const error = new MockApiError(
        'Bad Request',
        `/api/v1/notes/${TEST_UUID}/force-publish`,
        400,
        {
          detail: 'Note already published',
        }
      );
      mockApiClient.forcePublishNote.mockRejectedValue(error);

      await execute(mockInteraction);

      expect(mockInteraction.editReply).toHaveBeenCalled();
      const editReplyCall = mockInteraction.editReply.mock.calls[0][0];
      expect(editReplyCall.content).toContain('Invalid Request');
      expect(editReplyCall.content).toContain('Note already published');
    });

    it('should handle generic errors', async () => {
      mockApiClient.forcePublishNote.mockRejectedValue(new Error('Network error'));

      await execute(mockInteraction);

      expect(mockInteraction.editReply).toHaveBeenCalled();
      const editReplyCall = mockInteraction.editReply.mock.calls[0][0];
      expect(editReplyCall.content).toContain('Error ID');
    });
  });
});
