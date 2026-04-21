import { Factory } from 'fishery';
import { jest } from '@jest/globals';

export interface CacheMetrics {
  hits: number;
  misses: number;
  sets: number;
  deletes: number;
  evictions: number;
  size: number;
}

export interface MockCache {
  get: ReturnType<typeof jest.fn<(key: string) => Promise<unknown>>>;
  set: ReturnType<
    typeof jest.fn<(key: string, value: unknown, ttl?: number) => Promise<boolean>>
  >;
  delete: ReturnType<typeof jest.fn<(key: string) => Promise<boolean>>>;
  exists: ReturnType<typeof jest.fn<(key: string) => Promise<boolean>>>;
  expire: ReturnType<typeof jest.fn<(key: string, ttl: number) => Promise<boolean>>>;
  mget: ReturnType<typeof jest.fn<(keys: string[]) => Promise<unknown[]>>>;
  mset: ReturnType<
    typeof jest.fn<(items: Map<string, unknown>, ttl?: number) => Promise<boolean>>
  >;
  clear: ReturnType<typeof jest.fn<(pattern?: string) => Promise<number>>>;
  ping: ReturnType<typeof jest.fn<() => Promise<boolean>>>;
  getMetrics: ReturnType<typeof jest.fn<() => CacheMetrics>>;
  start: ReturnType<typeof jest.fn<() => void>>;
  stop: ReturnType<typeof jest.fn<() => void>>;
  _store: Map<string, unknown>;
  _metrics: CacheMetrics;
}

export type CacheTransientParams = {
  initialValues?: Record<string, unknown>;
};

export const cacheFactory = Factory.define<MockCache, CacheTransientParams>(
  ({ transientParams }) => {
    const { initialValues } = transientParams;

    const store = new Map<string, unknown>();
    const metrics: CacheMetrics = {
      hits: 0,
      misses: 0,
      sets: 0,
      deletes: 0,
      evictions: 0,
      size: 0,
    };

    if (initialValues) {
      for (const [key, value] of Object.entries(initialValues)) {
        store.set(key, value);
      }
      metrics.size = store.size;
    }

    const get = jest.fn<(key: string) => Promise<unknown>>(async (key: string) => {
      const value = store.get(key);
      if (value !== undefined) {
        metrics.hits++;
        return value;
      }
      metrics.misses++;
      return null;
    });

    const set = jest.fn<(key: string, value: unknown, ttl?: number) => Promise<boolean>>(
      async (key: string, value: unknown, _ttl?: number) => {
        store.set(key, value);
        metrics.sets++;
        metrics.size = store.size;
        return true;
      }
    );

    const deleteKey = jest.fn<(key: string) => Promise<boolean>>(async (key: string) => {
      const existed = store.has(key);
      store.delete(key);
      if (existed) {
        metrics.deletes++;
        metrics.size = store.size;
      }
      return existed;
    });

    const exists = jest.fn<(key: string) => Promise<boolean>>(async (key: string) => {
      return store.has(key);
    });

    const expire = jest.fn<(key: string, ttl: number) => Promise<boolean>>(
      async (key: string, _ttl: number) => {
        return store.has(key);
      }
    );

    const mget = jest.fn<(keys: string[]) => Promise<unknown[]>>(
      async (keys: string[]) => {
        return keys.map((key) => {
          const value = store.get(key);
          if (value !== undefined) {
            metrics.hits++;
            return value;
          }
          metrics.misses++;
          return null;
        });
      }
    );

    const mset = jest.fn<(items: Map<string, unknown>, ttl?: number) => Promise<boolean>>(
      async (items: Map<string, unknown>, _ttl?: number) => {
        for (const [key, value] of items) {
          store.set(key, value);
          metrics.sets++;
        }
        metrics.size = store.size;
        return true;
      }
    );

    const clear = jest.fn<(pattern?: string) => Promise<number>>(
      async (pattern?: string) => {
        let count = 0;
        if (pattern) {
          const regex = new RegExp(pattern.replace(/\*/g, '.*'));
          for (const key of store.keys()) {
            if (regex.test(key)) {
              store.delete(key);
              count++;
            }
          }
        } else {
          count = store.size;
          store.clear();
        }
        metrics.size = store.size;
        return count;
      }
    );

    const ping = jest.fn<() => Promise<boolean>>(async () => true);

    const getMetrics = jest.fn<() => CacheMetrics>(() => ({ ...metrics }));

    const start = jest.fn<() => void>();
    const stop = jest.fn<() => void>();

    return {
      get,
      set,
      delete: deleteKey,
      exists,
      expire,
      mget,
      mset,
      clear,
      ping,
      getMetrics,
      start,
      stop,
      _store: store,
      _metrics: metrics,
    };
  }
);
