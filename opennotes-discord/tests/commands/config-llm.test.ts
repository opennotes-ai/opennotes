import { jest } from '@jest/globals';
import { MessageFlags } from 'discord.js';
import { ApiError } from '../../src/lib/errors.js';

const mockLogger = {
  info: jest.fn<(...args: unknown[]) => void>(),
  error: jest.fn<(...args: unknown[]) => void>(),
  warn: jest.fn<(...args: unknown[]) => void>(),
  debug: jest.fn<(...args: unknown[]) => void>(),
};

const mockApiClient = {
  createLLMConfig: jest.fn<(...args: any[]) => Promise<any>>(),
};

const mockResolveCommunityServerId = jest.fn<(guildId: string) => Promise<string>>();

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
}));

jest.unstable_mockModule('../../src/api-client.js', () => ({
  apiClient: mockApiClient,
}));

jest.unstable_mockModule('../../src/lib/community-server-resolver.js', () => ({
  resolveCommunityServerId: mockResolveCommunityServerId,
}));

const { execute } = await import('../../src/commands/config.js');

describe('config-llm command', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockResolveCommunityServerId.mockImplementation(async (guildId: string) => `uuid-for-${guildId}`);
  });

  describe('successful configuration', () => {
    it('should configure OpenAI API key successfully', async () => {
      const mockConfig = {
        id: 1,
        community_server_id: 'guild456',
        provider: 'openai',
        enabled: true,
        created_at: new Date().toISOString(),
      };

      mockApiClient.createLLMConfig.mockResolvedValue(mockConfig);

      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('llm'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('set'),
          getString: jest.fn<(name: string, required?: boolean) => string | null>((name: string) => {
            if (name === 'provider') return 'openai';
            if (name === 'api_key') return 'sk-test1234567890abcdef';
            return null;
          }),
          getBoolean: jest.fn<(name: string) => boolean | null>().mockReturnValue(null),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      await execute(mockInteraction as any);

      expect(mockResolveCommunityServerId).toHaveBeenCalledWith('guild456');
      expect(mockApiClient.createLLMConfig).toHaveBeenCalledWith('uuid-for-guild456', {
        provider: 'openai',
        api_key: 'sk-test1234567890abcdef',
        enabled: true,
      });
      const v2EphemeralFlags = MessageFlags.Ephemeral | MessageFlags.IsComponentsV2;
      expect(mockInteraction.deferReply).toHaveBeenCalledWith({ flags: v2EphemeralFlags });
      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('OpenAI API Key Configured Successfully'),
        })
      );
    });

    it('should configure Anthropic API key successfully', async () => {
      const mockConfig = {
        id: 2,
        community_server_id: 'guild789',
        provider: 'anthropic',
        enabled: true,
        created_at: new Date().toISOString(),
      };

      mockApiClient.createLLMConfig.mockResolvedValue(mockConfig);

      const mockInteraction = {
        user: { id: 'user456' },
        guildId: 'guild789',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('llm'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('set'),
          getString: jest.fn<(name: string, required?: boolean) => string | null>((name: string) => {
            if (name === 'provider') return 'anthropic';
            if (name === 'api_key') return 'sk-ant-test1234567890abcdef';
            return null;
          }),
          getBoolean: jest.fn<(name: string) => boolean | null>().mockReturnValue(null),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      await execute(mockInteraction as any);

      expect(mockResolveCommunityServerId).toHaveBeenCalledWith('guild789');
      expect(mockApiClient.createLLMConfig).toHaveBeenCalledWith('uuid-for-guild789', {
        provider: 'anthropic',
        api_key: 'sk-ant-test1234567890abcdef',
        enabled: true,
      });
      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('Anthropic API Key Configured Successfully'),
        })
      );
    });

    it('should show security message after successful configuration', async () => {
      const mockConfig = {
        id: 1,
        community_server_id: 'guild456',
        provider: 'openai',
        enabled: true,
        created_at: new Date().toISOString(),
      };

      mockApiClient.createLLMConfig.mockResolvedValue(mockConfig);

      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('llm'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('set'),
          getString: jest.fn<(name: string, required?: boolean) => string | null>((name: string) => {
            if (name === 'provider') return 'openai';
            if (name === 'api_key') return 'sk-valid-key';
            return null;
          }),
          getBoolean: jest.fn<(name: string) => boolean | null>().mockReturnValue(null),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      await execute(mockInteraction as any);

      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('encrypted'),
        })
      );
    });
  });

  describe('validation', () => {
    it('should reject OpenAI API key not starting with sk-', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('llm'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('set'),
          getString: jest.fn<(name: string, required?: boolean) => string | null>((name: string) => {
            if (name === 'provider') return 'openai';
            if (name === 'api_key') return 'invalid-key-format';
            return null;
          }),
          getBoolean: jest.fn<(name: string) => boolean | null>().mockReturnValue(null),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      await execute(mockInteraction as any);

      expect(mockApiClient.createLLMConfig).not.toHaveBeenCalled();
      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('Invalid OpenAI API key format'),
        })
      );
    });

    it('should reject Anthropic API key not starting with sk-ant-', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('llm'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('set'),
          getString: jest.fn<(name: string, required?: boolean) => string | null>((name: string) => {
            if (name === 'provider') return 'anthropic';
            if (name === 'api_key') return 'sk-invalid-key';
            return null;
          }),
          getBoolean: jest.fn<(name: string) => boolean | null>().mockReturnValue(null),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      await execute(mockInteraction as any);

      expect(mockApiClient.createLLMConfig).not.toHaveBeenCalled();
      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('Invalid Anthropic API key format'),
        })
      );
    });

    it('should handle missing guildId', async () => {
      const mockInteraction = {
        user: { id: 'user123' },
        guildId: null,
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('llm'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('set'),
          getString: jest.fn<(name: string, required?: boolean) => string | null>(),
          getBoolean: jest.fn<(name: string) => boolean | null>(),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      await execute(mockInteraction as any);

      expect(mockApiClient.createLLMConfig).not.toHaveBeenCalled();
      expect(mockInteraction.editReply).toHaveBeenCalledWith({
        content: 'This command can only be used in a server.',
      });
    });
  });

  describe('server-side API key validation', () => {
    it('should pass correctly formatted key to server for validation', async () => {
      const mockConfig = {
        id: 1,
        community_server_id: 'guild456',
        provider: 'openai',
        enabled: true,
        created_at: new Date().toISOString(),
      };

      mockApiClient.createLLMConfig.mockResolvedValue(mockConfig);

      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('llm'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('set'),
          getString: jest.fn<(name: string, required?: boolean) => string | null>((name: string) => {
            if (name === 'provider') return 'openai';
            if (name === 'api_key') return 'sk-valid-format-key-1234567890';
            return null;
          }),
          getBoolean: jest.fn<(name: string) => boolean | null>().mockReturnValue(null),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      await execute(mockInteraction as any);

      expect(mockResolveCommunityServerId).toHaveBeenCalledWith('guild456');
      expect(mockApiClient.createLLMConfig).toHaveBeenCalledWith('uuid-for-guild456', {
        provider: 'openai',
        api_key: 'sk-valid-format-key-1234567890',
        enabled: true,
      });
    });

    it('should display server validation error when API key is invalid despite correct format', async () => {
      const apiError = new ApiError(
        'Bad Request',
        '/api/v1/community-servers/guild456/llm-config',
        400,
        { detail: 'The provided API key is invalid' },
        undefined
      );

      mockApiClient.createLLMConfig.mockRejectedValue(apiError);

      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('llm'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('set'),
          getString: jest.fn<(name: string, required?: boolean) => string | null>((name: string) => {
            if (name === 'provider') return 'openai';
            if (name === 'api_key') return 'sk-looks-valid-but-is-not-real';
            return null;
          }),
          getBoolean: jest.fn<(name: string) => boolean | null>().mockReturnValue(null),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      await execute(mockInteraction as any);

      expect(mockApiClient.createLLMConfig).toHaveBeenCalled();
      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('Invalid API key format or configuration'),
        })
      );
    });

    it('should display server validation error for Anthropic key that fails API validation', async () => {
      const apiError = new ApiError(
        'Bad Request',
        '/api/v1/community-servers/guild789/llm-config',
        400,
        { detail: 'The provided API key is invalid' },
        undefined
      );

      mockApiClient.createLLMConfig.mockRejectedValue(apiError);

      const mockInteraction = {
        user: { id: 'user456' },
        guildId: 'guild789',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('llm'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('set'),
          getString: jest.fn<(name: string, required?: boolean) => string | null>((name: string) => {
            if (name === 'provider') return 'anthropic';
            if (name === 'api_key') return 'sk-ant-looks-valid-but-revoked';
            return null;
          }),
          getBoolean: jest.fn<(name: string) => boolean | null>().mockReturnValue(null),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      await execute(mockInteraction as any);

      expect(mockResolveCommunityServerId).toHaveBeenCalledWith('guild789');
      expect(mockApiClient.createLLMConfig).toHaveBeenCalledWith('uuid-for-guild789', {
        provider: 'anthropic',
        api_key: 'sk-ant-looks-valid-but-revoked',
        enabled: true,
      });
      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('Invalid API key format or configuration'),
        })
      );
    });

    it('should not store API key when server-side validation fails', async () => {
      const apiError = new ApiError(
        'Bad Request',
        '/api/v1/community-servers/guild456/llm-config',
        400,
        { detail: 'The provided API key is invalid' },
        undefined
      );

      mockApiClient.createLLMConfig.mockRejectedValue(apiError);

      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('llm'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('set'),
          getString: jest.fn<(name: string, required?: boolean) => string | null>((name: string) => {
            if (name === 'provider') return 'openai';
            if (name === 'api_key') return 'sk-expired-or-invalid-key';
            return null;
          }),
          getBoolean: jest.fn<(name: string) => boolean | null>().mockReturnValue(null),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      await execute(mockInteraction as any);

      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.not.stringContaining('Configured Successfully'),
        })
      );
    });
  });

  describe('API error handling', () => {
    it('should handle 409 conflict (already exists)', async () => {
      const apiError = new ApiError(
        'Conflict',
        '/api/v1/community-servers/guild456/llm-config',
        409,
        { detail: 'Configuration already exists' },
        undefined
      );

      mockApiClient.createLLMConfig.mockRejectedValue(apiError);

      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('llm'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('set'),
          getString: jest.fn<(name: string, required?: boolean) => string | null>((name: string) => {
            if (name === 'provider') return 'openai';
            if (name === 'api_key') return 'sk-test-key';
            return null;
          }),
          getBoolean: jest.fn<(name: string) => boolean | null>().mockReturnValue(null),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      await execute(mockInteraction as any);

      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('LLM configuration already exists'),
        })
      );
    });

    it('should handle 400 bad request', async () => {
      const apiError = new ApiError(
        'Bad Request',
        '/api/v1/community-servers/guild456/llm-config',
        400,
        { detail: 'Invalid API key' },
        undefined
      );

      mockApiClient.createLLMConfig.mockRejectedValue(apiError);

      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('llm'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('set'),
          getString: jest.fn<(name: string, required?: boolean) => string | null>((name: string) => {
            if (name === 'provider') return 'openai';
            if (name === 'api_key') return 'sk-invalid';
            return null;
          }),
          getBoolean: jest.fn<(name: string) => boolean | null>().mockReturnValue(null),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      await execute(mockInteraction as any);

      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('Invalid API key format or configuration'),
        })
      );
    });

    it('should handle 403 permission denied', async () => {
      const apiError = new ApiError(
        'Forbidden',
        '/api/v1/community-servers/guild456/llm-config',
        403,
        { detail: 'Permission denied' },
        undefined
      );

      mockApiClient.createLLMConfig.mockRejectedValue(apiError);

      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('llm'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('set'),
          getString: jest.fn<(name: string, required?: boolean) => string | null>((name: string) => {
            if (name === 'provider') return 'anthropic';
            if (name === 'api_key') return 'sk-ant-test-key';
            return null;
          }),
          getBoolean: jest.fn<(name: string) => boolean | null>().mockReturnValue(null),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      await execute(mockInteraction as any);

      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('Manage Server'),
        })
      );
    });

    it('should handle 503 service unavailable', async () => {
      const apiError = new ApiError(
        'Service Unavailable',
        '/api/v1/community-servers/guild456/llm-config',
        503,
        { detail: 'Server unavailable' },
        undefined
      );

      mockApiClient.createLLMConfig.mockRejectedValue(apiError);

      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('llm'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('set'),
          getString: jest.fn<(name: string, required?: boolean) => string | null>((name: string) => {
            if (name === 'provider') return 'openai';
            if (name === 'api_key') return 'sk-test-key';
            return null;
          }),
          getBoolean: jest.fn<(name: string) => boolean | null>().mockReturnValue(null),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      await execute(mockInteraction as any);

      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('Unable to connect to the server'),
        })
      );
    });

    it('should handle unexpected errors with error ID', async () => {
      mockApiClient.createLLMConfig.mockRejectedValue(new Error('Unexpected error'));

      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('llm'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('set'),
          getString: jest.fn<(name: string, required?: boolean) => string | null>((name: string) => {
            if (name === 'provider') return 'openai';
            if (name === 'api_key') return 'sk-test-key';
            return null;
          }),
          getBoolean: jest.fn<(name: string) => boolean | null>().mockReturnValue(null),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      await execute(mockInteraction as any);

      expect(mockLogger.error).toHaveBeenCalled();
      expect(mockInteraction.editReply).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('Failed to process configuration command'),
        })
      );
    });
  });

  describe('ephemeral response', () => {
    it('should use ephemeral flags for all responses', async () => {
      const mockConfig = {
        id: 1,
        community_server_id: 'guild456',
        provider: 'openai',
        enabled: true,
        created_at: new Date().toISOString(),
      };

      mockApiClient.createLLMConfig.mockResolvedValue(mockConfig);

      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('llm'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('set'),
          getString: jest.fn<(name: string, required?: boolean) => string | null>((name: string) => {
            if (name === 'provider') return 'openai';
            if (name === 'api_key') return 'sk-test-key';
            return null;
          }),
          getBoolean: jest.fn<(name: string) => boolean | null>().mockReturnValue(null),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      await execute(mockInteraction as any);

      const v2EphemeralFlags = MessageFlags.Ephemeral | MessageFlags.IsComponentsV2;
      expect(mockInteraction.deferReply).toHaveBeenCalledWith({ flags: v2EphemeralFlags });
    });
  });

  describe('logging', () => {
    it('should log command execution start and completion for OpenAI', async () => {
      const mockConfig = {
        id: 1,
        community_server_id: 'guild456',
        provider: 'openai',
        enabled: true,
        created_at: new Date().toISOString(),
      };

      mockApiClient.createLLMConfig.mockResolvedValue(mockConfig);

      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('llm'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('set'),
          getString: jest.fn<(name: string, required?: boolean) => string | null>((name: string) => {
            if (name === 'provider') return 'openai';
            if (name === 'api_key') return 'sk-test-key';
            return null;
          }),
          getBoolean: jest.fn<(name: string) => boolean | null>().mockReturnValue(null),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      await execute(mockInteraction as any);

      expect(mockLogger.info).toHaveBeenCalledWith(
        'Executing config command',
        expect.objectContaining({
          command: 'config',
          user_id: 'user123',
          community_server_id: 'guild456',
        })
      );

      expect(mockLogger.info).toHaveBeenCalledWith(
        'LLM API key configured successfully',
        expect.objectContaining({
          community_server_id: 'guild456',
          user_id: 'user123',
          config_id: 1,
          provider: 'openai',
        })
      );
    });

    it('should log command execution start and completion for Anthropic', async () => {
      const mockConfig = {
        id: 2,
        community_server_id: 'guild789',
        provider: 'anthropic',
        enabled: true,
        created_at: new Date().toISOString(),
      };

      mockApiClient.createLLMConfig.mockResolvedValue(mockConfig);

      const mockInteraction = {
        user: { id: 'user456' },
        guildId: 'guild789',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('llm'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('set'),
          getString: jest.fn<(name: string, required?: boolean) => string | null>((name: string) => {
            if (name === 'provider') return 'anthropic';
            if (name === 'api_key') return 'sk-ant-test-key';
            return null;
          }),
          getBoolean: jest.fn<(name: string) => boolean | null>().mockReturnValue(null),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      await execute(mockInteraction as any);

      expect(mockLogger.info).toHaveBeenCalledWith(
        'LLM API key configured successfully',
        expect.objectContaining({
          provider: 'anthropic',
        })
      );
    });

    it('should log errors with full context', async () => {
      mockApiClient.createLLMConfig.mockRejectedValue(new Error('Test error'));

      const mockInteraction = {
        user: { id: 'user123' },
        guildId: 'guild456',
        options: {
          getSubcommandGroup: jest.fn<() => string>().mockReturnValue('llm'),
          getSubcommand: jest.fn<() => string>().mockReturnValue('set'),
          getString: jest.fn<(name: string, required?: boolean) => string | null>((name: string) => {
            if (name === 'provider') return 'openai';
            if (name === 'api_key') return 'sk-test-key';
            return null;
          }),
          getBoolean: jest.fn<(name: string) => boolean | null>().mockReturnValue(null),
        },
        deferReply: jest.fn<(opts: any) => Promise<void>>().mockResolvedValue(undefined),
        editReply: jest.fn<(opts: any) => Promise<void>>(),
      };

      await execute(mockInteraction as any);

      expect(mockLogger.error).toHaveBeenCalledWith(
        'Error in config command',
        expect.objectContaining({
          command: 'config',
          user_id: 'user123',
          community_server_id: 'guild456',
          error: 'Test error',
        })
      );
    });
  });
});
