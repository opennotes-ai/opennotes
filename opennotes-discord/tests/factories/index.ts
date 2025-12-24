/**
 * Test Factories for Discord Bot
 *
 * This directory contains Fishery factories for creating test fixtures.
 * Factories provide type-safe, consistent test data with automatic sequencing.
 *
 * Usage:
 *   import { noteFactory } from './factories/index.js';
 *   const note = noteFactory.build({ content: 'Custom content' });
 *   const notes = noteFactory.buildList(5);
 *
 * Re-export shared factories from @opennotes/test-utils:
 */
export { Factory, noteFactory, ratingFactory, loggerFactory, cacheFactory } from '@opennotes/test-utils';
export type { MockLogger, LoggerTransientParams, MockCache, CacheTransientParams } from '@opennotes/test-utils';

/**
 * Discord-specific factories:
 */

export {
  discordUserFactory,
  type MockDiscordUser,
  type DiscordUserTransientParams,
} from './discord-user.js';

export {
  discordMemberFactory,
  adminMemberFactory,
  type MockDiscordMember,
  type DiscordMemberTransientParams,
} from './discord-member.js';

export {
  discordGuildFactory,
  type MockDiscordGuild,
  type DiscordGuildTransientParams,
} from './discord-guild.js';

export {
  discordChannelFactory,
  type MockDiscordChannel,
  type DiscordChannelTransientParams,
} from './discord-channel.js';

export {
  chatInputCommandInteractionFactory,
  adminInteractionFactory,
  dmInteractionFactory,
  type MockChatInputCommandInteraction,
  type MockCommandInteractionOptions,
  type ChatInputCommandInteractionTransientParams,
} from './chat-input-command-interaction.js';

export {
  apiClientFactory,
  type MockApiClient,
  type ApiClientTransientParams,
} from './api-client.js';

export {
  discordMessageFactory,
  dmMessageFactory,
  systemMessageFactory,
  webhookMessageFactory,
  type MockDiscordMessage,
  type MessageTransientParams,
} from './discord-message.js';

export {
  natsConnectionFactory,
  closedNatsConnectionFactory,
  failingJetStreamConnectionFactory,
  createAsyncIterator,
  createMockJsMessage,
  createMockSubscription,
  createMockConnect,
  createFailingMockConnect,
  type MockNatsConnection,
  type MockJetStreamClient,
  type MockJetStreamManager,
  type MockConsumerAPI,
  type MockStatusEvent,
  type NatsConnectionTransientParams,
} from './nats-connection.js';

export {
  guildConfigFactory,
  type GuildConfig,
  type GuildConfigTransientParams,
} from './guild-config.js';

export {
  rateLimiterFactory,
  rateLimitedFactory,
  unlimitedRateLimiterFactory,
  type MockRateLimiter,
  type RateLimiterTransientParams,
} from './rate-limiter.js';

export {
  redisClientFactory,
  disconnectedRedisFactory,
  pubSubRedisFactory,
  createMockSubscriber,
  createMockRedisClass,
  simulateMessage,
  asRedis,
  type MockRedisClient,
  type MockRedisSubscriber,
  type MockRedisMulti,
  type MockRedisPipeline,
  type RedisTransientParams,
} from './redis.js';
