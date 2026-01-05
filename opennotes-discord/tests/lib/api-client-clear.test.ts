import { jest } from '@jest/globals';
import { loggerFactory } from '@opennotes/test-utils';

const mockFetch = jest.fn<typeof fetch>();
global.fetch = mockFetch;

const mockLogger = loggerFactory.build();

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
}));

jest.unstable_mockModule('../../src/config.js', () => ({
  config: {
    serverUrl: 'http://localhost:8000',
    discordToken: 'test-token',
    clientId: 'test-client-id',
    environment: 'development',
  },
}));

jest.unstable_mockModule('../../src/utils/gcp-auth.js', () => ({
  getIdentityToken: jest.fn<() => Promise<string | null>>().mockResolvedValue(null),
  isRunningOnGCP: jest.fn<() => Promise<boolean>>().mockResolvedValue(false),
}));

const { ApiClient } = await import('../../src/lib/api-client.js');

describe('ApiClient Clear Methods', () => {
  let client: InstanceType<typeof ApiClient>;

  beforeEach(() => {
    jest.clearAllMocks();
    client = new ApiClient({
      serverUrl: 'http://localhost:8000',
      environment: 'development',
    });
  });

  describe('getClearPreview', () => {
    it('should return preview with correct field mapping', async () => {
      const mockResponse = {
        would_delete_count: 15,
        message: 'Would delete 15 requests',
      };

      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify(mockResponse), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      );

      const result = await client.getClearPreview(
        '/api/v2/community-servers/uuid-123/clear-requests/preview?mode=all'
      );

      expect(result.wouldDeleteCount).toBe(15);
      expect(result.message).toBe('Would delete 15 requests');
      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/v2/community-servers/uuid-123/clear-requests/preview?mode=all',
        expect.objectContaining({
          headers: expect.any(Object),
        })
      );
    });

    it('should return zero count when no items to delete', async () => {
      const mockResponse = {
        would_delete_count: 0,
        message: 'Would delete 0 unpublished notes',
      };

      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify(mockResponse), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      );

      const result = await client.getClearPreview(
        '/api/v2/community-servers/uuid-123/clear-notes/preview?mode=30'
      );

      expect(result.wouldDeleteCount).toBe(0);
      expect(result.message).toBe('Would delete 0 unpublished notes');
    });
  });

  describe('executeClear', () => {
    it('should execute delete and return result with correct field mapping', async () => {
      const mockResponse = {
        deleted_count: 10,
        message: 'Deleted 10 requests',
      };

      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify(mockResponse), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      );

      const result = await client.executeClear(
        '/api/v2/community-servers/uuid-123/clear-requests?mode=all'
      );

      expect(result.deletedCount).toBe(10);
      expect(result.message).toBe('Deleted 10 requests');
      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/v2/community-servers/uuid-123/clear-requests?mode=all',
        expect.objectContaining({
          method: 'DELETE',
          headers: expect.any(Object),
        })
      );
    });

    it('should handle notes deletion with days filter', async () => {
      const mockResponse = {
        deleted_count: 5,
        message: 'Deleted 5 unpublished notes older than 30 days',
      };

      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify(mockResponse), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      );

      const result = await client.executeClear(
        '/api/v2/community-servers/uuid-123/clear-notes?mode=30'
      );

      expect(result.deletedCount).toBe(5);
      expect(result.message).toBe('Deleted 5 unpublished notes older than 30 days');
    });

    it('should use DELETE method', async () => {
      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify({ deleted_count: 0, message: 'Deleted 0 requests' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      );

      await client.executeClear('/api/v2/community-servers/uuid-123/clear-requests?mode=all');

      expect(mockFetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          method: 'DELETE',
        })
      );
    });
  });
});
