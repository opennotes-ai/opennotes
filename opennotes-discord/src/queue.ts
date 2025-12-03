import { Client } from 'discord.js';
import { QueueManager } from './lib/queue-manager.js';
import { ConfigCache } from './lib/config-cache.js';
import { apiClient } from './api-client.js';

export const configCache = new ConfigCache(apiClient);

let queueManagerInstance: QueueManager | null = null;

export function initializeQueueManager(client: Client): void {
  queueManagerInstance = new QueueManager(client);
}

export function getQueueManager(): QueueManager {
  if (!queueManagerInstance) {
    throw new Error('QueueManager not initialized. Call initializeQueueManager first.');
  }
  return queueManagerInstance;
}
