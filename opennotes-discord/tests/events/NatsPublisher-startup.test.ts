import { jest } from '@jest/globals';

const mockLogger = {
  error: jest.fn<(...args: unknown[]) => void>(),
  warn: jest.fn<(...args: unknown[]) => void>(),
  info: jest.fn<(...args: unknown[]) => void>(),
  debug: jest.fn<(...args: unknown[]) => void>(),
};

const mockCache = {
  get: jest.fn<(key: string) => unknown>(),
  set: jest.fn<(key: string, value: unknown, ttl?: number) => void>(),
  delete: jest.fn<(key: string) => void>(),
  start: jest.fn<() => void>(),
  stop: jest.fn<() => void>(),
};

const mockCloseRedisClient = jest.fn<() => void>();
const mockGetRedisClient = jest.fn(() => null);

const mockNatsPublisherConnect = jest.fn<() => Promise<void>>();
const mockNatsPublisherClose = jest.fn<() => Promise<void>>();
const mockNatsPublisherIsConnected = jest.fn<() => boolean>(() => false);

const mockNatsPublisherInstance = {
  connect: mockNatsPublisherConnect,
  close: mockNatsPublisherClose,
  isConnected: mockNatsPublisherIsConnected,
  publishBulkScanBatch: jest.fn<() => Promise<void>>(),
};

const mockInitializeNatsPublisher = jest.fn<() => Promise<typeof mockNatsPublisherInstance>>();
const mockCloseNatsPublisher = jest.fn<() => Promise<void>>();

jest.unstable_mockModule('../../src/redis-client.js', () => ({
  getRedisClient: mockGetRedisClient,
  closeRedisClient: mockCloseRedisClient,
}));

jest.unstable_mockModule('../../src/services/index.js', () => ({
  serviceProvider: {
    getRateLimitService: jest.fn(),
    getWriteNoteService: jest.fn(),
    getViewNotesService: jest.fn(),
    getRateNoteService: jest.fn(),
    getRequestNoteService: jest.fn(),
    getListRequestsService: jest.fn(),
    getStatusService: jest.fn(),
  },
}));

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
}));

jest.unstable_mockModule('../../src/cache.js', () => ({
  cache: mockCache,
}));

jest.unstable_mockModule('../../src/config.js', () => ({
  config: {
    serverUrl: 'http://localhost:8000',
    discordToken: 'test-token',
    clientId: 'test-client-id',
    healthCheck: {
      enabled: false,
      port: 3000,
    },
  },
}));

jest.unstable_mockModule('../../src/events/NatsPublisher.js', () => ({
  NatsPublisher: jest.fn(() => mockNatsPublisherInstance),
  getNatsPublisher: jest.fn(() => mockNatsPublisherInstance),
  initializeNatsPublisher: mockInitializeNatsPublisher,
  closeNatsPublisher: mockCloseNatsPublisher,
  natsPublisher: {
    publishBulkScanBatch: jest.fn(),
    isConnected: () => mockNatsPublisherIsConnected(),
  },
}));

const { Bot } = await import('../../src/bot.js');

