import { apiClient } from '../api-client.js';

/**
 * Resolves a Discord guild ID (snowflake) to a community server UUID.
 *
 * The server API expects community_server_id to be a UUID (internal database ID),
 * not a Discord snowflake. This function performs the lookup via the API.
 *
 * @param guildId - The Discord guild ID (snowflake string)
 * @returns The community server UUID
 * @throws Error if the community server is not found
 */
export async function resolveCommunityServerId(guildId: string): Promise<string> {
  const communityServer = await apiClient.getCommunityServerByPlatformId(guildId);
  return communityServer.id;
}
