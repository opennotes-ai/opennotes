import { LRUCache } from 'lru-cache';
import { ApiClient } from '../lib/api-client.js';
import { logger } from '../logger.js';
import { ConfigKey, ConfigValue, ConfigValidator } from '../lib/config-schema.js';

interface GuildConfig {
  [key: string]: ConfigValue;
}

export interface CacheMetrics {
  hits: number;
  misses: number;
  evictions: number;
  size: number;
  totalRequests: number;
  hitRate: number;
}

export class GuildConfigService {
  private cache: LRUCache<string, GuildConfig>;
  private readonly CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutes
  private readonly MAX_CACHE_SIZE = 500; // Max guilds to cache

  // Cache metrics
  private cacheHits = 0;
  private cacheMisses = 0;
  private cacheEvictions = 0;

  constructor(private apiClient: ApiClient) {
    this.cache = new LRUCache<string, GuildConfig>({
      max: this.MAX_CACHE_SIZE,
      ttl: this.CACHE_TTL_MS,
      updateAgeOnGet: true, // LRU behavior
      dispose: (): void => {
        this.cacheEvictions++;
      },
    });
  }

  async get(guildId: string, key: ConfigKey): Promise<ConfigValue> {
    const config = await this.getGuildConfig(guildId);
    return config[key] ?? ConfigValidator.getDefault(key);
  }

  async getAll(guildId: string): Promise<GuildConfig> {
    return this.getGuildConfig(guildId);
  }

  async set(guildId: string, key: ConfigKey, value: ConfigValue, updatedBy: string): Promise<void> {
    // Validate value
    const validation = ConfigValidator.validate(key, value);
    if (!validation.valid) {
      throw new Error(validation.error);
    }

    try {
      // Call API to store config
      await this.apiClient.setGuildConfig(guildId, key, validation.parsedValue!, updatedBy);

      // Invalidate cache
      this.invalidateCache(guildId);

      logger.info('Guild config updated', {
        guildId,
        key,
        value: validation.parsedValue,
        updatedBy,
      });
    } catch (error) {
      logger.error('Failed to set guild config', {
        error,
        guildId,
        key,
        value,
      });
      throw error;
    }
  }

  async reset(guildId: string, key?: ConfigKey, updatedBy?: string): Promise<void> {
    try {
      if (key) {
        // Reset single key to default
        const defaultValue = ConfigValidator.getDefault(key);
        await this.apiClient.setGuildConfig(guildId, key, defaultValue, updatedBy || 'system');
        logger.info('Guild config key reset', { guildId, key });
      } else {
        // Reset all keys
        await this.apiClient.resetGuildConfig(guildId);
        logger.info('All guild config reset', { guildId });
      }

      // Invalidate cache
      this.invalidateCache(guildId);
    } catch (error) {
      logger.error('Failed to reset guild config', {
        error,
        guildId,
        key,
      });
      throw error;
    }
  }

  private async getGuildConfig(guildId: string): Promise<GuildConfig> {
    // Check cache
    const cached = this.cache.get(guildId);
    if (cached !== undefined) {
      this.cacheHits++;
      return cached;
    }

    this.cacheMisses++;

    try {
      // Fetch from API
      const config = await this.apiClient.getGuildConfig(guildId);

      // Merge with defaults
      const fullConfig: GuildConfig = {} as GuildConfig;
      for (const key of ConfigValidator.getAllKeys()) {
        fullConfig[key] = (config[key] as ConfigValue | undefined) ?? ConfigValidator.getDefault(key);
      }

      // Update cache
      this.cache.set(guildId, fullConfig);

      return fullConfig;
    } catch (error) {
      logger.error('Failed to fetch guild config, using defaults', {
        error,
        guildId,
      });

      // Return all defaults on error
      const defaultConfig: GuildConfig = {} as GuildConfig;
      for (const key of ConfigValidator.getAllKeys()) {
        defaultConfig[key] = ConfigValidator.getDefault(key);
      }
      return defaultConfig;
    }
  }

  private invalidateCache(guildId: string): void {
    this.cache.delete(guildId);
  }

  clearAllCache(): void {
    this.cache.clear();
    this.cacheHits = 0;
    this.cacheMisses = 0;
    this.cacheEvictions = 0;
  }

  getCacheSize(): number {
    return this.cache.size;
  }

  getCacheMetrics(): CacheMetrics {
    const totalRequests = this.cacheHits + this.cacheMisses;
    const hitRate = totalRequests > 0 ? (this.cacheHits / totalRequests) * 100 : 0;

    return {
      hits: this.cacheHits,
      misses: this.cacheMisses,
      evictions: this.cacheEvictions,
      size: this.cache.size,
      totalRequests,
      hitRate: Math.round(hitRate * 100) / 100, // Round to 2 decimal places
    };
  }
}
