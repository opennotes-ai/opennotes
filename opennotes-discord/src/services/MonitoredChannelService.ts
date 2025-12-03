import { apiClient } from '../api-client.js';
import { cache } from '../cache.js';
import { logger } from '../logger.js';
import type { MonitoredChannelResponse } from '../lib/api-client.js';
import { safeJSONParse } from '../utils/safe-json.js';

const CACHE_KEY_PREFIX = 'monitored_channels';
const CACHE_TTL_MS = 5 * 60 * 1000;

export class MonitoredChannelService {
  private lastFetchTime: Map<string, number> = new Map();

  async isChannelMonitored(channelId: string, guildId: string): Promise<boolean> {
    const config = await this.getChannelConfig(channelId, guildId);
    return config !== null && config.enabled;
  }

  async getChannelConfig(
    channelId: string,
    guildId: string
  ): Promise<MonitoredChannelResponse | null> {
    const cacheKey = this.getCacheKey(guildId);

    let channels = await this.getCachedChannels(cacheKey, guildId);

    if (!channels) {
      await this.refreshCache(guildId);
      channels = await this.getCachedChannels(cacheKey, guildId);
    }

    if (!channels) {
      return null;
    }

    return channels.find(ch => ch.channel_id === channelId) || null;
  }

  async getAllMonitoredChannels(guildId: string): Promise<MonitoredChannelResponse[]> {
    const cacheKey = this.getCacheKey(guildId);

    let channels = await this.getCachedChannels(cacheKey, guildId);

    if (!channels) {
      await this.refreshCache(guildId);
      channels = await this.getCachedChannels(cacheKey, guildId);
    }

    return channels || [];
  }

  async refreshCache(guildId: string): Promise<void> {
    const lastFetch = this.lastFetchTime.get(guildId);
    const now = Date.now();

    if (lastFetch && now - lastFetch < 1000) {
      logger.debug('Skipping cache refresh - too recent', { guildId });
      return;
    }

    this.lastFetchTime.set(guildId, now);

    try {
      logger.debug('Fetching monitored channels from API', { guildId });

      const response = await apiClient.listMonitoredChannels(guildId, true);

      const cacheKey = this.getCacheKey(guildId);
      await cache.set(cacheKey, JSON.stringify(response.channels), CACHE_TTL_MS);

      logger.info('Monitored channels cache refreshed', {
        guildId,
        count: response.channels.length,
        ttl_ms: CACHE_TTL_MS,
      });
    } catch (error) {
      logger.error('Failed to refresh monitored channels cache', {
        guildId,
        error: error instanceof Error ? error.message : String(error),
      });
      throw error;
    }
  }

  async invalidateCache(guildId: string): Promise<void> {
    const cacheKey = this.getCacheKey(guildId);
    await cache.delete(cacheKey);
    this.lastFetchTime.delete(guildId);

    logger.info('Monitored channels cache invalidated', { guildId });
  }

  private async getCachedChannels(
    cacheKey: string,
    guildId: string
  ): Promise<MonitoredChannelResponse[] | null> {
    const cached = await cache.get<string>(cacheKey);

    if (!cached) {
      logger.debug('No cached monitored channels', { guildId });
      return null;
    }

    try {
      const channels = safeJSONParse<MonitoredChannelResponse[]>(cached, {
        validate: (data) => {
          if (!Array.isArray(data)) {
            logger.warn('Cached data is not an array', { guildId });
            return false;
          }
          return data.every((item: unknown) => {
            const hasRequiredFields =
              typeof item === 'object' &&
              item !== null &&
              'channel_id' in item &&
              'enabled' in item;

            if (!hasRequiredFields) {
              logger.warn('Cached item missing required fields', { guildId, item });
            }

            return hasRequiredFields;
          });
        },
      });

      logger.debug('Retrieved monitored channels from cache', {
        guildId,
        count: channels.length,
      });
      return channels;
    } catch (error) {
      logger.warn('Failed to parse cached monitored channels', {
        guildId,
        error: error instanceof Error ? error.message : String(error),
      });
      await cache.delete(cacheKey);
      return null;
    }
  }

  private getCacheKey(guildId: string): string {
    return `${CACHE_KEY_PREFIX}:${guildId}`;
  }
}
