import { jest } from '@jest/globals';
import {
  loggerFactory,
  cacheFactory,
  redisClientFactory,
  apiClientFactory,
  asRedis,
} from '../factories/index.js';

process.env.DISCORD_TOKEN = 'test-token';
process.env.CLIENT_ID = 'test-client-id';
process.env.SERVER_URL = 'http://localhost:3000';
process.env.API_KEY = 'test-api-key';

const mockLogger = loggerFactory.build();
const mockCache = cacheFactory.build();
const mockRedis = redisClientFactory.build();

jest.unstable_mockModule('../../src/lib/api-client.js', () => ({
  ApiClient: jest.fn(),
}));

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
}));

jest.unstable_mockModule('../../src/cache.js', () => ({
  cache: mockCache,
}));

const { ServiceProvider } = await import('../../src/services/ServiceProvider.js');

describe('ServiceProvider', () => {
  let serviceProvider: InstanceType<typeof ServiceProvider>;
  let mockApiClient: ReturnType<typeof apiClientFactory.build>;

  beforeEach(() => {
    jest.clearAllMocks();

    mockApiClient = apiClientFactory.build();
    serviceProvider = new ServiceProvider(mockApiClient as any, asRedis(mockRedis));
  });

  afterEach(() => {
    serviceProvider.shutdown();
  });

  describe('service accessors', () => {
    it('should return WriteNoteService', () => {
      const service = serviceProvider.getWriteNoteService();
      expect(service).toBeDefined();
    });

    it('should return ViewNotesService', () => {
      const service = serviceProvider.getViewNotesService();
      expect(service).toBeDefined();
    });

    it('should return RateNoteService', () => {
      const service = serviceProvider.getRateNoteService();
      expect(service).toBeDefined();
    });

    it('should return RequestNoteService', () => {
      const service = serviceProvider.getRequestNoteService();
      expect(service).toBeDefined();
    });

    it('should return ListRequestsService', () => {
      const service = serviceProvider.getListRequestsService();
      expect(service).toBeDefined();
    });

    it('should return StatusService', () => {
      const service = serviceProvider.getStatusService();
      expect(service).toBeDefined();
    });

    it('should return GuildConfigService', () => {
      const service = serviceProvider.getGuildConfigService();
      expect(service).toBeDefined();
    });

    it('should return ScoringService', () => {
      const service = serviceProvider.getScoringService();
      expect(service).toBeDefined();
    });
  });

  describe('shutdown', () => {
    it('should be safe to call shutdown multiple times', () => {
      serviceProvider.shutdown();
      expect(() => serviceProvider.shutdown()).not.toThrow();
    });
  });

  describe('instance isolation', () => {
    it('should create independent instances', () => {
      const provider1 = new ServiceProvider(mockApiClient as any, asRedis(mockRedis));
      const provider2 = new ServiceProvider(mockApiClient as any, asRedis(mockRedis));

      expect(provider1.getWriteNoteService()).not.toBe(provider2.getWriteNoteService());

      provider1.shutdown();
      provider2.shutdown();
    });
  });
});
