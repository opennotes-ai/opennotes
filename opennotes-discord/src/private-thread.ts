import { Client } from 'discord.js';
import { PrivateThreadManager } from './lib/private-thread-manager.js';
import { ConfigCache } from './lib/config-cache.js';
import { apiClient } from './api-client.js';

export const configCache = new ConfigCache(apiClient);

let privateThreadManagerInstance: PrivateThreadManager | null = null;

export function initializePrivateThreadManager(client: Client): void {
  privateThreadManagerInstance = new PrivateThreadManager(client);
}

export function getPrivateThreadManager(): PrivateThreadManager {
  if (!privateThreadManagerInstance) {
    throw new Error('PrivateThreadManager not initialized. Call initializePrivateThreadManager first.');
  }
  return privateThreadManagerInstance;
}
