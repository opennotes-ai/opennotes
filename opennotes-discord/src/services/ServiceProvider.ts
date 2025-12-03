import type { Redis } from 'ioredis';
import { ApiClient } from '../lib/api-client.js';
import { cache } from '../cache.js';
import { WriteNoteService } from './WriteNoteService.js';
import { ViewNotesService } from './ViewNotesService.js';
import { RateNoteService } from './RateNoteService.js';
import { RequestNoteService } from './RequestNoteService.js';
import { ListRequestsService } from './ListRequestsService.js';
import { StatusService } from './StatusService.js';
import { RateLimitFactory, RateLimiterInterface } from './RateLimitFactory.js';
import { GuildConfigService } from './GuildConfigService.js';
import { ScoringService } from './ScoringService.js';

export class ServiceProvider {
  private writeNoteService: WriteNoteService;
  private viewNotesService: ViewNotesService;
  private rateNoteService: RateNoteService;
  private requestNoteService: RequestNoteService;
  private listRequestsService: ListRequestsService;
  private statusService: StatusService;
  private guildConfigService: GuildConfigService;
  private scoringService: ScoringService;
  private writeRateLimiter: RateLimiterInterface;
  private rateRateLimiter: RateLimiterInterface;
  private requestRateLimiter: RateLimiterInterface;
  private viewRateLimiter: RateLimiterInterface;
  private listRateLimiter: RateLimiterInterface;

  constructor(apiClient: ApiClient, redis: Redis) {
    this.writeRateLimiter = RateLimitFactory.create(
      { useRedis: true, maxRequests: 5, windowSeconds: 60, keyPrefix: 'ratelimit:write' },
      redis
    );
    this.rateRateLimiter = RateLimitFactory.create(
      { useRedis: true, maxRequests: 10, windowSeconds: 60, keyPrefix: 'ratelimit:rate' },
      redis
    );
    this.requestRateLimiter = RateLimitFactory.create(
      { useRedis: true, maxRequests: 5, windowSeconds: 60, keyPrefix: 'ratelimit:request' },
      redis
    );
    this.viewRateLimiter = RateLimitFactory.create(
      { useRedis: true, maxRequests: 20, windowSeconds: 60, keyPrefix: 'ratelimit:view' },
      redis
    );
    this.listRateLimiter = RateLimitFactory.create(
      { useRedis: true, maxRequests: 20, windowSeconds: 60, keyPrefix: 'ratelimit:list' },
      redis
    );

    this.writeNoteService = new WriteNoteService(apiClient, this.writeRateLimiter);
    this.viewNotesService = new ViewNotesService(apiClient, this.viewRateLimiter);
    this.rateNoteService = new RateNoteService(apiClient, this.rateRateLimiter);
    this.requestNoteService = new RequestNoteService(apiClient, this.requestRateLimiter);
    this.listRequestsService = new ListRequestsService(apiClient, this.listRateLimiter);
    this.statusService = new StatusService(apiClient, cache);
    this.guildConfigService = new GuildConfigService(apiClient);
    this.scoringService = new ScoringService(apiClient);
  }

  getWriteNoteService(): WriteNoteService {
    return this.writeNoteService;
  }

  getViewNotesService(): ViewNotesService {
    return this.viewNotesService;
  }

  getRateNoteService(): RateNoteService {
    return this.rateNoteService;
  }

  getRequestNoteService(): RequestNoteService {
    return this.requestNoteService;
  }

  getListRequestsService(): ListRequestsService {
    return this.listRequestsService;
  }

  getStatusService(): StatusService {
    return this.statusService;
  }

  getGuildConfigService(): GuildConfigService {
    return this.guildConfigService;
  }

  getScoringService(): ScoringService {
    return this.scoringService;
  }

  shutdown(): void {
    // Redis rate limiters don't need cleanup - TTL handles expiration
  }
}
