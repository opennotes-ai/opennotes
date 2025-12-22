import { jest } from '@jest/globals';
import { ApiClient, type JSONAPISingleResponse, type SimilaritySearchResultAttributes } from '../../src/lib/api-client.js';

type FetchWithRetryFn = <T>(endpoint: string, options?: RequestInit) => Promise<T>;

describe('ApiClient.similaritySearch', () => {
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

  describe('JSONAPI passthrough', () => {
    it('should return raw JSONAPI response without transformation', async () => {
      const mockJsonApiResponse: JSONAPISingleResponse<SimilaritySearchResultAttributes> = {
        jsonapi: { version: '1.1' },
        data: {
          type: 'similarity-search-results',
          id: 'search-123',
          attributes: {
            matches: [
              {
                id: 'fact-check-1',
                dataset_name: 'snopes',
                dataset_tags: ['snopes', 'factcheck'],
                title: 'Test Fact Check',
                content: 'This is a test fact check content',
                summary: 'Test summary',
                rating: 'FALSE',
                source_url: 'https://snopes.com/test',
                published_date: '2024-01-15',
                author: 'Fact Checker',
                embedding_provider: 'openai',
                embedding_model: 'text-embedding-3-small',
                similarity_score: 0.92,
              },
              {
                id: 'fact-check-2',
                dataset_name: 'snopes',
                dataset_tags: ['snopes'],
                title: 'Another Fact Check',
                content: 'Another test content',
                summary: null,
                rating: 'TRUE',
                source_url: null,
                published_date: null,
                author: null,
                embedding_provider: null,
                embedding_model: null,
                similarity_score: 0.85,
              },
            ],
            query_text: 'test query',
            dataset_tags: ['snopes'],
            similarity_threshold: 0.7,
            rrf_score_threshold: 0.5,
            total_matches: 2,
          },
        },
      };

      fetchWithRetrySpy.mockResolvedValue(mockJsonApiResponse);

      const result = await apiClient.similaritySearch(
        'test query',
        'community-server-123',
        ['snopes'],
        0.7,
        5
      );

      expect(result).toEqual(mockJsonApiResponse);

      expect(result.jsonapi).toBeDefined();
      expect(result.jsonapi.version).toBe('1.1');
      expect(result.data).toBeDefined();
      expect(result.data.type).toBe('similarity-search-results');
      expect(result.data.id).toBe('search-123');
      expect(result.data.attributes).toBeDefined();
      expect(result.data.attributes.matches).toHaveLength(2);
      expect(result.data.attributes.query_text).toBe('test query');
      expect(result.data.attributes.dataset_tags).toEqual(['snopes']);
      expect(result.data.attributes.similarity_threshold).toBe(0.7);
      expect(result.data.attributes.rrf_score_threshold).toBe(0.5);
      expect(result.data.attributes.total_matches).toBe(2);
    });

    it('should access match properties through data.attributes.matches', async () => {
      const mockJsonApiResponse: JSONAPISingleResponse<SimilaritySearchResultAttributes> = {
        jsonapi: { version: '1.1' },
        data: {
          type: 'similarity-search-results',
          id: 'search-456',
          attributes: {
            matches: [
              {
                id: 'match-1',
                dataset_name: 'politifact',
                dataset_tags: ['politifact'],
                title: 'Political Claim Check',
                content: 'Content about political claim',
                summary: 'Summary of claim',
                rating: 'PANTS_ON_FIRE',
                source_url: 'https://politifact.com/check',
                published_date: '2024-02-20',
                author: 'PolitiFact Staff',
                embedding_provider: 'openai',
                embedding_model: 'text-embedding-3-small',
                similarity_score: 0.95,
              },
            ],
            query_text: 'political claim query',
            dataset_tags: ['politifact'],
            similarity_threshold: 0.8,
            rrf_score_threshold: 0.6,
            total_matches: 1,
          },
        },
      };

      fetchWithRetrySpy.mockResolvedValue(mockJsonApiResponse);

      const result = await apiClient.similaritySearch(
        'political claim query',
        'community-server-789',
        ['politifact'],
        0.8,
        10
      );

      const firstMatch = result.data.attributes.matches[0];
      expect(firstMatch.id).toBe('match-1');
      expect(firstMatch.dataset_name).toBe('politifact');
      expect(firstMatch.title).toBe('Political Claim Check');
      expect(firstMatch.rating).toBe('PANTS_ON_FIRE');
      expect(firstMatch.similarity_score).toBe(0.95);
    });

    it('should handle empty matches array', async () => {
      const mockJsonApiResponse: JSONAPISingleResponse<SimilaritySearchResultAttributes> = {
        jsonapi: { version: '1.1' },
        data: {
          type: 'similarity-search-results',
          id: 'search-empty',
          attributes: {
            matches: [],
            query_text: 'no results query',
            dataset_tags: ['snopes'],
            similarity_threshold: 0.9,
            rrf_score_threshold: 0.7,
            total_matches: 0,
          },
        },
      };

      fetchWithRetrySpy.mockResolvedValue(mockJsonApiResponse);

      const result = await apiClient.similaritySearch(
        'no results query',
        'community-server-000',
        ['snopes'],
        0.9,
        5
      );

      expect(result.data.attributes.matches).toHaveLength(0);
      expect(result.data.attributes.total_matches).toBe(0);
    });

    it('should send correct JSONAPI request body', async () => {
      const mockJsonApiResponse: JSONAPISingleResponse<SimilaritySearchResultAttributes> = {
        jsonapi: { version: '1.1' },
        data: {
          type: 'similarity-search-results',
          id: 'search-req-test',
          attributes: {
            matches: [],
            query_text: 'request body test',
            dataset_tags: ['snopes', 'politifact'],
            similarity_threshold: 0.75,
            rrf_score_threshold: 0.5,
            total_matches: 0,
          },
        },
      };

      fetchWithRetrySpy.mockResolvedValue(mockJsonApiResponse);

      await apiClient.similaritySearch(
        'request body test',
        'cs-uuid-123',
        ['snopes', 'politifact'],
        0.75,
        10
      );

      expect(fetchWithRetrySpy).toHaveBeenCalledWith(
        '/api/v2/similarity-searches',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({
            data: {
              type: 'similarity-searches',
              attributes: {
                text: 'request body test',
                community_server_id: 'cs-uuid-123',
                dataset_tags: ['snopes', 'politifact'],
                similarity_threshold: 0.75,
                limit: 10,
              },
            },
          }),
        })
      );
    });
  });
});