describe('NATS Publisher Startup Initialization', () => {
  let bot: InstanceType<typeof Bot>;

  beforeEach(() => {
    jest.clearAllMocks();
    mockNatsPublisherConnect.mockResolvedValue(undefined);
    mockNatsPublisherClose.mockResolvedValue(undefined);
    mockNatsPublisherIsConnected.mockReturnValue(true);
    mockInitializeNatsPublisher.mockResolvedValue(mockNatsPublisherInstance);
    mockCloseNatsPublisher.mockResolvedValue(undefined);
    bot = new Bot();
  });

  afterEach(async () => {
    if (bot && bot.isRunning()) {
      await bot.stop();
    }
  });

  describe('AC#1: NATS connection is initialized during bot startup', () => {
    it('should call initializeNatsPublisher during bot.start()', async () => {
      const mockLogin = jest.spyOn(bot.getClient(), 'login').mockResolvedValue('token');

      try {
        await bot.start();
      } catch {
      }

      expect(mockInitializeNatsPublisher).toHaveBeenCalled();

      mockLogin.mockRestore();
    });

    it('should initialize NATS publisher BEFORE Discord login', async () => {
      const callOrder: string[] = [];

      mockInitializeNatsPublisher.mockImplementation(async () => {
        callOrder.push('nats_connect');
        return mockNatsPublisherInstance;
      });

      const mockLogin = jest.spyOn(bot.getClient(), 'login').mockImplementation(async () => {
        callOrder.push('discord_login');
        return 'token';
      });

      try {
        await bot.start();
      } catch {
      }

      expect(callOrder.indexOf('nats_connect')).toBeLessThan(callOrder.indexOf('discord_login'));

      mockLogin.mockRestore();
    });
  });

  describe('AC#2: Bot fails to start if NATS connection cannot be established', () => {
    it('should throw error and prevent bot startup when NATS connection fails', async () => {
      const connectionError = new Error('NATS connection refused');
      mockInitializeNatsPublisher.mockRejectedValue(connectionError);

      const mockLogin = jest.spyOn(bot.getClient(), 'login').mockResolvedValue('token');

      await expect(bot.start()).rejects.toThrow('NATS connection refused');

      expect(mockLogin).not.toHaveBeenCalled();

      mockLogin.mockRestore();
    });

    it('should not start cache or other services if NATS fails', async () => {
      const connectionError = new Error('NATS unavailable');
      mockInitializeNatsPublisher.mockRejectedValue(connectionError);

      const mockLogin = jest.spyOn(bot.getClient(), 'login').mockResolvedValue('token');

      try {
        await bot.start();
      } catch {
      }

      expect(mockCache.start).not.toHaveBeenCalled();

      mockLogin.mockRestore();
    });
  });

  describe('AC#3: Startup logs indicate NATS connection status', () => {
    it('should log NATS initialization attempt during startup', async () => {
      mockInitializeNatsPublisher.mockResolvedValue(mockNatsPublisherInstance);

      const mockLogin = jest.spyOn(bot.getClient(), 'login').mockResolvedValue('token');

      try {
        await bot.start();
      } catch {
      }

      expect(mockLogger.info).toHaveBeenCalledWith('Initializing NATS publisher connection');

      mockLogin.mockRestore();
    });

    it('should log NATS connection success during startup', async () => {
      mockInitializeNatsPublisher.mockResolvedValue(mockNatsPublisherInstance);

      const mockLogin = jest.spyOn(bot.getClient(), 'login').mockResolvedValue('token');

      try {
        await bot.start();
      } catch {
      }

      expect(mockLogger.info).toHaveBeenCalledWith('NATS publisher initialized successfully');

      mockLogin.mockRestore();
    });

    it('should log NATS connection failure during startup', async () => {
      const connectionError = new Error('Connection timeout');
      mockInitializeNatsPublisher.mockRejectedValue(connectionError);

      const mockLogin = jest.spyOn(bot.getClient(), 'login').mockResolvedValue('token');

      try {
        await bot.start();
      } catch {
      }

      expect(mockLogger.error).toHaveBeenCalledWith(
        'Failed to initialize NATS publisher - bot cannot start without NATS',
        expect.objectContaining({
          error: 'Connection timeout',
        })
      );

      mockLogin.mockRestore();
    });
  });

  describe('NATS cleanup on shutdown', () => {
    it('should close NATS publisher during bot.stop()', async () => {
      await bot.stop();

      expect(mockCloseNatsPublisher).toHaveBeenCalled();
    });

    it('should log NATS publisher closure during shutdown', async () => {
      await bot.stop();

      expect(mockLogger.info).toHaveBeenCalledWith('NATS publisher closed');
    });
  });
});
