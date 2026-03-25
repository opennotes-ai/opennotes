import type { CacheInterface } from '../cache/interfaces.js';

export const NAV_STATE_TTL = 900;
const MAX_STACK_SIZE = 10;

export interface ScreenState {
  commandContext: string;
  components: unknown[];
  flags: number;
  content?: string;
  metadata?: Record<string, unknown>;
}

export class NavigationStateManager {
  private cache: CacheInterface;

  constructor(cache: CacheInterface) {
    this.cache = cache;
  }

  private key(userId: string, messageId: string): string {
    return `nav_state:${userId}:${messageId}`;
  }

  async push(userId: string, messageId: string, state: ScreenState): Promise<void> {
    const cacheKey = this.key(userId, messageId);
    const stack = (await this.cache.get<ScreenState[]>(cacheKey)) ?? [];
    stack.push(state);
    while (stack.length > MAX_STACK_SIZE) {
      stack.shift();
    }
    await this.cache.set(cacheKey, stack, NAV_STATE_TTL);
  }

  async pop(userId: string, messageId: string): Promise<ScreenState | null> {
    const cacheKey = this.key(userId, messageId);
    const stack = await this.cache.get<ScreenState[]>(cacheKey);
    if (!stack || stack.length === 0) {
      return null;
    }
    const state = stack.pop()!;
    await this.cache.set(cacheKey, stack, NAV_STATE_TTL);
    return state;
  }

  async peek(userId: string, messageId: string): Promise<ScreenState | null> {
    const cacheKey = this.key(userId, messageId);
    const stack = await this.cache.get<ScreenState[]>(cacheKey);
    if (!stack || stack.length === 0) {
      return null;
    }
    await this.cache.expire(cacheKey, NAV_STATE_TTL);
    return stack[stack.length - 1];
  }

  async clear(userId: string, messageId: string): Promise<void> {
    await this.cache.delete(this.key(userId, messageId));
  }
}
