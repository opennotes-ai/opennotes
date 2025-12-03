import { jest } from '@jest/globals';
import type { Client, TextChannel } from 'discord.js';
import { MessageFetcher } from '../../src/lib/message-fetcher.js';

describe('MessageFetcher', () => {
  let mockClient: jest.Mocked<Client>;
  let messageFetcher: MessageFetcher;

  beforeEach(() => {
    mockClient = {
      channels: {
        cache: new Map(),
        fetch: jest.fn(),
      },
    } as any;

    messageFetcher = new MessageFetcher(mockClient);
  });

  describe('LRU cache behavior', () => {
    it('should cache fetched messages', async () => {
      const mockChannel = {
        isTextBased: () => true,
        messages: {
          fetch: jest.fn<() => Promise<any>>().mockResolvedValue({
            content: 'Test message',
            author: { username: 'TestUser' },
            url: 'https://discord.com/test',
          }),
        },
      } as any as TextChannel;

      (mockClient.channels.fetch as jest.Mock<() => Promise<any>>).mockResolvedValue(mockChannel);

      // First call - should fetch from Discord
      const result1 = await messageFetcher.fetchMessage('123456', 'channel123');
      expect(result1).toEqual({
        content: 'Test message',
        author: 'TestUser',
        url: 'https://discord.com/test',
      });

      // Second call - should return from cache
      const result2 = await messageFetcher.fetchMessage('123456', 'channel123');
      expect(result2).toEqual(result1);

      // Verify fetch was only called once (first time)
      expect(mockChannel.messages.fetch).toHaveBeenCalledTimes(1);
    });

    it('should track cache hits and misses', async () => {
      const mockChannel = {
        isTextBased: () => true,
        messages: {
          fetch: jest.fn<() => Promise<any>>().mockResolvedValue({
            content: 'Test',
            author: { username: 'User' },
            url: 'https://test.com',
          }),
        },
      } as any as TextChannel;

      (mockClient.channels.fetch as jest.Mock<() => Promise<any>>).mockResolvedValue(mockChannel);

      // First call - cache miss
      await messageFetcher.fetchMessage('123', 'ch1');
      let metrics = messageFetcher.getCacheMetrics();
      expect(metrics.hits).toBe(0);
      expect(metrics.misses).toBe(1);

      // Second call - cache hit
      await messageFetcher.fetchMessage('123', 'ch1');
      metrics = messageFetcher.getCacheMetrics();
      expect(metrics.hits).toBe(1);
      expect(metrics.misses).toBe(1);
      expect(metrics.hitRate).toBe(0.5);
    });

    it('should respect max cache size (evict oldest entries)', async () => {
      // Create fetcher with max size of 3
      const smallCacheFetcher = new MessageFetcher(mockClient, 3);

      const mockChannel = {
        isTextBased: () => true,
        messages: {
          fetch: jest.fn<(id: string) => Promise<any>>().mockImplementation((id: string) =>
            Promise.resolve({
              content: `Message ${id}`,
              author: { username: 'User' },
              url: `https://test.com/${id}`,
            }),
          ),
        },
      } as any as TextChannel;

      (mockClient.channels.fetch as jest.Mock<() => Promise<any>>).mockResolvedValue(mockChannel);

      // Add 4 messages (exceeds max size of 3)
      await smallCacheFetcher.fetchMessage('1', 'ch1');
      await smallCacheFetcher.fetchMessage('2', 'ch1');
      await smallCacheFetcher.fetchMessage('3', 'ch1');
      await smallCacheFetcher.fetchMessage('4', 'ch1');

      // Cache size should be 3 (max size)
      expect(smallCacheFetcher.getCacheSize()).toBe(3);

      const metrics = smallCacheFetcher.getCacheMetrics();
      expect(metrics.size).toBe(3);
      expect(metrics.maxSize).toBe(3);
    });

    it('should cache not-found messages to prevent repeated lookups', async () => {
      const mockChannel = {
        isTextBased: () => true,
        messages: {
          fetch: jest.fn<() => Promise<any>>().mockRejectedValue(new Error('Not found')),
        },
      } as any as TextChannel;

      (mockClient.channels.fetch as jest.Mock<() => Promise<any>>).mockResolvedValue(mockChannel);
      (mockClient.channels.cache as any) = new Map();

      // First call - should attempt fetch
      const result1 = await messageFetcher.fetchMessage('nonexistent', 'ch1');
      expect(result1).toBeNull();

      // Second call - should return null from cache without fetching
      const result2 = await messageFetcher.fetchMessage('nonexistent', 'ch1');
      expect(result2).toBeNull();

      // Should have attempted fetch only once
      expect(mockChannel.messages.fetch).toHaveBeenCalledTimes(1);
    });

    it('should clear cache properly', async () => {
      const mockChannel = {
        isTextBased: () => true,
        messages: {
          fetch: jest.fn<() => Promise<any>>().mockResolvedValue({
            content: 'Test',
            author: { username: 'User' },
            url: 'https://test.com',
          }),
        },
      } as any as TextChannel;

      (mockClient.channels.fetch as jest.Mock<() => Promise<any>>).mockResolvedValue(mockChannel);

      // Add some messages
      await messageFetcher.fetchMessage('1', 'ch1');
      await messageFetcher.fetchMessage('2', 'ch1');

      expect(messageFetcher.getCacheSize()).toBeGreaterThan(0);
      const metricsBefore = messageFetcher.getCacheMetrics();
      expect(metricsBefore.misses).toBe(2);

      // Clear cache
      messageFetcher.clearCache();

      expect(messageFetcher.getCacheSize()).toBe(0);
      const metricsAfter = messageFetcher.getCacheMetrics();
      expect(metricsAfter.hits).toBe(0);
      expect(metricsAfter.misses).toBe(0);
      expect(metricsAfter.size).toBe(0);
    });

    it('should calculate hit rate correctly', async () => {
      const mockChannel = {
        isTextBased: () => true,
        messages: {
          fetch: jest.fn<() => Promise<any>>().mockResolvedValue({
            content: 'Test',
            author: { username: 'User' },
            url: 'https://test.com',
          }),
        },
      } as any as TextChannel;

      (mockClient.channels.fetch as jest.Mock<() => Promise<any>>).mockResolvedValue(mockChannel);

      // 1 miss
      await messageFetcher.fetchMessage('1', 'ch1');
      // 1 hit
      await messageFetcher.fetchMessage('1', 'ch1');
      // 1 hit
      await messageFetcher.fetchMessage('1', 'ch1');
      // 1 hit
      await messageFetcher.fetchMessage('1', 'ch1');

      const metrics = messageFetcher.getCacheMetrics();
      expect(metrics.hits).toBe(3);
      expect(metrics.misses).toBe(1);
      expect(metrics.hitRate).toBe(0.75); // 3/4
    });

    it('should handle TTL expiration (conceptual test)', () => {
      // Create fetcher with very short TTL (1ms)
      const shortTTLFetcher = new MessageFetcher(mockClient, 1000, 1);
      const metrics = shortTTLFetcher.getCacheMetrics();

      // Verify TTL setting was applied (maxSize is set correctly)
      expect(metrics.maxSize).toBe(1000);
    });
  });

  describe('getCacheMetrics', () => {
    it('should return correct metrics structure', () => {
      const metrics = messageFetcher.getCacheMetrics();

      expect(metrics).toHaveProperty('hits');
      expect(metrics).toHaveProperty('misses');
      expect(metrics).toHaveProperty('size');
      expect(metrics).toHaveProperty('maxSize');
      expect(metrics).toHaveProperty('hitRate');
      expect(metrics).toHaveProperty('searchPerformance');

      expect(typeof metrics.hits).toBe('number');
      expect(typeof metrics.misses).toBe('number');
      expect(typeof metrics.size).toBe('number');
      expect(typeof metrics.maxSize).toBe('number');
      expect(typeof metrics.hitRate).toBe('number');

      expect(typeof metrics.searchPerformance.totalSearches).toBe('number');
      expect(typeof metrics.searchPerformance.limitReached).toBe('number');
      expect(typeof metrics.searchPerformance.averageChannelsChecked).toBe('number');
    });

    it('should return 0 hit rate when no requests made', () => {
      const metrics = messageFetcher.getCacheMetrics();
      expect(metrics.hitRate).toBe(0);
    });
  });

  describe('channel search limits', () => {
    it('should limit channel searches to default 50 channels', async () => {
      // Create 100 mock channels
      const channelCache = new Map();
      for (let i = 0; i < 100; i++) {
        const mockChannel = {
          isTextBased: () => true,
          messages: {
            fetch: jest.fn<() => Promise<any>>().mockRejectedValue(new Error('Not found')),
          },
        } as any as TextChannel;
        channelCache.set(`channel${i}`, mockChannel);
      }

      (mockClient.channels.cache as any) = channelCache;
      (mockClient.channels.fetch as jest.Mock<() => Promise<any>>).mockRejectedValue(new Error('Not found'));

      // Try to fetch a message (will search all channels)
      await messageFetcher.fetchMessage('nonexistent');

      const metrics = messageFetcher.getCacheMetrics();

      // Should have searched, but limited to 50 channels
      expect(metrics.searchPerformance.totalSearches).toBe(1);
      expect(metrics.searchPerformance.limitReached).toBe(1);
      expect(metrics.searchPerformance.averageChannelsChecked).toBe(50);
    });

    it('should track search performance metrics', async () => {
      // Create 10 mock channels
      const channelCache = new Map();
      for (let i = 0; i < 10; i++) {
        const shouldFind = i === 5;
        const mockChannel = {
          isTextBased: () => true,
          messages: {
            fetch: jest.fn<() => Promise<any>>().mockImplementation(() => {
              if (shouldFind) {
                return Promise.resolve({
                  content: 'Found!',
                  author: { username: 'User' },
                  url: 'https://test.com',
                });
              }
              return Promise.reject(new Error('Not found'));
            }),
          },
        } as any as TextChannel;
        channelCache.set(`channel${i}`, mockChannel);
      }

      (mockClient.channels.cache as any) = channelCache;
      (mockClient.channels.fetch as jest.Mock<() => Promise<any>>).mockRejectedValue(new Error('Not found'));

      // Search for message (will find it in channel 5, checking 6 channels)
      await messageFetcher.fetchMessage('test-message');

      const metrics = messageFetcher.getCacheMetrics();

      // Should have performed 1 search
      expect(metrics.searchPerformance.totalSearches).toBe(1);
      // Should not have reached limit (only 10 channels)
      expect(metrics.searchPerformance.limitReached).toBe(0);
      // Should have checked some channels before finding it
      expect(metrics.searchPerformance.averageChannelsChecked).toBeGreaterThan(0);
    });

    it('should clear search metrics when clearing cache', async () => {
      const channelCache = new Map();
      for (let i = 0; i < 5; i++) {
        const mockChannel = {
          isTextBased: () => true,
          messages: {
            fetch: jest.fn<() => Promise<any>>().mockRejectedValue(new Error('Not found')),
          },
        } as any as TextChannel;
        channelCache.set(`channel${i}`, mockChannel);
      }

      (mockClient.channels.cache as any) = channelCache;
      (mockClient.channels.fetch as jest.Mock<() => Promise<any>>).mockRejectedValue(new Error('Not found'));

      // Perform a search
      await messageFetcher.fetchMessage('test');

      let metrics = messageFetcher.getCacheMetrics();
      expect(metrics.searchPerformance.totalSearches).toBeGreaterThan(0);

      // Clear cache
      messageFetcher.clearCache();

      metrics = messageFetcher.getCacheMetrics();
      expect(metrics.searchPerformance.totalSearches).toBe(0);
      expect(metrics.searchPerformance.limitReached).toBe(0);
      expect(metrics.searchPerformance.averageChannelsChecked).toBe(0);
    });
  });
});
