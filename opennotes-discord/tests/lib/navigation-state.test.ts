import { jest } from '@jest/globals';
import type { CacheInterface } from '../../src/cache/interfaces.js';
import {
  NavigationStateManager,
  NAV_STATE_TTL,
  type ScreenState,
} from '../../src/lib/navigation-state.js';

function buildMockCache(): jest.Mocked<CacheInterface> {
  return {
    get: jest.fn<CacheInterface['get']>(),
    set: jest.fn<CacheInterface['set']>(),
    delete: jest.fn<CacheInterface['delete']>(),
    exists: jest.fn<CacheInterface['exists']>(),
    expire: jest.fn<CacheInterface['expire']>(),
    mget: jest.fn<CacheInterface['mget']>(),
    mset: jest.fn<CacheInterface['mset']>(),
    clear: jest.fn<CacheInterface['clear']>(),
    ping: jest.fn<CacheInterface['ping']>(),
    getMetrics: jest.fn<CacheInterface['getMetrics']>(),
    start: jest.fn<CacheInterface['start']>(),
    stop: jest.fn<CacheInterface['stop']>(),
  } as jest.Mocked<CacheInterface>;
}

function buildScreenState(overrides: Partial<ScreenState> = {}): ScreenState {
  return {
    commandContext: 'list:notes',
    components: [{ type: 17 }],
    flags: 0,
    ...overrides,
  };
}

