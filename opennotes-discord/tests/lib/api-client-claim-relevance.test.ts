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
import type { ClaimRelevanceCheckResponse } from '../../src/lib/api-client.js';

function getLastFetchRequest(): { url: string; method: string; headers: Record<string, string>; body: string } {
  const request = mockFetch.mock.calls[mockFetch.mock.calls.length - 1][0] as Request;
  const headers: Record<string, string> = {};
  request.headers.forEach((value, key) => { headers[key] = value; });
  return {
    url: request.url,
    method: request.method,
    headers,
    body: '',
  };
}

describe('ApiClient.checkClaimRelevance', () => {
  let apiClient: InstanceType<typeof ApiClient>;

  beforeEach(() => {
    jest.clearAllMocks();
    apiClient = new ApiClient({
      serverUrl: 'http://localhost:8000',
      apiKey: 'test-key',
      environment: 'development',
    });
  });

  it('should send correct JSON:API request body to /api/v2/claim-relevance-checks', async () => {
    const mockResponse: ClaimRelevanceCheckResponse = {
      data: {
        type: 'claim-relevance-checks',
        id: 'check-123',
        attributes: {
          outcome: 'relevant',
          reasoning: 'The message repeats a debunked claim',
          should_flag: true,
        },
      },
      jsonapi: { version: '1.1' },
    };

    mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify(mockResponse), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    );

    await apiClient.checkClaimRelevance({
      originalMessage: 'Vaccines cause autism',
      matchedContent: 'This claim has been debunked',
      matchedSource: 'https://snopes.com/vaccines',
      similarityScore: 0.85,
    });

    const req = getLastFetchRequest();
    expect(req.url).toContain('/api/v2/claim-relevance-checks');
    expect(req.method).toBe('POST');
  });

  it('should return mapped result with shouldFlag=true when relevant', async () => {
    const mockResponse: ClaimRelevanceCheckResponse = {
      data: {
        type: 'claim-relevance-checks',
        id: 'check-123',
        attributes: {
          outcome: 'relevant',
          reasoning: 'The message repeats a debunked claim',
          should_flag: true,
        },
      },
      jsonapi: { version: '1.1' },
    };

    mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify(mockResponse), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    );

    const result = await apiClient.checkClaimRelevance({
      originalMessage: 'Vaccines cause autism',
      matchedContent: 'Debunked',
      matchedSource: 'https://snopes.com/vaccines',
      similarityScore: 0.85,
    });

    expect(result).toEqual({
      outcome: 'relevant',
      reasoning: 'The message repeats a debunked claim',
      shouldFlag: true,
    });
  });

  it('should return mapped result with shouldFlag=false when not relevant', async () => {
    const mockResponse: ClaimRelevanceCheckResponse = {
      data: {
        type: 'claim-relevance-checks',
        id: 'check-456',
        attributes: {
          outcome: 'not_relevant',
          reasoning: 'The message discusses the topic but does not make a claim',
          should_flag: false,
        },
      },
      jsonapi: { version: '1.1' },
    };

    mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify(mockResponse), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    );

    const result = await apiClient.checkClaimRelevance({
      originalMessage: 'I read about the vaccines debate',
      matchedContent: 'Fact check content',
      matchedSource: 'https://snopes.com',
      similarityScore: 0.65,
    });

    expect(result).toEqual({
      outcome: 'not_relevant',
      reasoning: 'The message discusses the topic but does not make a claim',
      shouldFlag: false,
    });
  });

  it('should return null on API error (fail-open)', async () => {
    mockFetch.mockResolvedValueOnce(
      new Response('Internal Server Error', {
        status: 500,
        statusText: 'Internal Server Error',
      })
    );

    const result = await apiClient.checkClaimRelevance({
      originalMessage: 'Some message',
      matchedContent: 'Some content',
      matchedSource: 'https://example.com',
      similarityScore: 0.8,
    });

    expect(result).toBeNull();
  });

  it('should return null on network error (fail-open)', async () => {
    mockFetch.mockRejectedValueOnce(new Error('fetch failed'));

    const result = await apiClient.checkClaimRelevance({
      originalMessage: 'Some message',
      matchedContent: 'Some content',
      matchedSource: 'https://example.com',
      similarityScore: 0.8,
    });

    expect(result).toBeNull();
  });

  it('should handle indeterminate outcome', async () => {
    const mockResponse: ClaimRelevanceCheckResponse = {
      data: {
        type: 'claim-relevance-checks',
        id: 'check-789',
        attributes: {
          outcome: 'indeterminate',
          reasoning: 'Cannot determine relevance with confidence',
          should_flag: true,
        },
      },
      jsonapi: { version: '1.1' },
    };

    mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify(mockResponse), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    );

    const result = await apiClient.checkClaimRelevance({
      originalMessage: 'Ambiguous message',
      matchedContent: 'Fact check content',
      matchedSource: 'https://snopes.com',
      similarityScore: 0.7,
    });

    expect(result).toEqual({
      outcome: 'indeterminate',
      reasoning: 'Cannot determine relevance with confidence',
      shouldFlag: true,
    });
  });
});
