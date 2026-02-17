import { jest } from '@jest/globals';
import { ApiClient, type ClaimRelevanceCheckResponse } from '../../src/lib/api-client.js';

type FetchWithRetryFn = <T>(endpoint: string, options?: RequestInit) => Promise<T>;

describe('ApiClient.checkClaimRelevance', () => {
  let apiClient: ApiClient;
  let fetchWithRetrySpy: jest.SpiedFunction<FetchWithRetryFn>;

  beforeEach(() => {
    apiClient = new ApiClient({
      serverUrl: 'http://localhost:8000',
      apiKey: 'test-key',
      environment: 'development',
    });

    fetchWithRetrySpy = jest.spyOn(
      apiClient as unknown as { fetchWithRetry: FetchWithRetryFn },
      'fetchWithRetry'
    );
  });

  afterEach(() => {
    jest.restoreAllMocks();
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

    fetchWithRetrySpy.mockResolvedValue(mockResponse);

    await apiClient.checkClaimRelevance({
      originalMessage: 'Vaccines cause autism',
      matchedContent: 'This claim has been debunked',
      matchedSource: 'https://snopes.com/vaccines',
      similarityScore: 0.85,
    });

    expect(fetchWithRetrySpy).toHaveBeenCalledWith(
      '/api/v2/claim-relevance-checks',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          data: {
            type: 'claim-relevance-checks',
            attributes: {
              original_message: 'Vaccines cause autism',
              matched_content: 'This claim has been debunked',
              matched_source: 'https://snopes.com/vaccines',
              similarity_score: 0.85,
            },
          },
        }),
      })
    );
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

    fetchWithRetrySpy.mockResolvedValue(mockResponse);

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

    fetchWithRetrySpy.mockResolvedValue(mockResponse);

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
    fetchWithRetrySpy.mockRejectedValue(new Error('API request failed: 500 Internal Server Error'));

    const result = await apiClient.checkClaimRelevance({
      originalMessage: 'Some message',
      matchedContent: 'Some content',
      matchedSource: 'https://example.com',
      similarityScore: 0.8,
    });

    expect(result).toBeNull();
  });

  it('should return null on network error (fail-open)', async () => {
    fetchWithRetrySpy.mockRejectedValue(new Error('fetch failed'));

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

    fetchWithRetrySpy.mockResolvedValue(mockResponse);

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
