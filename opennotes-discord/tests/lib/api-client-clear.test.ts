import { jest } from '@jest/globals';
import { loggerFactory } from '@opennotes/test-utils';
import { getFetchRequestDetails } from '../utils/fetch-request-helpers.js';

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
    it('should return preview with correct field mapping for requests', async () => {
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

      const result = await client.getClearPreview('uuid-123', 'requests', 'all');

      expect(result.wouldDeleteCount).toBe(15);
      expect(result.message).toBe('Would delete 15 requests');

      const req = getFetchRequestDetails(mockFetch);
      expect(req.url).toContain('/api/v2/community-servers/uuid-123/clear-requests/preview');
      expect(req.url).toContain('mode=all');
      expect(req.method).toBe('GET');
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

      const result = await client.getClearPreview('uuid-123', 'notes', '30');

      expect(result.wouldDeleteCount).toBe(0);
      expect(result.message).toBe('Would delete 0 unpublished notes');

      const req = getFetchRequestDetails(mockFetch);
      expect(req.url).toContain('/api/v2/community-servers/uuid-123/clear-notes/preview');
      expect(req.url).toContain('mode=30');
    });

    it('should call the correct endpoint for notes type', async () => {
      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify({ would_delete_count: 3, message: 'ok' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      );

      await client.getClearPreview('server-id', 'notes', 'all');

      const req = getFetchRequestDetails(mockFetch);
      expect(req.url).toContain('/clear-notes/preview');
      expect(req.url).not.toContain('/clear-requests/');
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

      const result = await client.executeClear('uuid-123', 'requests', 'all');

      expect(result.deletedCount).toBe(10);
      expect(result.message).toBe('Deleted 10 requests');

      const req = getFetchRequestDetails(mockFetch);
      expect(req.url).toContain('/api/v2/community-servers/uuid-123/clear-requests');
      expect(req.url).toContain('mode=all');
      expect(req.url).not.toContain('/preview');
      expect(req.method).toBe('DELETE');
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

      const result = await client.executeClear('uuid-123', 'notes', '30');

      expect(result.deletedCount).toBe(5);
      expect(result.message).toBe('Deleted 5 unpublished notes older than 30 days');

      const req = getFetchRequestDetails(mockFetch);
      expect(req.url).toContain('/clear-notes');
      expect(req.url).toContain('mode=30');
    });

    it('should use DELETE method for requests', async () => {
      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify({ deleted_count: 0, message: 'Deleted 0 requests' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      );

      await client.executeClear('uuid-123', 'requests', 'all');

      const req = getFetchRequestDetails(mockFetch);
      expect(req.method).toBe('DELETE');
    });

    it('should use DELETE method for notes', async () => {
      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify({ deleted_count: 0, message: 'Deleted 0 notes' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      );

      await client.executeClear('uuid-123', 'notes', 'all');

      const req = getFetchRequestDetails(mockFetch);
      expect(req.method).toBe('DELETE');
      expect(req.url).toContain('/clear-notes');
    });
  });
});
