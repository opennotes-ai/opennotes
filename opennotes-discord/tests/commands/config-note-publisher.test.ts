import { jest } from '@jest/globals';

const mockLogger = {
  info: jest.fn<(...args: unknown[]) => void>(),
  error: jest.fn<(...args: unknown[]) => void>(),
  warn: jest.fn<(...args: unknown[]) => void>(),
};

const mockNotePublisherConfigService = {
  setConfig: jest.fn<(...args: any[]) => Promise<void>>(),
  setThreshold: jest.fn<(...args: any[]) => Promise<void>>(),
  enableChannel: jest.fn<(...args: any[]) => Promise<void>>(),
  disableChannel: jest.fn<(...args: any[]) => Promise<void>>(),
  getConfig: jest.fn<(...args: any[]) => Promise<any>>(),
  getDefaultThreshold: jest.fn<() => number>().mockReturnValue(0.7),
};

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
}));

jest.unstable_mockModule('../../src/services/NotePublisherConfigService.js', () => ({
  NotePublisherConfigService: jest.fn(() => mockNotePublisherConfigService),
}));

const { execute } = await import('../../src/commands/config.js');

describe('config-note-publisher command', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('enable subcommand', () => {
    it('should enable auto-posting', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('note-publisher'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('enable'),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      mockNotePublisherConfigService.setConfig.mockResolvedValue(undefined);

      await execute(mockInteraction as any);

      expect(mockNotePublisherConfigService.setConfig).toHaveBeenCalledWith(
        'guild456',
        true,
        undefined,
        undefined,
        'user123'
      );
      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('Note publishering enabled'),
        })
      );
    });
  });

  describe('disable subcommand', () => {
    it('should disable auto-posting', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('note-publisher'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('disable'),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      mockNotePublisherConfigService.setConfig.mockResolvedValue(undefined);

      await execute(mockInteraction as any);

      expect(mockNotePublisherConfigService.setConfig).toHaveBeenCalledWith(
        'guild456',
        false,
        undefined,
        undefined,
        'user123'
      );
      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('Note publishering disabled'),
        })
      );
    });
  });

  describe('threshold subcommand', () => {
    it('should set threshold value', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('note-publisher'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('threshold'),
          getNumber: jest.fn<() => number>().mockReturnValue(0.8),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      mockNotePublisherConfigService.setThreshold.mockResolvedValue(undefined);

      await execute(mockInteraction as any);

      expect(mockNotePublisherConfigService.setThreshold).toHaveBeenCalledWith(
        'guild456',
        0.8,
        undefined,
        'user123'
      );
      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringMatching(/Threshold updated.*80%/),
        })
      );
    });
  });

  describe('enable-channel subcommand', () => {
    it('should enable auto-posting in specific channel', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('note-publisher'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('enable-channel'),
          getChannel: jest.fn<() => any>().mockReturnValue({ id: 'channel789' }),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      mockNotePublisherConfigService.enableChannel.mockResolvedValue(undefined);

      await execute(mockInteraction as any);

      expect(mockNotePublisherConfigService.enableChannel).toHaveBeenCalledWith(
        'guild456',
        'channel789',
        'user123'
      );
      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('Note publishering enabled'),
        })
      );
    });

    it('should handle invalid channel', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('note-publisher'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('enable-channel'),
          getChannel: jest.fn<() => any>().mockReturnValue({ id: null }),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      expect(mockNotePublisherConfigService.enableChannel).not.toHaveBeenCalled();
      expect(mockInteraction.editReply).toHaveBeenCalledWith({ content: '❌ Invalid channel' });
    });
  });

  describe('disable-channel subcommand', () => {
    it('should disable auto-posting in specific channel', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('note-publisher'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('disable-channel'),
          getChannel: jest.fn<() => any>().mockReturnValue({ id: 'channel789' }),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      mockNotePublisherConfigService.disableChannel.mockResolvedValue(undefined);

      await execute(mockInteraction as any);

      expect(mockNotePublisherConfigService.disableChannel).toHaveBeenCalledWith(
        'guild456',
        'channel789',
        'user123'
      );
      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('Note publishering disabled'),
        })
      );
    });
  });

  describe('status subcommand', () => {
    it('should show server-wide status', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('note-publisher'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('status'),
          getChannel: jest.fn<() => any>().mockReturnValue(null),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      mockNotePublisherConfigService.getConfig.mockResolvedValue({
        enabled: true,
        threshold: 0.75,
      });

      await execute(mockInteraction as any);

      expect(mockNotePublisherConfigService.getConfig).toHaveBeenCalledWith('guild456', undefined);
      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringMatching(/Auto-Post Configuration.*Enabled.*75%/s),
        })
      );
    });

    it('should show channel-specific status', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('note-publisher'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('status'),
          getChannel: jest.fn<() => any>().mockReturnValue({ id: 'channel789' }),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      mockNotePublisherConfigService.getConfig.mockResolvedValue({
        enabled: false,
        threshold: 0.7,
      });

      await execute(mockInteraction as any);

      expect(mockNotePublisherConfigService.getConfig).toHaveBeenCalledWith('guild456', 'channel789');
      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringMatching(/Disabled/),
        })
      );
    });
  });

  describe('error handling', () => {
    it('should handle missing guildId', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: null,
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('note-publisher'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('enable'),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>(),
        reply: jest.fn<(opts: any) => Promise<any>>(),
      };

      await execute(mockInteraction as any);

      expect(mockInteraction.editReply).toHaveBeenCalledWith({
        content: 'This command can only be used in a server.',
      });
    });

    it('should handle service errors', async () => {
      mockNotePublisherConfigService.setConfig.mockRejectedValue(new Error('API error'));

      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('note-publisher'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('enable'),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
        deferred: true,
      };

      await execute(mockInteraction as any);

      expect(mockLogger.error).toHaveBeenCalled();
      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('Error ID'),
        })
      );
    });

    it('should handle unknown subcommand', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('note-publisher'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('unknown'),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      expect(mockInteraction.editReply).toHaveBeenCalledWith({
        content: 'Unknown subcommand.',
      });
    });
  });

  describe('ephemeral responses', () => {
    it('should use ephemeral flags', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('note-publisher'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('enable'),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<any>>().mockResolvedValue({}),
      };

      await execute(mockInteraction as any);

      expect(mockInteraction.deferReply).toHaveBeenCalledWith({ flags: 64 });
    });
  });
});
