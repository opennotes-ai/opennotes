import { logger } from '../logger.js';
import type { ApiClient } from './api-client.js';

/**
 * Simple in-memory cache with TTL for user profile UUID lookups.
 */
const cache = new Map<string, { uuid: string; expiry: number }>();
const CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutes

/**
 * Check if a string is a valid UUID v4/v7 format.
 */
export function isValidUUID(value: string): boolean {
  const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  return uuidRegex.test(value);
}

/**
 * Resolves a Discord user ID (snowflake) to a user profile UUID.
 *
 * The server API expects author_id and rater_id to be UUIDs (internal database IDs),
 * not Discord snowflakes. This function performs the lookup via the API with caching.
 *
 * @param discordUserId - The Discord user ID (snowflake string)
 * @param client - The API client to use for lookups
 * @returns The user profile UUID
 * @throws Error if the user profile cannot be found or created
 */
export async function resolveUserProfileId(discordUserId: string, client: ApiClient): Promise<string> {
  // Skip if already a UUID
  if (isValidUUID(discordUserId)) {
    return discordUserId;
  }

  // Check cache
  const cached = cache.get(discordUserId);
  if (cached && cached.expiry > Date.now()) {
    logger.debug('User profile cache hit', { discordUserId, uuid: cached.uuid });
    return cached.uuid;
  }

  // Lookup from server
  logger.debug('Resolving Discord user ID to profile UUID', { discordUserId });
  const response = await client.getUserProfileByPlatformId(discordUserId);
  const uuid = response.data.id;

  // Cache result
  cache.set(discordUserId, { uuid, expiry: Date.now() + CACHE_TTL_MS });
  logger.debug('User profile resolved and cached', { discordUserId, uuid });

  return uuid;
}

/**
 * Clear the user profile cache. Useful for testing.
 */
export function clearCache(): void {
  cache.clear();
}
