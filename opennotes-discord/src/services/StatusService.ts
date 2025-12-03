import { ApiClient } from '../lib/api-client.js';
import { logger } from '../logger.js';
import {
  ServiceResult,
  StatusResult,
  ErrorCode,
  ServiceError,
} from './types.js';
import { getErrorMessage } from '../utils/error-handlers.js';

export interface CacheProvider {
  getMetrics(): { size: number };
}

export class StatusService {
  constructor(
    private apiClient: ApiClient,
    private cache: CacheProvider
  ) {}

  async execute(guilds?: number): Promise<ServiceResult<StatusResult>> {
    try {
      const startTime = Date.now();
      const serverHealth = await this.apiClient.healthCheck();
      const apiLatency = Date.now() - startTime;

      const uptime = process.uptime();

      const status: StatusResult = {
        bot: {
          uptime,
          cacheSize: this.cache.getMetrics().size,
          guilds,
        },
        server: {
          status: serverHealth.status,
          version: serverHealth.version,
          latency: apiLatency,
        },
      };

      logger.info('Status check completed', { status });

      return {
        success: true,
        data: status,
      };
    } catch (error: unknown) {
      logger.error('Failed to check status in service', { error: getErrorMessage(error) });

      return {
        success: false,
        error: this.mapError(error),
      };
    }
  }

  private mapError(_error: unknown): ServiceError {
    return {
      code: ErrorCode.API_ERROR,
      message: 'Unable to connect to the server. The bot is running but the API may be down.',
    };
  }
}
