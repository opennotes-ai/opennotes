import { jest } from '@jest/globals';
import { apiClientFactory, type MockApiClient } from './api-client.js';

describe('apiClientFactory', () => {
  afterEach(() => {
    jest.clearAllMocks();
  });

  describe('basic factory creation', () => {
    it('should create a mock API client with all methods', () => {
      const mockClient = apiClientFactory.build();

      expect(mockClient.healthCheck).toBeDefined();
      expect(mockClient.createNote).toBeDefined();
      expect(mockClient.getNotes).toBeDefined();
      expect(mockClient.getNote).toBeDefined();
      expect(mockClient.rateNote).toBeDefined();
      expect(mockClient.scoreNotes).toBeDefined();
      expect(mockClient.requestNote).toBeDefined();
      expect(mockClient.getCommunityServerByPlatformId).toBeDefined();
      expect(mockClient.getNoteScore).toBeDefined();
      expect(mockClient.getScoringStatus).toBeDefined();
      expect(mockClient.similaritySearch).toBeDefined();
    });

    it('should return typed jest mocks', () => {
      const mockClient = apiClientFactory.build();

      expect(typeof mockClient.healthCheck).toBe('function');
      expect(mockClient.healthCheck.mock).toBeDefined();
    });

    it('should create unique instances with sequenced IDs', () => {
      const client1 = apiClientFactory.build();
      const client2 = apiClientFactory.build();

      expect(client1).not.toBe(client2);
    });
  });

  describe('healthCheck defaults', () => {
    it('should return healthy status by default', async () => {
      const mockClient = apiClientFactory.build();
      const result = await mockClient.healthCheck();

      expect(result.status).toBe('healthy');
      expect(result.version).toBe('1.0.0');
    });

    it('should allow configuring health check status via transient params', async () => {
      const mockClient = apiClientFactory.build({}, {
        transient: {
          healthCheckStatus: 'degraded',
          healthCheckVersion: '2.0.0',
        },
      });

      const result = await mockClient.healthCheck();

      expect(result.status).toBe('degraded');
      expect(result.version).toBe('2.0.0');
    });

    it('should reject when healthCheckShouldFail is true', async () => {
      const mockClient = apiClientFactory.build({}, {
        transient: {
          healthCheckShouldFail: true,
        },
      });

      await expect(mockClient.healthCheck()).rejects.toThrow('Health check failed');
    });
  });

  describe('note methods defaults', () => {
    it('should return mock note from createNote', async () => {
      const mockClient = apiClientFactory.build();
      const result = await mockClient.createNote();

      expect(result.data).toBeDefined();
      expect(result.data.type).toBe('notes');
      expect(result.data.attributes.summary).toBe('Test note summary');
    });

    it('should allow configuring note defaults via transient params', async () => {
      const mockClient = apiClientFactory.build({}, {
        transient: {
          defaultNoteId: 'custom-note-id',
          defaultNoteSummary: 'Custom summary',
          defaultNoteStatus: 'CURRENTLY_RATED_HELPFUL',
        },
      });

      const result = await mockClient.getNote();

      expect(result.data.id).toBe('custom-note-id');
      expect(result.data.attributes.summary).toBe('Custom summary');
      expect(result.data.attributes.status).toBe('CURRENTLY_RATED_HELPFUL');
    });

    it('should return mock note list from getNotes', async () => {
      const mockClient = apiClientFactory.build();
      const result = await mockClient.getNotes();

      expect(result.data).toBeInstanceOf(Array);
      expect(result.data.length).toBeGreaterThan(0);
    });
  });

  describe('rating methods defaults', () => {
    it('should return mock rating from rateNote', async () => {
      const mockClient = apiClientFactory.build();
      const result = await mockClient.rateNote();

      expect(result.data).toBeDefined();
      expect(result.data.type).toBe('ratings');
      expect(result.data.attributes.helpfulness_level).toBe('HELPFUL');
    });

    it('should allow configuring rating defaults', async () => {
      const mockClient = apiClientFactory.build({}, {
        transient: {
          defaultRatingId: 'custom-rating-id',
          defaultHelpfulnessLevel: 'NOT_HELPFUL',
        },
      });

      const result = await mockClient.rateNote();

      expect(result.data.id).toBe('custom-rating-id');
      expect(result.data.attributes.helpfulness_level).toBe('NOT_HELPFUL');
    });
  });

  describe('scoring methods defaults', () => {
    it('should return mock score from getNoteScore', async () => {
      const mockClient = apiClientFactory.build();
      const result = await mockClient.getNoteScore();

      expect(result.data).toBeDefined();
      expect(result.data.type).toBe('note-scores');
      expect(result.data.attributes.score).toBe(0.75);
      expect(result.data.attributes.confidence).toBe('standard');
    });

    it('should allow configuring score defaults', async () => {
      const mockClient = apiClientFactory.build({}, {
        transient: {
          defaultScore: 0.95,
          defaultConfidence: 'provisional',
        },
      });

      const result = await mockClient.getNoteScore();

      expect(result.data.attributes.score).toBe(0.95);
      expect(result.data.attributes.confidence).toBe('provisional');
    });

    it('should return mock scoring status', async () => {
      const mockClient = apiClientFactory.build();
      const result = await mockClient.getScoringStatus();

      expect(result.data.type).toBe('scoring-status');
      expect(result.data.attributes.current_note_count).toBe(100);
    });
  });

  describe('community server methods defaults', () => {
    it('should return mock community server', async () => {
      const mockClient = apiClientFactory.build();
      const result = await mockClient.getCommunityServerByPlatformId();

      expect(result.data).toBeDefined();
      expect(result.data.type).toBe('community-servers');
      expect(result.data.attributes.platform).toBe('discord');
    });

    it('should allow configuring community server ID', async () => {
      const mockClient = apiClientFactory.build({}, {
        transient: {
          defaultCommunityServerId: 'custom-community-id',
        },
      });

      const result = await mockClient.getCommunityServerByPlatformId();

      expect(result.data.id).toBe('custom-community-id');
    });
  });

  describe('mock method behavior', () => {
    it('should allow overriding mock return values', async () => {
      const mockClient = apiClientFactory.build();

      mockClient.healthCheck.mockResolvedValueOnce({
        status: 'custom-status',
        version: '3.0.0',
      });

      const result = await mockClient.healthCheck();

      expect(result.status).toBe('custom-status');
      expect(result.version).toBe('3.0.0');
    });

    it('should allow mocking rejections', async () => {
      const mockClient = apiClientFactory.build();

      mockClient.createNote.mockRejectedValueOnce(new Error('API Error'));

      await expect(mockClient.createNote()).rejects.toThrow('API Error');
    });

    it('should track call counts', async () => {
      const mockClient = apiClientFactory.build();

      await mockClient.healthCheck();
      await mockClient.healthCheck();
      await mockClient.getNotes();

      expect(mockClient.healthCheck).toHaveBeenCalledTimes(2);
      expect(mockClient.getNotes).toHaveBeenCalledTimes(1);
    });
  });

  describe('buildList', () => {
    it('should create multiple unique mock clients', () => {
      const clients = apiClientFactory.buildList(3);

      expect(clients).toHaveLength(3);
      expect(clients[0]).not.toBe(clients[1]);
      expect(clients[1]).not.toBe(clients[2]);
    });
  });
});
