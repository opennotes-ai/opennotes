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

export interface MockInteractionUser {
  id: string;
  username: string;
}

export interface MockInteractionChannel {
  id: string;
  send: ReturnType<typeof jest.fn<() => Promise<unknown>>>;
}

export interface MockInteractionClient {
  guilds: {
    cache: {
      size: number;
    };
  };
}

export interface MockInteractionOptions {
  getString: ReturnType<typeof jest.fn<(name: string) => string | null>>;
  getBoolean: ReturnType<typeof jest.fn<(name: string) => boolean | null>>;
  getInteger: ReturnType<typeof jest.fn<(name: string) => number | null>>;
  getUser: ReturnType<typeof jest.fn<(name: string) => MockInteractionUser | null>>;
  getChannel: ReturnType<typeof jest.fn<(name: string) => MockInteractionChannel | null>>;
  getRole: ReturnType<typeof jest.fn<(name: string) => { id: string; name: string } | null>>;
  getMentionable: ReturnType<typeof jest.fn<(name: string) => { id: string } | null>>;
  getNumber: ReturnType<typeof jest.fn<(name: string) => number | null>>;
  getAttachment: ReturnType<typeof jest.fn<(name: string) => { url: string } | null>>;
  getSubcommand: ReturnType<typeof jest.fn<() => string>>;
  getSubcommandGroup: ReturnType<typeof jest.fn<() => string | null>>;
}

export interface MockInteractionTargetMessage {
  id: string;
  content: string;
  author: {
    id: string;
    username: string;
  };
}

export interface MockInteraction {
  deferReply: ReturnType<typeof jest.fn<() => Promise<void>>>;
  editReply: ReturnType<typeof jest.fn<() => Promise<unknown>>>;
  reply: ReturnType<typeof jest.fn<() => Promise<unknown>>>;
  followUp: ReturnType<typeof jest.fn<() => Promise<unknown>>>;
  deleteReply: ReturnType<typeof jest.fn<() => Promise<void>>>;
  showModal: ReturnType<typeof jest.fn<() => Promise<void>>>;
  deferred: boolean;
  user: MockInteractionUser;
  channelId: string;
  guildId: string | null;
  channel: MockInteractionChannel;
  client: MockInteractionClient;
  options: MockInteractionOptions;
  targetMessage: MockInteractionTargetMessage;
  customId: string;
  fields: {
    getTextInputValue: ReturnType<typeof jest.fn<(customId: string) => string>>;
  };
}

export interface MockInteractionOverrides {
  user?: Partial<MockInteractionUser>;
  channel?: Partial<MockInteractionChannel>;
  client?: Partial<MockInteractionClient>;
  options?: Partial<MockInteractionOptions>;
  targetMessage?: Partial<MockInteractionTargetMessage>;
  deferred?: boolean;
  channelId?: string;
  guildId?: string | null;
  customId?: string;
}

export function createMockInteraction(overrides?: MockInteractionOverrides): MockInteraction {
  return {
    deferReply: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
    editReply: jest.fn<() => Promise<unknown>>().mockResolvedValue({}),
    reply: jest.fn<() => Promise<unknown>>().mockResolvedValue({}),
    followUp: jest.fn<() => Promise<unknown>>().mockResolvedValue({}),
    deleteReply: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
    showModal: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
    deferred: overrides?.deferred ?? false,
    user: {
      id: 'user-123',
      username: 'testuser',
      ...overrides?.user,
    },
    channelId: overrides?.channelId ?? 'channel-456',
    guildId: overrides?.guildId ?? 'guild-789',
    channel: {
      id: 'channel-456',
      send: jest.fn<() => Promise<unknown>>().mockResolvedValue({}),
      ...overrides?.channel,
    },
    client: {
      guilds: {
        cache: {
          size: 5,
        },
      },
      ...overrides?.client,
    },
    options: {
      getString: jest.fn<(name: string) => string | null>(),
      getBoolean: jest.fn<(name: string) => boolean | null>(),
      getInteger: jest.fn<(name: string) => number | null>(),
      getUser: jest.fn<(name: string) => MockInteractionUser | null>(),
      getChannel: jest.fn<(name: string) => MockInteractionChannel | null>(),
      getRole: jest.fn<(name: string) => { id: string; name: string } | null>(),
      getMentionable: jest.fn<(name: string) => { id: string } | null>(),
      getNumber: jest.fn<(name: string) => number | null>(),
      getAttachment: jest.fn<(name: string) => { url: string } | null>(),
      getSubcommand: jest.fn<() => string>(),
      getSubcommandGroup: jest.fn<() => string | null>(),
      ...overrides?.options,
    },
    targetMessage: {
      id: 'message-123',
      content: 'test message content',
      author: {
        id: 'author-456',
        username: 'testauthor',
      },
      ...overrides?.targetMessage,
    },
    customId: overrides?.customId ?? 'test-custom-id',
    fields: {
      getTextInputValue: jest.fn<(customId: string) => string>(),
    },
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
