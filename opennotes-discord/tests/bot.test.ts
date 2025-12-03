import { jest } from '@jest/globals';
import { Client } from 'discord.js';

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

jest.unstable_mockModule('../src/redis-client.js', () => ({
  getRedisClient: mockGetRedisClient,
  closeRedisClient: mockCloseRedisClient,
}));

jest.unstable_mockModule('../src/services/index.js', () => ({
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

jest.unstable_mockModule('../src/logger.js', () => ({
  logger: mockLogger,
}));

jest.unstable_mockModule('../src/cache.js', () => ({
  cache: mockCache,
}));

jest.unstable_mockModule('../src/config.js', () => ({
  config: {
    serverUrl: 'http://localhost:8000',
    discordToken: 'test-token',
    clientId: 'test-client-id',
  },
}));

const { Bot } = await import('../src/bot.js');

describe('Bot', () => {
  let bot: any;

  beforeEach(() => {
    jest.clearAllMocks();
    bot = new Bot();
  });

  afterEach(async () => {
    if (bot && bot.isRunning()) {
      await bot.stop();
    }
  });

  describe('constructor', () => {
    it('should create a bot instance', () => {
      expect(bot).toBeDefined();
      expect(bot.isRunning()).toBe(false);
    });

    it('should load commands', () => {
      const client = bot.getClient();
      expect(client).toBeInstanceOf(Client);
    });
  });

  describe('command loading', () => {
    it('should have loaded all commands', () => {
      expect(mockLogger.info).toHaveBeenCalledWith(
        'Commands loaded',
        expect.objectContaining({ count: 6 })
      );
    });

    it('should load note command', () => {
      expect(mockLogger.debug).toHaveBeenCalledWith(
        'Loaded command',
        expect.objectContaining({ name: 'note' })
      );
    });

    it('should load config command', () => {
      expect(mockLogger.debug).toHaveBeenCalledWith(
        'Loaded command',
        expect.objectContaining({ name: 'config' })
      );
    });

    it('should load list command', () => {
      expect(mockLogger.debug).toHaveBeenCalledWith(
        'Loaded command',
        expect.objectContaining({ name: 'list' })
      );
    });

    it('should load status-bot command', () => {
      expect(mockLogger.debug).toHaveBeenCalledWith(
        'Loaded command',
        expect.objectContaining({ name: 'status-bot' })
      );
    });
  });

  describe('getClient', () => {
    it('should return the Discord client', () => {
      const client = bot.getClient();
      expect(client).toBeInstanceOf(Client);
    });
  });

  describe('isRunning', () => {
    it('should return false when bot is not started', () => {
      expect(bot.isRunning()).toBe(false);
    });
  });

  describe('stop', () => {
    it('should stop the bot gracefully', async () => {
      await bot.stop();

      expect(mockLogger.info).toHaveBeenCalledWith('Stopping bot');
      expect(mockCache.stop).toHaveBeenCalled();
      expect(bot.isRunning()).toBe(false);
    });

    it('should close Redis client during shutdown', async () => {
      await bot.stop();

      expect(mockCloseRedisClient).toHaveBeenCalled();
      expect(mockLogger.info).toHaveBeenCalledWith('Redis client closed');
    });
  });
});
