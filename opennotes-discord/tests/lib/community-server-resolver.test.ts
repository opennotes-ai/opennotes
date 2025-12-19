import { jest } from '@jest/globals';

const mockApiClient = {
  getCommunityServerByPlatformId: jest.fn<
    (platformId: string, platform?: string) => Promise<{
      id: string;
      platform: string;
      platform_id: string;
      name: string;
      is_active: boolean;
    }>
  >(),
};

jest.unstable_mockModule('../../src/api-client.js', () => ({
  apiClient: mockApiClient,
}));

const { resolveCommunityServerId } = await import('../../src/lib/community-server-resolver.js');

describe('resolveCommunityServerId', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('should call getCommunityServerByPlatformId with the guild ID', async () => {
    const guildId = '1234567890123456789';
    const expectedUuid = 'f47ac10b-58cc-4372-a567-0e02b2c3d479';

    mockApiClient.getCommunityServerByPlatformId.mockResolvedValueOnce({
      id: expectedUuid,
      platform: 'discord',
      platform_id: guildId,
      name: 'Test Server',
      is_active: true,
    });

    await resolveCommunityServerId(guildId);

    expect(mockApiClient.getCommunityServerByPlatformId).toHaveBeenCalledWith(guildId);
  });

  it('should return the UUID from the community server response', async () => {
    const guildId = '1234567890123456789';
    const expectedUuid = 'f47ac10b-58cc-4372-a567-0e02b2c3d479';

    mockApiClient.getCommunityServerByPlatformId.mockResolvedValueOnce({
      id: expectedUuid,
      platform: 'discord',
      platform_id: guildId,
      name: 'Test Server',
      is_active: true,
    });

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

    mockApiClient.getCommunityServerByPlatformId.mockResolvedValueOnce({
      id: expectedUuid,
      platform: 'discord',
      platform_id: guildId,
      name: 'Another Server',
      is_active: true,
    });

    const result = await resolveCommunityServerId(guildId);

    expect(result).toBe(expectedUuid);
    expect(mockApiClient.getCommunityServerByPlatformId).toHaveBeenCalledWith(guildId);
  });
});
