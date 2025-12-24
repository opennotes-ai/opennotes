import { Factory } from 'fishery';
import { jest } from '@jest/globals';
import type { MockDiscordMember } from './discord-member.js';

export interface MockDiscordGuild {
  id: string;
  name: string;
  memberCount: number;
  members: {
    cache: Map<string, MockDiscordMember>;
    fetch: ReturnType<typeof jest.fn<(id: string) => Promise<MockDiscordMember | null>>>;
    fetchMe: ReturnType<typeof jest.fn<() => Promise<MockDiscordMember>>>;
    me: MockDiscordMember | null;
  };
  channels: {
    cache: Map<string, unknown> & { filter: (fn: (channel: unknown) => boolean) => Map<string, unknown> };
    create: ReturnType<typeof jest.fn<(options: any) => Promise<any>>>;
    fetch: ReturnType<typeof jest.fn<(id?: string) => Promise<any>>>;
  };
  roles: {
    cache: Map<string, { id: string; name: string }>;
    everyone: { id: string; name: string };
  };
}

export interface DiscordGuildTransientParams {
  botMember?: MockDiscordMember;
}

export const discordGuildFactory = Factory.define<MockDiscordGuild, DiscordGuildTransientParams>(
  ({ sequence, transientParams }) => {
    const { botMember } = transientParams;

    const membersCache = new Map<string, MockDiscordMember>();
    const channelsCache = new Map<string, unknown>();
    const rolesCache = new Map<string, { id: string; name: string }>();

    const everyoneRole = { id: `guild-${sequence}`, name: '@everyone' };
    rolesCache.set(everyoneRole.id, everyoneRole);

    const channelsCacheWithFilter = Object.assign(channelsCache, {
      filter: jest.fn((fn: (channel: unknown) => boolean) => {
        const filtered = new Map<string, unknown>();
        for (const [key, value] of channelsCache) {
          if (fn(value)) {
            filtered.set(key, value);
          }
        }
        return filtered;
      }),
    });

    return {
      id: `guild-${sequence}`,
      name: `Test Guild ${sequence}`,
      memberCount: 100,
      members: {
        cache: membersCache,
        fetch: jest.fn<(id: string) => Promise<MockDiscordMember | null>>().mockResolvedValue(null),
        fetchMe: jest.fn<() => Promise<MockDiscordMember>>().mockImplementation(async () => {
          if (botMember) {
            return botMember;
          }
          throw new Error('No bot member configured');
        }),
        me: botMember ?? null,
      },
      channels: {
        cache: channelsCacheWithFilter,
        create: jest.fn<(options: any) => Promise<any>>().mockResolvedValue({ id: 'new-channel-id' }),
        fetch: jest.fn<(id?: string) => Promise<any>>().mockResolvedValue(null),
      },
      roles: {
        cache: rolesCache,
        everyone: everyoneRole,
      },
    };
  }
);
