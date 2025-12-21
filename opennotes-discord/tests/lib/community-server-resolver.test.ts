import { jest } from '@jest/globals';
import type { CommunityServerJSONAPIResponse } from '../../src/lib/api-client.js';

const mockApiClient = {
  getCommunityServerByPlatformId: jest.fn<
    (platformId: string, platform?: string) => Promise<CommunityServerJSONAPIResponse>
  >(),
};

jest.unstable_mockModule('../../src/api-client.js', () => ({
  apiClient: mockApiClient,
}));

const { resolveCommunityServerId } = await import('../../src/lib/community-server-resolver.js');

function createMockCommunityServerResponse(
  id: string,
  platformId: string,
  name: string,
  isActive: boolean = true
): CommunityServerJSONAPIResponse {
  return {
    data: {
      type: 'community-servers',
      id,
      attributes: {
        platform: 'discord',
        platform_id: platformId,
        name,
        is_active: isActive,
        is_public: true,
      },
    },
    jsonapi: { version: '1.1' },
  };
}

describe('resolveCommunityServerId', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('should call getCommunityServerByPlatformId with the guild ID', async () => {
    const guildId = '1234567890123456789';
    const expectedUuid = 'f47ac10b-58cc-4372-a567-0e02b2c3d479';

    mockApiClient.getCommunityServerByPlatformId.mockResolvedValueOnce(
      createMockCommunityServerResponse(expectedUuid, guildId, 'Test Server')
    );

    await resolveCommunityServerId(guildId);

    expect(mockApiClient.getCommunityServerByPlatformId).toHaveBeenCalledWith(guildId);
  });

  it('should return the UUID from the community server response', async () => {
    const guildId = '1234567890123456789';
    const expectedUuid = 'f47ac10b-58cc-4372-a567-0e02b2c3d479';

    mockApiClient.getCommunityServerByPlatformId.mockResolvedValueOnce(
      createMockCommunityServerResponse(expectedUuid, guildId, 'Test Server')
    );

    const result = await resolveCommunityServerId(guildId);

    expect(result).toBe(expectedUuid);
  });

  it('should propagate errors from the API', async () => {
    const guildId = 'nonexistent-guild';
    const error = new Error('Community server not found');

    mockApiClient.getCommunityServerByPlatformId.mockRejectedValueOnce(error);

    await expect(resolveCommunityServerId(guildId)).rejects.toThrow('Community server not found');
  });

  it('should handle different guild ID formats', async () => {
    const guildId = '9876543210987654321';
    const expectedUuid = 'a1b2c3d4-e5f6-4789-abcd-ef1234567890';

    mockApiClient.getCommunityServerByPlatformId.mockResolvedValueOnce(
      createMockCommunityServerResponse(expectedUuid, guildId, 'Another Server')
    );

    const result = await resolveCommunityServerId(guildId);

    expect(result).toBe(expectedUuid);
    expect(mockApiClient.getCommunityServerByPlatformId).toHaveBeenCalledWith(guildId);
  });
});