describe('NavigationStateManager', () => {
  let mockCache: jest.Mocked<CacheInterface>;
  let manager: NavigationStateManager;

  beforeEach(() => {
    mockCache = buildMockCache();
    mockCache.set.mockResolvedValue(true);
    mockCache.delete.mockResolvedValue(true);
    mockCache.expire.mockResolvedValue(true);
    manager = new NavigationStateManager(mockCache);
  });

  describe('NAV_STATE_TTL', () => {
    it('should be 900 seconds (15 minutes)', () => {
      expect(NAV_STATE_TTL).toBe(900);
    });
  });

  describe('push', () => {
    it('should create a new stack when none exists', async () => {
      mockCache.get.mockResolvedValue(null);
      const state = buildScreenState();

      await manager.push('user1', 'msg1', state);

      expect(mockCache.get).toHaveBeenCalledWith('nav_state:user1:msg1');
      expect(mockCache.set).toHaveBeenCalledWith(
        'nav_state:user1:msg1',
        [state],
        NAV_STATE_TTL,
      );
    });

    it('should append to an existing stack', async () => {
      const existing = buildScreenState({ commandContext: 'list:requests' });
      mockCache.get.mockResolvedValue([existing]);
      const newState = buildScreenState({ commandContext: 'note:view' });

      await manager.push('user1', 'msg1', newState);

      expect(mockCache.set).toHaveBeenCalledWith(
        'nav_state:user1:msg1',
        [existing, newState],
        NAV_STATE_TTL,
      );
    });

    it('should cap stack size at 10 by evicting oldest entries', async () => {
      const existingStack = Array.from({ length: 10 }, (_, i) =>
        buildScreenState({ commandContext: `screen:${i}` }),
      );
      mockCache.get.mockResolvedValue(existingStack);
      const newState = buildScreenState({ commandContext: 'screen:10' });

      await manager.push('user1', 'msg1', newState);

      const setCall = mockCache.set.mock.calls[0];
      const savedStack = setCall[1] as ScreenState[];
      expect(savedStack).toHaveLength(10);
      expect(savedStack[0].commandContext).toBe('screen:1');
      expect(savedStack[9].commandContext).toBe('screen:10');
    });

    it('should set TTL on every push', async () => {
      mockCache.get.mockResolvedValue(null);
      const state = buildScreenState();

      await manager.push('user1', 'msg1', state);

      expect(mockCache.set).toHaveBeenCalledWith(
        expect.any(String),
        expect.any(Array),
        NAV_STATE_TTL,
      );
    });

    it('should use correct key format with userId and messageId', async () => {
      mockCache.get.mockResolvedValue(null);
      const state = buildScreenState();

      await manager.push('abc123', 'xyz789', state);

      expect(mockCache.get).toHaveBeenCalledWith('nav_state:abc123:xyz789');
      expect(mockCache.set).toHaveBeenCalledWith(
        'nav_state:abc123:xyz789',
        expect.any(Array),
        NAV_STATE_TTL,
      );
    });
  });

  describe('pop', () => {
    it('should return null when no stack exists', async () => {
      mockCache.get.mockResolvedValue(null);

      const result = await manager.pop('user1', 'msg1');

      expect(result).toBeNull();
    });

    it('should return null when stack is empty', async () => {
      mockCache.get.mockResolvedValue([]);

      const result = await manager.pop('user1', 'msg1');

      expect(result).toBeNull();
    });

    it('should return and remove the last state from the stack', async () => {
      const first = buildScreenState({ commandContext: 'list:notes' });
      const second = buildScreenState({ commandContext: 'note:view' });
      mockCache.get.mockResolvedValue([first, second]);

      const result = await manager.pop('user1', 'msg1');

      expect(result).toEqual(second);
      expect(mockCache.set).toHaveBeenCalledWith(
        'nav_state:user1:msg1',
        [first],
        NAV_STATE_TTL,
      );
    });

    it('should refresh TTL on pop', async () => {
      const state = buildScreenState();
      mockCache.get.mockResolvedValue([state]);

      await manager.pop('user1', 'msg1');

      expect(mockCache.set).toHaveBeenCalledWith(
        expect.any(String),
        expect.any(Array),
        NAV_STATE_TTL,
      );
    });
  });

  describe('peek', () => {
    it('should return null when no stack exists', async () => {
      mockCache.get.mockResolvedValue(null);

      const result = await manager.peek('user1', 'msg1');

      expect(result).toBeNull();
    });

    it('should return null when stack is empty', async () => {
      mockCache.get.mockResolvedValue([]);

      const result = await manager.peek('user1', 'msg1');

      expect(result).toBeNull();
    });

    it('should return the last state without removing it', async () => {
      const first = buildScreenState({ commandContext: 'list:notes' });
      const second = buildScreenState({ commandContext: 'note:view' });
      mockCache.get.mockResolvedValue([first, second]);

      const result = await manager.peek('user1', 'msg1');

      expect(result).toEqual(second);
      expect(mockCache.set).not.toHaveBeenCalled();
    });

    it('should refresh TTL via expire on peek', async () => {
      const state = buildScreenState();
      mockCache.get.mockResolvedValue([state]);

      await manager.peek('user1', 'msg1');

      expect(mockCache.expire).toHaveBeenCalledWith(
        'nav_state:user1:msg1',
        NAV_STATE_TTL,
      );
    });
  });

  describe('clear', () => {
    it('should delete the stack key from cache', async () => {
      await manager.clear('user1', 'msg1');

      expect(mockCache.delete).toHaveBeenCalledWith('nav_state:user1:msg1');
    });
  });

  describe('ScreenState serialization', () => {
    it('should support metadata in screen state', async () => {
      mockCache.get.mockResolvedValue(null);
      const state = buildScreenState({
        metadata: { page: 2, filter: 'active' },
      });

      await manager.push('user1', 'msg1', state);

      const setCall = mockCache.set.mock.calls[0];
      const savedStack = setCall[1] as ScreenState[];
      expect(savedStack[0].metadata).toEqual({ page: 2, filter: 'active' });
    });

    it('should support flags in screen state', async () => {
      mockCache.get.mockResolvedValue(null);
      const state = buildScreenState({ flags: 64 });

      await manager.push('user1', 'msg1', state);

      const setCall = mockCache.set.mock.calls[0];
      const savedStack = setCall[1] as ScreenState[];
      expect(savedStack[0].flags).toBe(64);
    });

    it('should support complex component arrays', async () => {
      mockCache.get.mockResolvedValue(null);
      const components = [
        { type: 17, components: [{ type: 10, content: 'test' }] },
      ];
      const state = buildScreenState({ components });

      await manager.push('user1', 'msg1', state);

      const setCall = mockCache.set.mock.calls[0];
      const savedStack = setCall[1] as ScreenState[];
      expect(savedStack[0].components).toEqual(components);
    });
  });
});
