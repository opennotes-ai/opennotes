import { apiClient } from '../api-client.js';
import { getRedisClient } from '../redis-client.js';
import { ServiceProvider } from './ServiceProvider.js';

const redis = getRedisClient();
if (!redis) {
  throw new Error('Redis client is required for ServiceProvider. Set REDIS_URL environment variable.');
}

export const serviceProvider = new ServiceProvider(apiClient, redis);

export * from './types.js';
export * from './WriteNoteService.js';
export * from './ViewNotesService.js';
export * from './RateNoteService.js';
export * from './RequestNoteService.js';
export * from './ListRequestsService.js';
export * from './StatusService.js';
export * from './RedisRateLimitService.js';
export * from './RateLimitFactory.js';
export * from './ServiceProvider.js';
export * from './GuildConfigService.js';
export * from './GuildOnboardingService.js';
