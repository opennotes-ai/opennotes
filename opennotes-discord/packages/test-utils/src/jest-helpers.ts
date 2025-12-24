import { jest } from '@jest/globals';
import { loggerFactory, type MockLogger } from './factories/logger.js';
import {
  cacheFactory,
  type MockCache,
  type CacheTransientParams,
} from './factories/cache.js';

export type { MockLogger };
export type { MockCache, CacheTransientParams };

export function createMockLogger(): MockLogger {
  return loggerFactory.build();
}

export function createMockCache(
  initialValues?: Record<string, unknown>
): MockCache {
  return cacheFactory.build({}, { transient: { initialValues } });
}

export function createMockInteraction(overrides?: any) {
  return {
    deferReply: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
    editReply: jest.fn<() => Promise<any>>().mockResolvedValue({}),
    reply: jest.fn<() => Promise<any>>().mockResolvedValue({}),
    followUp: jest.fn<() => Promise<any>>().mockResolvedValue({}),
    deleteReply: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
    showModal: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
    deferred: false,
    user: {
      id: 'user-123',
      username: 'testuser',
    },
    channelId: 'channel-456',
    guildId: 'guild-789',
    channel: {
      id: 'channel-456',
      send: jest.fn<() => Promise<any>>().mockResolvedValue({}),
    },
    client: {
      guilds: {
        cache: {
          size: 5,
        },
      },
    },
    options: {
      getString: jest.fn<(name: string) => string | null>(),
      getBoolean: jest.fn<(name: string) => boolean | null>(),
      getInteger: jest.fn<(name: string) => number | null>(),
      getUser: jest.fn<(name: string) => any>(),
      getChannel: jest.fn<(name: string) => any>(),
      getRole: jest.fn<(name: string) => any>(),
      getMentionable: jest.fn<(name: string) => any>(),
      getNumber: jest.fn<(name: string) => number | null>(),
      getAttachment: jest.fn<(name: string) => any>(),
      getSubcommand: jest.fn<() => string>(),
      getSubcommandGroup: jest.fn<() => string | null>(),
    },
    targetMessage: {
      id: 'message-123',
      content: 'test message content',
      author: {
        id: 'author-456',
        username: 'testauthor',
      },
    },
    customId: 'test-custom-id',
    fields: {
      getTextInputValue: jest.fn<(customId: string) => string>(),
    },
    ...overrides,
  };
}

export function createMockFetchResponse(
  data: any,
  options?: { ok?: boolean; status?: number; statusText?: string }
): {
  ok: boolean;
  status: number;
  statusText: string;
  json: ReturnType<typeof jest.fn<() => Promise<any>>>;
  text: ReturnType<typeof jest.fn<() => Promise<string>>>;
  headers: Headers;
} {
  return {
    ok: options?.ok ?? true,
    status: options?.status ?? 200,
    statusText: options?.statusText ?? 'OK',
    json: jest.fn<() => Promise<any>>().mockResolvedValue(data),
    text: jest.fn<() => Promise<string>>().mockResolvedValue(JSON.stringify(data)),
    headers: new Headers(),
  };
}
