import { jest } from '@jest/globals';
import {
  responseFactoryHelpers,
  loggerFactory,
  type JsonApiResource,
} from '@opennotes/test-utils';

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

describe('ApiClient MonitoredChannel Methods - JSONAPI Passthrough', () => {
  let client: InstanceType<typeof ApiClient>;

  beforeEach(() => {
    jest.clearAllMocks();
    client = new ApiClient({
      serverUrl: 'http://localhost:8000',
      environment: 'development',
    });
  });

  describe('listMonitoredChannels', () => {
    it('should return raw JSONAPI list response structure', async () => {
      const monitoredChannelResource: JsonApiResource = {
        type: 'monitored-channels',
        id: 'uuid-123',
        attributes: {
          community_server_id: 'server-456',
          channel_id: 'channel-789',
          enabled: true,
          similarity_threshold: 0.8,
          dataset_tags: ['snopes'],
          previously_seen_autopublish_threshold: null,
          previously_seen_autorequest_threshold: null,
          created_at: '2024-01-01T00:00:00Z',
          updated_at: '2024-01-02T00:00:00Z',
          updated_by: 'user-123',
        },
      };

      mockFetch.mockResolvedValueOnce(
        responseFactoryHelpers.jsonApiCollection([monitoredChannelResource], {
          links: { self: '/api/v2/monitored-channels' },
        })
      );

      const result = await client.listMonitoredChannels('server-456', true);

      expect(result.data).toHaveLength(1);
      expect(result.data[0].type).toBe('monitored-channels');
      expect(result.data[0].id).toBe('uuid-123');
      expect(result.data[0].attributes.community_server_id).toBe('server-456');
      expect(result.data[0].attributes.channel_id).toBe('channel-789');
      expect(result.data[0].attributes.enabled).toBe(true);
      expect(result.jsonapi).toEqual({ version: '1.1' });
      expect(result.meta?.count).toBe(1);
    });
  });

  describe('createMonitoredChannel', () => {
    it('should return raw JSONAPI single response structure', async () => {
      const newChannelResource: JsonApiResource = {
        type: 'monitored-channels',
        id: 'uuid-new-123',
        attributes: {
          community_server_id: 'server-456',
          channel_id: 'channel-new-789',
          enabled: true,
          similarity_threshold: 0.8,
          dataset_tags: ['snopes'],
          previously_seen_autopublish_threshold: null,
          previously_seen_autorequest_threshold: null,
          created_at: '2024-01-01T00:00:00Z',
          updated_at: null,
          updated_by: 'user-123',
        },
        links: { self: '/api/v2/monitored-channels/uuid-new-123' },
      };

      mockFetch.mockResolvedValueOnce(
        responseFactoryHelpers.jsonApiSuccess(newChannelResource, { status: 201 })
      );

      const result = await client.createMonitoredChannel({
        community_server_id: 'server-456',
        channel_id: 'channel-new-789',
        enabled: true,
        similarity_threshold: 0.8,
        dataset_tags: ['snopes'],
        updated_by: 'user-123',
      });

      expect(result).not.toBeNull();
      expect(result!.data.type).toBe('monitored-channels');
      expect(result!.data.id).toBe('uuid-new-123');
      expect(result!.data.attributes.community_server_id).toBe('server-456');
      expect(result!.data.attributes.channel_id).toBe('channel-new-789');
      expect(result!.jsonapi).toEqual({ version: '1.1' });
    });

    it('should return null on 409 conflict', async () => {
      mockFetch.mockResolvedValueOnce(
        responseFactoryHelpers.jsonApiError(409, {
          status: '409',
          title: 'Conflict',
          detail: 'Resource already exists',
        })
      );

      const result = await client.createMonitoredChannel({
        community_server_id: 'server-456',
        channel_id: 'channel-existing',
        enabled: true,
      });

      expect(result).toBeNull();
    });
  });

  describe('getMonitoredChannelByUuid', () => {
    it('should return raw JSONAPI single response structure', async () => {
      const channelResource: JsonApiResource = {
        type: 'monitored-channels',
        id: 'uuid-123',
        attributes: {
          community_server_id: 'server-456',
          channel_id: 'channel-789',
          enabled: true,
          similarity_threshold: 0.8,
          dataset_tags: ['snopes'],
          previously_seen_autopublish_threshold: 0.9,
          previously_seen_autorequest_threshold: 0.85,
          created_at: '2024-01-01T00:00:00Z',
          updated_at: '2024-01-02T00:00:00Z',
          updated_by: 'user-123',
        },
        links: { self: '/api/v2/monitored-channels/uuid-123' },
      };

      mockFetch.mockResolvedValueOnce(
        responseFactoryHelpers.jsonApiSuccess(channelResource)
      );

      const result = await client.getMonitoredChannelByUuid('uuid-123');

      expect(result.data.type).toBe('monitored-channels');
      expect(result.data.id).toBe('uuid-123');
      expect(result.data.attributes.channel_id).toBe('channel-789');
      expect(result.data.attributes.previously_seen_autopublish_threshold).toBe(0.9);
      expect(result.jsonapi).toEqual({ version: '1.1' });
    });
  });

  describe('getMonitoredChannel', () => {
    it('should return raw JSONAPI single response when channel found', async () => {
      const channelResource: JsonApiResource = {
        type: 'monitored-channels',
        id: 'uuid-123',
        attributes: {
          community_server_id: 'server-456',
          channel_id: 'channel-789',
          enabled: true,
          similarity_threshold: 0.8,
          dataset_tags: ['snopes'],
          previously_seen_autopublish_threshold: null,
          previously_seen_autorequest_threshold: null,
          created_at: '2024-01-01T00:00:00Z',
          updated_at: null,
          updated_by: null,
        },
      };

      mockFetch.mockResolvedValueOnce(
        responseFactoryHelpers.jsonApiCollection([channelResource])
      );

      const result = await client.getMonitoredChannel('channel-789', 'server-456');

      expect(result).not.toBeNull();
      expect(result!.data.type).toBe('monitored-channels');
      expect(result!.data.id).toBe('uuid-123');
      expect(result!.data.attributes.channel_id).toBe('channel-789');
    });

    it('should return null when channel not found', async () => {
      mockFetch.mockResolvedValueOnce(
        responseFactoryHelpers.jsonApiCollection([])
      );

      const result = await client.getMonitoredChannel('channel-nonexistent', 'server-456');

      expect(result).toBeNull();
    });
  });

  describe('updateMonitoredChannel', () => {
    it('should return raw JSONAPI single response on successful update', async () => {
      const existingChannelResource: JsonApiResource = {
        type: 'monitored-channels',
        id: 'uuid-123',
        attributes: {
          community_server_id: 'server-456',
          channel_id: 'channel-789',
          enabled: true,
          similarity_threshold: 0.8,
          dataset_tags: ['snopes'],
          previously_seen_autopublish_threshold: null,
          previously_seen_autorequest_threshold: null,
          created_at: '2024-01-01T00:00:00Z',
          updated_at: null,
          updated_by: null,
        },
      };

      const updatedChannelResource: JsonApiResource = {
        type: 'monitored-channels',
        id: 'uuid-123',
        attributes: {
          community_server_id: 'server-456',
          channel_id: 'channel-789',
          enabled: false,
          similarity_threshold: 0.9,
          dataset_tags: ['snopes', 'politifact'],
          previously_seen_autopublish_threshold: null,
          previously_seen_autorequest_threshold: null,
          created_at: '2024-01-01T00:00:00Z',
          updated_at: '2024-01-02T00:00:00Z',
          updated_by: 'user-456',
        },
        links: { self: '/api/v2/monitored-channels/uuid-123' },
      };

      mockFetch
        .mockResolvedValueOnce(
          responseFactoryHelpers.jsonApiCollection([existingChannelResource])
        )
        .mockResolvedValueOnce(
          responseFactoryHelpers.jsonApiSuccess(updatedChannelResource)
        );

      const result = await client.updateMonitoredChannel('channel-789', {
        enabled: false,
        similarity_threshold: 0.9,
        dataset_tags: ['snopes', 'politifact'],
        updated_by: 'user-456',
      });

      expect(result).not.toBeNull();
      expect(result!.data.type).toBe('monitored-channels');
      expect(result!.data.id).toBe('uuid-123');
      expect(result!.data.attributes.enabled).toBe(false);
      expect(result!.data.attributes.similarity_threshold).toBe(0.9);
      expect(result!.data.attributes.dataset_tags).toEqual(['snopes', 'politifact']);
      expect(result!.jsonapi).toEqual({ version: '1.1' });
    });

    it('should return null when channel not found', async () => {
      mockFetch.mockResolvedValueOnce(
        responseFactoryHelpers.jsonApiCollection([])
      );

      const result = await client.updateMonitoredChannel('channel-nonexistent', {
        enabled: false,
      });

      expect(result).toBeNull();
    });
  });
});
