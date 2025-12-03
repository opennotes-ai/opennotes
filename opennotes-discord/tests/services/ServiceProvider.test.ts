import { jest } from '@jest/globals';

process.env.DISCORD_TOKEN = 'test-token';
process.env.CLIENT_ID = 'test-client-id';
process.env.SERVER_URL = 'http://localhost:3000';
process.env.API_KEY = 'test-api-key';

const mockLogger = {
  info: jest.fn(),
  error: jest.fn(),
  warn: jest.fn(),
  debug: jest.fn(),
};

const mockCache = {
  get: jest.fn(),
  set: jest.fn(),
  delete: jest.fn(),
  clear: jest.fn(),
};

const mockRedis = {
  incr: jest.fn<() => Promise<number>>().mockResolvedValue(1),
  pexpire: jest.fn<() => Promise<number>>().mockResolvedValue(1),
  pttl: jest.fn<() => Promise<number>>().mockResolvedValue(60000),
  del: jest.fn<() => Promise<number>>().mockResolvedValue(1),
  keys: jest.fn<() => Promise<string[]>>().mockResolvedValue([]),
  info: jest.fn<() => Promise<string>>().mockResolvedValue('used_memory_human:1M'),
};

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
const { ApiClient } = await import('../../src/lib/api-client.js');

describe('ServiceProvider', () => {
  let serviceProvider: InstanceType<typeof ServiceProvider>;
  let mockApiClient: jest.Mocked<InstanceType<typeof ApiClient>>;

  beforeEach(() => {
    jest.clearAllMocks();

    mockApiClient = new ApiClient({
      serverUrl: 'http://localhost:3000',
      apiKey: 'test-token',
    }) as jest.Mocked<InstanceType<typeof ApiClient>>;
    serviceProvider = new ServiceProvider(mockApiClient, mockRedis as any);
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
      const provider1 = new ServiceProvider(mockApiClient, mockRedis as any);
      const provider2 = new ServiceProvider(mockApiClient, mockRedis as any);

      expect(provider1.getWriteNoteService()).not.toBe(provider2.getWriteNoteService());

      provider1.shutdown();
      provider2.shutdown();
    });
  });
});
