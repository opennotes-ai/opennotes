import { RatingThresholds } from './types.js';
import { ApiClient } from './api-client.js';
import { logger } from '../logger.js';

const CACHE_TTL_MS = 5 * 60 * 1000;
const FALLBACK_THRESHOLDS: RatingThresholds = {
  min_ratings_needed: 5,
  min_raters_per_note: 5,
};

export class ConfigCache {
  private cache: RatingThresholds | null = null;
  private lastFetch: number = 0;
  private apiClient: ApiClient;

  constructor(apiClient: ApiClient) {
    this.apiClient = apiClient;
  }

  async getRatingThresholds(): Promise<RatingThresholds> {
    const now = Date.now();

    if (this.cache && (now - this.lastFetch) < CACHE_TTL_MS) {
      logger.debug('Returning cached rating thresholds');
      return this.cache;
    }

    try {
      logger.debug('Fetching rating thresholds from server');
      const thresholds = await this.apiClient.getRatingThresholds();
      this.cache = thresholds;
      this.lastFetch = now;
      return thresholds;
    } catch (error) {
      logger.warn('Failed to fetch rating thresholds, using fallback', { error });
      return FALLBACK_THRESHOLDS;
    }
  }

  clearCache(): void {
    this.cache = null;
    this.lastFetch = 0;
  }
}
