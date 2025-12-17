import { ConfigCache } from './lib/config-cache.js';
import { apiClient } from './api-client.js';

export const configCache = new ConfigCache(apiClient);
