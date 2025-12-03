/**
 * Cache configuration interface
 */
export interface CacheConfig {
  defaultTtl?: number;
  keyPrefix?: string;
  maxSize?: number;
  evictionPolicy?: 'lru' | 'fifo';
}

/**
 * Cache metrics for monitoring
 */
export interface CacheMetrics {
  hits: number;
  misses: number;
  sets: number;
  deletes: number;
  evictions: number;
  size: number;
}

/**
 * Abstract cache interface
 *
 * Provides a unified interface for cache operations across different implementations.
 * Supports both in-memory and distributed caching strategies.
 */
export interface CacheInterface {
  /**
   * Get a value from the cache
   * @param key Cache key
   * @returns The cached value or null if not found
   */
  get<T>(key: string): Promise<T | null>;

  /**
   * Set a value in the cache
   * @param key Cache key
   * @param value Value to cache
   * @param ttl Time to live in seconds (optional)
   * @returns True if successful
   */
  set(key: string, value: unknown, ttl?: number): Promise<boolean>;

  /**
   * Delete a value from the cache
   * @param key Cache key
   * @returns True if the key existed and was deleted
   */
  delete(key: string): Promise<boolean>;

  /**
   * Check if a key exists in the cache
   * @param key Cache key
   * @returns True if the key exists
   */
  exists(key: string): Promise<boolean>;

  /**
   * Set expiration time for a key
   * @param key Cache key
   * @param ttl Time to live in seconds
   * @returns True if successful
   */
  expire(key: string, ttl: number): Promise<boolean>;

  /**
   * Get multiple values from the cache
   * @param keys Array of cache keys
   * @returns Array of values (null for missing keys)
   */
  mget(keys: string[]): Promise<unknown[]>;

  /**
   * Set multiple values in the cache
   * @param items Map of key-value pairs
   * @param ttl Time to live in seconds (optional)
   * @returns True if successful
   */
  mset(items: Map<string, unknown>, ttl?: number): Promise<boolean>;

  /**
   * Clear cache entries matching a pattern
   * @param pattern Key pattern (optional, clears all if not provided)
   * @returns Number of keys deleted
   */
  clear(pattern?: string): Promise<number>;

  /**
   * Check if the cache is healthy
   * @returns True if the cache is operational
   */
  ping(): Promise<boolean>;

  /**
   * Get cache metrics
   * @returns Current cache metrics
   */
  getMetrics(): CacheMetrics;

  /**
   * Start the cache (for implementations that need initialization)
   */
  start(): void;

  /**
   * Stop the cache (cleanup resources)
   */
  stop(): void;
}

/**
 * Cache entry with expiration metadata
 */
export interface CacheEntry<T> {
  value: T;
  expiresAt: number | null;
  createdAt: number;
}
