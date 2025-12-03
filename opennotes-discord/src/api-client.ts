import { config } from './config.js';
import { ApiClient } from './lib/api-client.js';

export { ApiClient };
export const apiClient = new ApiClient({
  serverUrl: config.serverUrl,
  apiKey: config.apiKey,
  internalServiceSecret: config.internalServiceSecret,
  environment: config.environment,
});
