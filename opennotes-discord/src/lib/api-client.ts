import type { components } from './generated-types.js';
import {
  Note,
  Rating,
  NoteRequest,
  CreateNoteRequest,
  CreateRatingRequest,
  ListRequestsFilters,
} from './types.js';
import {
  validateNoteCreate,
  validateNoteResponse,
  validateRatingCreate,
  validateRequestCreate,
  validateRequestResponse,
  validateRequestListResponse,
  validateScoringRequest,
  validateScoringResponse,
  validateRatingThresholdsResponse,
  validateHealthCheckResponse,
  validateNoteListResponse,
} from './schema-validator.js';
import { ApiError } from './errors.js';
import { logger } from '../logger.js';
import { getIdentityToken, isRunningOnGCP } from '../utils/gcp-auth.js';
import { createDiscordClaimsToken } from '../utils/discord-claims.js';

// Server API types from generated OpenAPI schema
export type NoteResponse = components['schemas']['NoteResponse'];
export type NoteCreate = components['schemas']['NoteCreate'];
export type RatingResponse = components['schemas']['RatingResponse'];
export type RequestResponse = components['schemas']['RequestResponse'];
export type RequestCreate = components['schemas']['RequestCreate'];
export type RequestListResponse = components['schemas']['RequestListResponse'];
export type NoteListResponse = components['schemas']['NoteListResponse'];
export type NoteStatus = components['schemas']['NoteStatus'];
export type RatingThresholdsResponse = components['schemas']['RatingThresholdsResponse'];
export type ScoringRequest = components['schemas']['ScoringRequest'];
export type ScoringResponse = components['schemas']['ScoringResponse'];
export type NoteScoreResponse = components['schemas']['NoteScoreResponse'];
export type TopNotesResponse = components['schemas']['TopNotesResponse'];
export type ScoringStatusResponse = components['schemas']['ScoringStatusResponse'];
export type ScoreConfidence = components['schemas']['ScoreConfidence'];
export type BatchScoreRequest = components['schemas']['BatchScoreRequest'];
export type BatchScoreResponse = components['schemas']['BatchScoreResponse'];
export type MonitoredChannelResponse = components['schemas']['MonitoredChannelResponse'];
export type MonitoredChannelCreate = components['schemas']['MonitoredChannelCreate'];
export type MonitoredChannelUpdate = components['schemas']['MonitoredChannelUpdate'];
export type MonitoredChannelListResponse = components['schemas']['MonitoredChannelListResponse'];
export type SimilaritySearchRequest = components['schemas']['src__fact_checking__embeddings_jsonapi_router__SimilaritySearchRequest'];
export type SimilaritySearchResponse = components['schemas']['SimilaritySearchResponse'];
export type FactCheckMatch = components['schemas']['FactCheckMatch'];
export type LLMConfigResponse = components['schemas']['LLMConfigResponse'];
export type LLMConfigCreate = components['schemas']['LLMConfigCreate'];
export type AddCommunityAdminRequest = components['schemas']['AddCommunityAdminRequest'];
export type CommunityAdminResponse = components['schemas']['CommunityAdminResponse'];
export type RemoveCommunityAdminResponse = components['schemas']['RemoveCommunityAdminResponse'];
export type PreviouslySeenCheckRequest = components['schemas']['src__fact_checking__previously_seen_jsonapi_router__PreviouslySeenCheckRequest'];
export type PreviouslySeenCheckResponse = components['schemas']['PreviouslySeenCheckResponse'];
export type PreviouslySeenMessageMatch = components['schemas']['PreviouslySeenMessageMatch'];
export type NotePublisherRecordRequest = components['schemas']['NotePublisherRecordRequest'];
export type NotePublisherConfigRequest = components['schemas']['NotePublisherConfigRequest'];
export type NotePublisherConfigResponse = components['schemas']['NotePublisherConfigResponse'];
export type DuplicateCheckResponse = components['schemas']['DuplicateCheckResponse'];
export type LastPostResponse = components['schemas']['LastPostResponse'];

// JSON:API v2 types from generated OpenAPI schema
export type NoteCreateRequest = components['schemas']['NoteCreateRequest'];
export type NoteCreateAttributes = components['schemas']['NoteCreateAttributes'];
export type RatingCreateRequest = components['schemas']['RatingCreateRequest'];
export type RatingCreateAttributes = components['schemas']['RatingCreateAttributes'];

// JSON:API generic types for parsing v2 responses
export interface JSONAPIResource<T> {
  type: string;
  id: string;
  attributes: T;
}

export interface JSONAPILinks {
  self?: string;
  first?: string;
  prev?: string;
  next?: string;
  last?: string;
}

export interface JSONAPIMeta {
  count?: number;
}

export interface JSONAPIListResponse<T> {
  data: JSONAPIResource<T>[];
  jsonapi: { version: string };
  links?: JSONAPILinks;
  meta?: JSONAPIMeta;
}

export interface JSONAPISingleResponse<T> {
  data: JSONAPIResource<T>;
  jsonapi: { version: string };
  links?: JSONAPILinks;
}

// Type for note attributes in JSON:API response (matches server NoteAttributes)
// Note: tweet_id has been removed - platform message ID now comes from the linked request
export interface NoteAttributes {
  summary: string;
  classification: string;
  status: NoteStatus;
  helpfulness_score: number;
  author_participant_id: string;
  community_server_id: string;
  channel_id?: string | null;
  request_id?: string | null;
  ratings_count: number;
  force_published: boolean;
  force_published_at?: string | null;
  ai_generated?: boolean;
  ai_provider?: string | null;
  created_at: string;
  updated_at?: string | null;
}

// Type for community server attributes in JSON:API response
export interface CommunityServerAttributes {
  platform: string;
  platform_id: string;
  name: string;
  description?: string | null;
  is_active: boolean;
  is_public: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

// Type for rating attributes in JSON:API response
export interface RatingAttributes {
  note_id: string;
  rater_participant_id: string;
  helpfulness_level: string;
  created_at?: string | null;
  updated_at?: string | null;
}

// Type for request attributes in JSON:API response
export interface RequestAttributes {
  request_id: string;
  requested_by: string;
  status: string;
  note_id?: string | null;
  community_server_id?: string | null;
  requested_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  content?: string | null;
  platform_message_id?: string | null;
  metadata?: Record<string, unknown> | null;
}

// Type for note score attributes in JSON:API response
export interface NoteScoreAttributes {
  score: number;
  confidence: string;
  algorithm: string;
  rating_count: number;
  tier: number;
  tier_name: string;
  calculated_at?: string | null;
  content?: string | null;
}

// Type for scoring status attributes in JSON:API response
export interface ScoringStatusAttributes {
  current_note_count: number;
  active_tier: {
    level: number;
    name: string;
    scorer_components: string[];
  };
  data_confidence: string;
  tier_thresholds: Record<string, {
    min: number;
    max: number | null;
    current: boolean;
  }>;
  next_tier_upgrade?: {
    tier: string;
    notes_needed: number;
    notes_to_upgrade: number;
  } | null;
  performance_metrics: {
    avg_scoring_time_ms: number;
    last_scoring_time_ms?: number | null;
    scorer_success_rate: number;
    total_scoring_operations: number;
    failed_scoring_operations: number;
  };
  warnings: string[];
  configuration: Record<string, unknown>;
}

// Type for monitored channel attributes in JSON:API response
export interface MonitoredChannelJSONAPIAttributes {
  community_server_id: string;
  channel_id: string;
  enabled: boolean;
  similarity_threshold: number;
  dataset_tags: string[];
  previously_seen_autopublish_threshold?: number | null;
  previously_seen_autorequest_threshold?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
  updated_by?: string | null;
}

// Type for note publisher config attributes in JSON:API response
export interface NotePublisherConfigJSONAPIAttributes {
  community_server_id: string;
  channel_id?: string | null;
  enabled: boolean;
  threshold?: number | null;
  updated_at?: string | null;
  updated_by?: string | null;
}

// Type for note publisher post attributes in JSON:API response
export interface NotePublisherPostJSONAPIAttributes {
  note_id: string;
  original_message_id: string;
  auto_post_message_id?: string | null;
  channel_id: string;
  community_server_id: string;
  score_at_post: number;
  confidence_at_post: string;
  posted_at?: string | null;
  success: boolean;
  error_message?: string | null;
}

// Type for previously seen message attributes in JSON:API response
export interface PreviouslySeenMessageJSONAPIAttributes {
  community_server_id: string;
  original_message_id: string;
  published_note_id: string;
  embedding_provider?: string | null;
  embedding_model?: string | null;
  extra_metadata?: Record<string, unknown> | null;
  created_at?: string | null;
}

// Type for previously seen match in check results
export interface PreviouslySeenMatchResource {
  id: string;
  community_server_id: string;
  original_message_id: string;
  published_note_id: string;
  embedding_provider?: string | null;
  embedding_model?: string | null;
  extra_metadata?: Record<string, unknown> | null;
  created_at?: string | null;
  similarity_score: number;
}

// Type for previously seen check result attributes
export interface PreviouslySeenCheckResultAttributes {
  should_auto_publish: boolean;
  should_auto_request: boolean;
  autopublish_threshold: number;
  autorequest_threshold: number;
  matches: PreviouslySeenMatchResource[];
  top_match?: PreviouslySeenMatchResource | null;
}

// Type for fact-check match in similarity search results
export interface FactCheckMatchResource {
  id: string;
  dataset_name: string;
  dataset_tags: string[];
  title: string;
  content: string;
  summary?: string | null;
  rating?: string | null;
  source_url?: string | null;
  published_date?: string | null;
  author?: string | null;
  embedding_provider?: string | null;
  embedding_model?: string | null;
  similarity_score: number;
}

// Type for similarity search result attributes
export interface SimilaritySearchResultAttributes {
  matches: FactCheckMatchResource[];
  query_text: string;
  dataset_tags: string[];
  similarity_threshold: number;
  rrf_score_threshold: number;
  total_matches: number;
}

// Extended type for note publisher config response that allows null id
export interface NotePublisherConfigResponseExtended {
  id: string | null;
  community_server_id: string;
  channel_id: string | null;
  enabled: boolean;
  threshold: number | null;
  updated_at: string | null;
  updated_by: string | null;
}

// Extended type for duplicate check response that matches v1 format for service compatibility
export interface DuplicateCheckResponseExtended {
  exists: boolean;
  note_publisher_post_id: string | null;
}

// Extended type for last post response that matches v1 format for service compatibility
export interface LastPostResponseExtended {
  posted_at: string;
  note_id: string;
  channel_id: string;
}

// Extended type for monitored channel response with id
export interface MonitoredChannelResponseExtended {
  id: string;
  community_server_id: string;
  channel_id: string;
  enabled: boolean;
  similarity_threshold: number;
  dataset_tags: string[];
  previously_seen_autopublish_threshold: number | null;
  previously_seen_autorequest_threshold: number | null;
  created_at: string | null;
  updated_at: string | null;
  updated_by: string | null;
}

// Extended type for monitored channel list response
export interface MonitoredChannelListResponseExtended {
  channels: MonitoredChannelResponseExtended[];
  total: number;
}

// Previously seen match type for service compatibility
export interface PreviouslySeenMatchExtended {
  id: string;
  community_server_id: string;
  original_message_id: string;
  published_note_id: string;
  embedding_provider?: string | null;
  embedding_model?: string | null;
  extra_metadata?: { [key: string]: string | number | boolean | null };
  created_at: string;
  similarity_score: number;
}

// Extended type for previously seen check response (camelCase for service compatibility)
export interface PreviouslySeenCheckResponseExtended {
  shouldAutoPublish: boolean;
  shouldAutoRequest: boolean;
  autopublishThreshold: number;
  autorequestThreshold: number;
  matches: PreviouslySeenMatchExtended[];
  topMatch?: PreviouslySeenMatchExtended | null;
}

export interface ApiClientConfig {
  serverUrl: string;
  apiKey?: string;
  internalServiceSecret?: string;
  retryAttempts?: number;
  retryDelayMs?: number;
  environment?: 'development' | 'production';
  requestTimeout?: number;
  maxResponseSize?: number;
}

export interface UserContext {
  userId: string;
  username?: string;
  displayName?: string;
  avatarUrl?: string;
  guildId?: string;
  channelId?: string;
  hasManageServer?: boolean;
}

export class ApiClient {
  private baseUrl: string;
  private apiKey?: string;
  private internalServiceSecret?: string;
  private retryAttempts: number;
  private retryDelayMs: number;
  private environment: 'development' | 'production';
  private requestTimeout: number;
  private maxResponseSize: number;
  private onGCP: boolean | null = null;
  private gcpDetectionPromise: Promise<void> | null = null;

  constructor(config: ApiClientConfig) {
    this.environment = config.environment ?? 'production';
    this.validateHttps(config.serverUrl);
    this.baseUrl = config.serverUrl;
    this.apiKey = config.apiKey;
    this.internalServiceSecret = config.internalServiceSecret;
    this.retryAttempts = config.retryAttempts ?? 3;
    this.retryDelayMs = config.retryDelayMs ?? 1000;
    this.requestTimeout = config.requestTimeout ?? 30000;
    this.maxResponseSize = config.maxResponseSize ?? 10 * 1024 * 1024;

    this.gcpDetectionPromise = this.detectGCPEnvironment();
  }

  private async detectGCPEnvironment(): Promise<void> {
    try {
      const result = await isRunningOnGCP();
      this.onGCP = result;
      if (result) {
        logger.info('Running on GCP - will use IAM authentication for server calls');
      } else {
        logger.info('Not running on GCP - using API key authentication only');
      }
    } catch {
      this.onGCP = false;
      logger.info('GCP detection failed - using API key authentication only');
    }
  }

  private async ensureGCPDetectionComplete(): Promise<void> {
    if (this.gcpDetectionPromise) {
      await this.gcpDetectionPromise;
      this.gcpDetectionPromise = null;
    }
  }

  private sanitizeForLogging(data: unknown): unknown {
    if (!data || typeof data !== 'object') {
      return data;
    }

    if (Array.isArray(data)) {
      return (data as unknown[]).map((item: unknown) => this.sanitizeForLogging(item));
    }

    const sensitiveFields = [
      'password',
      'token',
      'api_key',
      'apikey',
      'secret',
      'authorization',
      'cookie',
      'auth',
      'bearer',
      'session',
      'credential',
    ];

    const sanitized: Record<string, unknown> = {};
    for (const key of Object.keys(data as Record<string, unknown>)) {
      const lowerKey = String(key).toLowerCase();
      const isSensitive = sensitiveFields.some(field => lowerKey.includes(field));

      if (isSensitive) {
        sanitized[key] = '[REDACTED]';
      } else {
        const value = (data as Record<string, unknown>)[key];
        if (typeof value === 'object' && value !== null) {
          sanitized[key] = this.sanitizeForLogging(value);
        } else {
          sanitized[key] = (data as Record<string, unknown>)[key];
        }
      }
    }

    return sanitized;
  }

  private validateResponseSize(response: Response): void {
    const contentLength = response.headers.get('content-length');

    if (contentLength) {
      const size = parseInt(contentLength, 10);

      if (!isNaN(size) && size > this.maxResponseSize) {
        logger.error('Response size exceeds limit', {
          contentLength: size,
          maxResponseSize: this.maxResponseSize,
          url: response.url,
        });

        throw new ApiError(
          `Response size ${size} bytes exceeds maximum allowed size of ${this.maxResponseSize} bytes`,
          response.url,
          response.status,
          undefined,
          undefined,
          {
            contentLength: size,
            maxResponseSize: this.maxResponseSize,
          }
        );
      }

      if (!isNaN(size) && size > this.maxResponseSize * 0.8) {
        logger.warn('Response size approaching limit', {
          contentLength: size,
          maxResponseSize: this.maxResponseSize,
          url: response.url,
        });
      }
    }
  }

  private validateHttps(serverUrl: string): void {
    const url = new URL(serverUrl);

    if (url.protocol !== 'https:') {
      const isLocalhost = url.hostname === 'localhost' || url.hostname === '127.0.0.1' || url.hostname === '::1';

      if (this.environment === 'production' && !isLocalhost) {
        throw new Error(
          `HTTPS is required for production API connections. Current URL: ${serverUrl}`
        );
      }

      if (!isLocalhost && this.environment === 'development') {
        logger.warn('Non-HTTPS API connection detected in development', {
          serverUrl,
          protocol: url.protocol,
          environment: this.environment,
        });
      }
    }
  }

  private async fetchWithRetry<T>(
    endpoint: string,
    options: RequestInit = {},
    attempt = 1,
    context?: UserContext
  ): Promise<T> {
    await this.ensureGCPDetectionComplete();

    const url = `${this.baseUrl}${endpoint}`;

    let headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...options.headers as Record<string, string>,
    };

    if (this.apiKey) {
      headers['X-API-Key'] = this.apiKey;
    }

    if (this.internalServiceSecret) {
      headers['X-Internal-Auth'] = this.internalServiceSecret;
    }

    if (this.onGCP) {
      const identityToken = await getIdentityToken(this.baseUrl);
      if (identityToken) {
        headers['Authorization'] = `Bearer ${identityToken}`;
        logger.debug('Added IAM identity token to request', { endpoint });
      } else {
        logger.warn('Failed to get IAM identity token', { endpoint });
      }
    }

    headers = this.addProfileHeaders(headers, context);

    const requestBody = options.body ? (JSON.parse(options.body as string) as unknown) : undefined;

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.requestTimeout);

    try {
      logger.debug('API request', {
        endpoint,
        method: options.method || 'GET',
        attempt,
        url,
        timeout: this.requestTimeout,
      });

      const response = await fetch(url, {
        ...options,
        headers,
        signal: controller.signal,
      });

      clearTimeout(timeout);

      this.validateResponseSize(response);

      if (!response.ok) {
        let responseBody: unknown;
        const contentType = response.headers.get('content-type');

        try {
          if (contentType?.includes('application/json')) {
            responseBody = await response.json();
          } else {
            responseBody = await response.text();
          }
        } catch (parseError) {
          responseBody = 'Unable to parse response body';
        }

        logger.error('API request failed', {
          endpoint,
          method: options.method || 'GET',
          statusCode: response.status,
          statusText: response.statusText,
          responseBody: this.sanitizeForLogging(responseBody),
          requestBody: this.sanitizeForLogging(requestBody),
          attempt,
          maxAttempts: this.retryAttempts,
        });

        const apiError = new ApiError(
          `API request failed: ${response.status} ${response.statusText}`,
          endpoint,
          response.status,
          responseBody,
          requestBody,
          {
            method: options.method || 'GET',
            attempt,
            maxAttempts: this.retryAttempts,
          }
        );

        if (attempt < this.retryAttempts && this.shouldRetry(response.status)) {
          const delayMs = this.getRetryDelay(response, attempt);
          logger.info('Retrying API request', {
            endpoint,
            attempt: attempt + 1,
            maxAttempts: this.retryAttempts,
            delayMs,
            statusCode: response.status,
          });
          await this.delay(delayMs);
          return this.fetchWithRetry<T>(endpoint, options, attempt + 1, context);
        }

        throw apiError;
      }

      // Handle empty responses (204 No Content)
      if (response.status === 204) {
        logger.debug('API request successful (no content)', {
          endpoint,
          method: options.method || 'GET',
          statusCode: response.status,
        });
        return null as T;
      }

      const contentType = response.headers.get('content-type');
      const isJsonResponse = contentType?.includes('application/json') ||
        contentType?.includes('application/vnd.api+json');
      const responseData = isJsonResponse
        ? await response.json()
        : null;

      logger.debug('API request successful', {
        endpoint,
        method: options.method || 'GET',
        statusCode: response.status,
      });

      return responseData as T;
    } catch (error) {
      clearTimeout(timeout);

      if (error instanceof ApiError) {
        throw error;
      }

      const isAbortError = error instanceof Error && error.name === 'AbortError';

      if (isAbortError) {
        logger.error('API request timeout', {
          endpoint,
          method: options.method || 'GET',
          timeout: this.requestTimeout,
          attempt,
        });

        throw new ApiError(
          `API request timeout after ${this.requestTimeout}ms`,
          endpoint,
          0,
          undefined,
          requestBody,
          {
            method: options.method || 'GET',
            attempt,
            timeout: this.requestTimeout,
          }
        );
      }

      logger.error('API request exception', {
        endpoint,
        method: options.method || 'GET',
        error: error instanceof Error ? error.message : String(error),
        stack: error instanceof Error ? error.stack : undefined,
        attempt,
      });

      if (attempt < this.retryAttempts) {
        logger.info('Retrying after exception', {
          endpoint,
          attempt: attempt + 1,
          maxAttempts: this.retryAttempts,
        });
        await this.delay(this.retryDelayMs * attempt);
        return this.fetchWithRetry<T>(endpoint, options, attempt + 1, context);
      }

      throw new ApiError(
        `API request failed: ${error instanceof Error ? error.message : String(error)}`,
        endpoint,
        0,
        undefined,
        requestBody,
        {
          method: options.method || 'GET',
          attempt,
          originalError: error instanceof Error ? error.message : String(error),
        }
      );
    }
  }

  private getRetryDelay(response: Response, attempt: number): number {
    const retryAfter = response.headers.get('retry-after');

    if (retryAfter) {
      const seconds = parseInt(retryAfter, 10);
      if (!isNaN(seconds)) {
        const delayMs = seconds * 1000;
        logger.debug('Using Retry-After header (seconds)', {
          retryAfter,
          delayMs,
        });
        return Math.min(delayMs, 60000);
      }

      const retryDate = new Date(retryAfter);
      if (!isNaN(retryDate.getTime())) {
        const delayMs = Math.max(0, retryDate.getTime() - Date.now());
        logger.debug('Using Retry-After header (date)', {
          retryAfter,
          delayMs,
        });
        return Math.min(delayMs, 60000);
      }
    }

    const exponentialDelay = this.retryDelayMs * Math.pow(2, attempt - 1);
    return Math.min(exponentialDelay, 60000);
  }

  private shouldRetry(statusCode: number): boolean {
    return statusCode >= 500 || statusCode === 429 || statusCode === 408;
  }

  private delay(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  private addProfileHeaders(headers: Record<string, string>, context?: UserContext): Record<string, string> {
    if (!context) {
      return headers;
    }

    if (context.userId) {
      headers['X-Discord-User-Id'] = context.userId;
    }

    if (context.username) {
      headers['X-Discord-Username'] = context.username;
    }

    if (context.displayName) {
      headers['X-Discord-Display-Name'] = context.displayName;
    }

    if (context.avatarUrl) {
      headers['X-Discord-Avatar-Url'] = context.avatarUrl;
    }

    if (context.guildId) {
      headers['X-Guild-Id'] = context.guildId;
    }

    if (context.hasManageServer !== undefined) {
      headers['X-Discord-Has-Manage-Server'] = context.hasManageServer.toString();
    }

    const claimsToken = createDiscordClaimsToken(
      context.userId,
      context.guildId || '',
      context.hasManageServer ?? false
    );
    if (claimsToken) {
      headers['X-Discord-Claims'] = claimsToken;
    }

    return headers;
  }

  private buildJSONAPIRequestBody<T>(type: string, attributes: T): { data: { type: string; attributes: T } } {
    return {
      data: {
        type,
        attributes,
      },
    };
  }

  private buildJSONAPIUpdateBody<T>(
    type: string,
    id: string,
    attributes: T
  ): { data: { type: string; id: string; attributes: T } } {
    return {
      data: {
        type,
        id,
        attributes,
      },
    };
  }

  async healthCheck(): Promise<{ status: string; version: string }> {
    const response = await this.fetchWithRetry<{ status: string; version: string }>('/health');
    validateHealthCheckResponse(response);
    return response;
  }

  async scoreNotes(request: ScoringRequest): Promise<ScoringResponse> {
    validateScoringRequest(request);

    const response = await this.fetchWithRetry<ScoringResponse>('/api/v1/scoring/score', {
      method: 'POST',
      body: JSON.stringify(request),
    });

    validateScoringResponse(response);
    return response;
  }

  async getNotes(messageId: string): Promise<Note[]> {
    return this.fetchWithRetry<Note[]>(`/api/v1/notes/${messageId}`);
  }

  async getNote(noteId: string): Promise<NoteResponse> {
    const jsonApiResponse = await this.fetchWithRetry<JSONAPISingleResponse<NoteAttributes>>(
      `/api/v2/notes/${noteId}`
    );

    return {
      id: jsonApiResponse.data.id,
      summary: jsonApiResponse.data.attributes.summary,
      classification: jsonApiResponse.data.attributes.classification as components['schemas']['NoteClassification'],
      status: jsonApiResponse.data.attributes.status,
      helpfulness_score: jsonApiResponse.data.attributes.helpfulness_score,
      author_participant_id: jsonApiResponse.data.attributes.author_participant_id,
      community_server_id: jsonApiResponse.data.attributes.community_server_id,
      channel_id: jsonApiResponse.data.attributes.channel_id ?? null,
      request_id: jsonApiResponse.data.attributes.request_id ?? null,
      ratings_count: jsonApiResponse.data.attributes.ratings_count,
      force_published: jsonApiResponse.data.attributes.force_published,
      force_published_by: null,
      force_published_at: jsonApiResponse.data.attributes.force_published_at ?? null,
      created_at: jsonApiResponse.data.attributes.created_at,
      updated_at: jsonApiResponse.data.attributes.updated_at ?? null,
      ratings: [],
      request: null,
    };
  }

  async createNote(request: CreateNoteRequest, context?: UserContext): Promise<Note> {
    let community_server_id: string | undefined;
    if (context?.guildId) {
      try {
        const communityServer = await this.getCommunityServerByPlatformId(context.guildId);
        community_server_id = communityServer.id;
      } catch (error) {
        logger.error('Failed to lookup community server', {
          guildId: context.guildId,
          error: error instanceof Error ? error.message : String(error),
        });
        throw new ApiError(
          'Guild not registered. Please run /config content-monitor enable-all first.',
          '/api/v2/notes',
          400
        );
      }
    }

    const noteAttributes = {
      author_participant_id: request.authorId,
      channel_id: request.channelId || null,
      community_server_id,
      request_id: request.requestId || null,
      summary: request.content,
      classification: request.classification || 'NOT_MISLEADING',
    };

    validateNoteCreate(noteAttributes);

    const jsonApiRequest = this.buildJSONAPIRequestBody('notes', noteAttributes);

    const jsonApiResponse = await this.fetchWithRetry<JSONAPISingleResponse<NoteAttributes>>(
      '/api/v2/notes',
      {
        method: 'POST',
        body: JSON.stringify(jsonApiRequest),
      },
      1,
      context
    );

    return {
      id: jsonApiResponse.data.id,
      messageId: request.messageId,
      authorId: jsonApiResponse.data.attributes.author_participant_id,
      content: jsonApiResponse.data.attributes.summary,
      createdAt: new Date(jsonApiResponse.data.attributes.created_at).getTime(),
      helpfulCount: 0,
      notHelpfulCount: 0,
    };
  }

  async rateNote(request: CreateRatingRequest, context?: UserContext): Promise<Rating> {
    const ratingAttributes = {
      note_id: request.noteId,
      rater_participant_id: request.userId,
      helpfulness_level: request.helpful ? 'HELPFUL' : 'NOT_HELPFUL',
    };

    validateRatingCreate(ratingAttributes);

    const jsonApiRequest = this.buildJSONAPIRequestBody('ratings', ratingAttributes);

    const jsonApiResponse = await this.fetchWithRetry<JSONAPISingleResponse<RatingAttributes>>(
      '/api/v2/ratings',
      {
        method: 'POST',
        body: JSON.stringify(jsonApiRequest),
      },
      1,
      context
    );

    return {
      noteId: jsonApiResponse.data.attributes.note_id,
      userId: jsonApiResponse.data.attributes.rater_participant_id,
      helpful: jsonApiResponse.data.attributes.helpfulness_level === 'HELPFUL',
      createdAt: jsonApiResponse.data.attributes.created_at
        ? new Date(jsonApiResponse.data.attributes.created_at).getTime()
        : Date.now(),
    };
  }

  async requestNote(request: NoteRequest, context?: UserContext): Promise<void> {
    const requestId = `discord-${request.messageId}-${Date.now()}`;

    const requestAttributes: Record<string, unknown> = {
      request_id: requestId,
      community_server_id: request.community_server_id,
      original_message_content: request.originalMessageContent ?? null,
      requested_by: request.userId,
      platform_message_id: request.messageId,
      platform_channel_id: request.discord_channel_id ?? null,
      platform_author_id: request.discord_author_id ?? null,
      platform_timestamp: request.discord_timestamp?.toISOString() ?? null,
    };

    if (request.fact_check_metadata) {
      requestAttributes.metadata = request.fact_check_metadata;
    }

    validateRequestCreate(requestAttributes);

    const jsonApiRequest = this.buildJSONAPIRequestBody('requests', requestAttributes);

    await this.fetchWithRetry<JSONAPISingleResponse<RequestAttributes>>(
      '/api/v2/requests',
      {
        method: 'POST',
        body: JSON.stringify(jsonApiRequest),
      },
      1,
      context
    );
  }

  async listRequests(filters?: ListRequestsFilters, context?: UserContext): Promise<RequestListResponse> {
    const params = new URLSearchParams();

    if (filters?.page) { params.append('page[number]', filters.page.toString()); }
    if (filters?.size) { params.append('page[size]', filters.size.toString()); }
    if (filters?.status) { params.append('filter[status]', filters.status); }
    if (filters?.requestedBy) { params.append('filter[requested_by]', filters.requestedBy); }
    if (filters?.communityServerId) { params.append('filter[community_server_id]', filters.communityServerId); }

    const queryString = params.toString();
    const endpoint = queryString ? `/api/v2/requests?${queryString}` : '/api/v2/requests';

    const jsonApiResponse = await this.fetchWithRetry<JSONAPIListResponse<RequestAttributes>>(
      endpoint,
      {},
      1,
      context
    );

    const requests: RequestResponse[] = jsonApiResponse.data.map((resource) => ({
      id: resource.id,
      request_id: resource.attributes.request_id,
      requested_by: resource.attributes.requested_by,
      status: resource.attributes.status as components['schemas']['RequestStatus'],
      note_id: resource.attributes.note_id ?? undefined,
      community_server_id: resource.attributes.community_server_id ?? '',
      requested_at: resource.attributes.requested_at ?? new Date().toISOString(),
      created_at: resource.attributes.created_at ?? new Date().toISOString(),
      updated_at: resource.attributes.updated_at ?? undefined,
      platform_message_id: resource.attributes.platform_message_id ?? undefined,
      content: resource.attributes.content ?? undefined,
      metadata: resource.attributes.metadata ?? undefined,
    }));

    const response: RequestListResponse = {
      requests,
      total: jsonApiResponse.meta?.count ?? requests.length,
      page: filters?.page ?? 1,
      size: filters?.size ?? 20,
    };

    validateRequestListResponse(response);
    return response;
  }

  async getRequest(requestId: string, context?: UserContext): Promise<RequestResponse> {
    const endpoint = `/api/v2/requests/${encodeURIComponent(requestId)}`;
    const jsonApiResponse = await this.fetchWithRetry<JSONAPISingleResponse<RequestAttributes>>(
      endpoint,
      {},
      1,
      context
    );

    const response: RequestResponse = {
      id: jsonApiResponse.data.id,
      request_id: jsonApiResponse.data.attributes.request_id,
      requested_by: jsonApiResponse.data.attributes.requested_by,
      status: jsonApiResponse.data.attributes.status as components['schemas']['RequestStatus'],
      note_id: jsonApiResponse.data.attributes.note_id ?? undefined,
      community_server_id: jsonApiResponse.data.attributes.community_server_id ?? '',
      requested_at: jsonApiResponse.data.attributes.requested_at ?? new Date().toISOString(),
      created_at: jsonApiResponse.data.attributes.created_at ?? new Date().toISOString(),
      updated_at: jsonApiResponse.data.attributes.updated_at ?? undefined,
      platform_message_id: jsonApiResponse.data.attributes.platform_message_id ?? undefined,
      content: jsonApiResponse.data.attributes.content ?? undefined,
      metadata: jsonApiResponse.data.attributes.metadata ?? undefined,
    };

    validateRequestResponse(response);
    return response;
  }

  async generateAiNote(requestId: string, context?: UserContext): Promise<NoteResponse> {
    const endpoint = `/api/v1/requests/${encodeURIComponent(requestId)}/generate-ai-note`;
    const response = await this.fetchWithRetry<NoteResponse>(endpoint, {
      method: 'POST',
    }, 1, context);
    validateNoteResponse(response);
    return response;
  }

  async getCommunityServerByPlatformId(
    platformId: string,
    platform: string = 'discord'
  ): Promise<{ id: string; platform: string; platform_id: string; name: string; is_active: boolean }> {
    const params = new URLSearchParams();
    params.append('platform', platform);
    params.append('platform_id', platformId);

    const endpoint = `/api/v2/community-servers/lookup?${params.toString()}`;
    const jsonApiResponse = await this.fetchWithRetry<JSONAPISingleResponse<CommunityServerAttributes>>(endpoint);

    return {
      id: jsonApiResponse.data.id,
      platform: jsonApiResponse.data.attributes.platform,
      platform_id: jsonApiResponse.data.attributes.platform_id,
      name: jsonApiResponse.data.attributes.name,
      is_active: jsonApiResponse.data.attributes.is_active,
    };
  }

  async getRatingThresholds(): Promise<RatingThresholdsResponse> {
    const response = await this.fetchWithRetry<RatingThresholdsResponse>('/api/v1/config/rating-thresholds');
    validateRatingThresholdsResponse(response);
    return response;
  }

  async listNotesWithStatus(
    status: NoteStatus,
    page: number = 1,
    size: number = 20,
    communityServerId?: string,
    excludeRatedByParticipantId?: string,
    context?: UserContext
  ): Promise<NoteListResponse> {
    const params = new URLSearchParams();
    params.append('page[number]', page.toString());
    params.append('page[size]', size.toString());
    params.append('filter[status]', status);
    if (communityServerId) {
      params.append('filter[community_server_id]', communityServerId);
    }
    if (excludeRatedByParticipantId) {
      params.append('filter[rated_by_participant_id__not_in]', excludeRatedByParticipantId);
    }

    const jsonApiResponse = await this.fetchWithRetry<JSONAPIListResponse<NoteAttributes>>(
      `/api/v2/notes?${params.toString()}`,
      {},
      1,
      context
    );

    const response = this.transformJSONAPINoteListResponse(jsonApiResponse, page, size);
    validateNoteListResponse(response);
    return response;
  }

  private transformJSONAPINoteListResponse(
    jsonApiResponse: JSONAPIListResponse<NoteAttributes>,
    page: number,
    size: number
  ): NoteListResponse {
    const notes: NoteResponse[] = jsonApiResponse.data.map((resource) => ({
      id: resource.id,
      summary: resource.attributes.summary,
      classification: resource.attributes.classification as components['schemas']['NoteClassification'],
      status: resource.attributes.status,
      helpfulness_score: resource.attributes.helpfulness_score,
      author_participant_id: resource.attributes.author_participant_id,
      community_server_id: resource.attributes.community_server_id,
      channel_id: resource.attributes.channel_id ?? null,
      request_id: resource.attributes.request_id ?? null,
      ratings_count: resource.attributes.ratings_count,
      force_published: resource.attributes.force_published,
      force_published_by: null,
      force_published_at: resource.attributes.force_published_at ?? null,
      created_at: resource.attributes.created_at,
      updated_at: resource.attributes.updated_at ?? null,
      ratings: [],
      request: null,
    }));

    return {
      notes,
      total: jsonApiResponse.meta?.count ?? notes.length,
      page,
      size,
    };
  }

  async getRatingsForNote(noteId: string): Promise<RatingResponse[]> {
    const jsonApiResponse = await this.fetchWithRetry<JSONAPIListResponse<RatingAttributes>>(
      `/api/v2/notes/${noteId}/ratings`
    );

    return jsonApiResponse.data.map((resource) => ({
      id: resource.id,
      note_id: resource.attributes.note_id,
      rater_participant_id: resource.attributes.rater_participant_id,
      helpfulness_level: resource.attributes.helpfulness_level as components['schemas']['HelpfulnessLevel'],
      created_at: resource.attributes.created_at ?? new Date().toISOString(),
      updated_at: resource.attributes.updated_at ?? undefined,
    }));
  }

  async updateRating(ratingId: string, helpful: boolean, context?: UserContext): Promise<Rating> {
    const updateAttributes = {
      helpfulness_level: helpful ? 'HELPFUL' : 'NOT_HELPFUL',
    };

    const jsonApiRequest = this.buildJSONAPIUpdateBody('ratings', ratingId, updateAttributes);

    const jsonApiResponse = await this.fetchWithRetry<JSONAPISingleResponse<RatingAttributes>>(
      `/api/v2/ratings/${ratingId}`,
      {
        method: 'PUT',
        body: JSON.stringify(jsonApiRequest),
      },
      1,
      context
    );

    return {
      noteId: jsonApiResponse.data.attributes.note_id,
      userId: jsonApiResponse.data.attributes.rater_participant_id,
      helpful: jsonApiResponse.data.attributes.helpfulness_level === 'HELPFUL',
      createdAt: jsonApiResponse.data.attributes.created_at
        ? new Date(jsonApiResponse.data.attributes.created_at).getTime()
        : Date.now(),
    };
  }

  async getGuildConfig(guildId: string): Promise<Record<string, unknown>> {
    const response = await this.fetchWithRetry<{ community_id: string; config: Record<string, unknown> }>(
      `/api/v1/community-config/${guildId}`
    );
    return response.config;
  }

  async setGuildConfig(guildId: string, key: string, value: string | boolean | number, updatedBy: string, context?: UserContext): Promise<void> {
    await this.fetchWithRetry(`/api/v1/community-config/${guildId}`, {
      method: 'PUT',
      body: JSON.stringify({ key, value: String(value), updated_by: updatedBy }),
    }, 1, context);
  }

  async resetGuildConfig(guildId: string, context?: UserContext): Promise<void> {
    await this.fetchWithRetry(`/api/v1/community-config/${guildId}`, {
      method: 'DELETE',
    }, 1, context);
  }

  async getNoteScore(noteId: string): Promise<NoteScoreResponse> {
    const jsonApiResponse = await this.fetchWithRetry<JSONAPISingleResponse<NoteScoreAttributes>>(
      `/api/v2/scoring/notes/${noteId}/score`
    );

    return {
      note_id: jsonApiResponse.data.id,
      score: jsonApiResponse.data.attributes.score,
      confidence: jsonApiResponse.data.attributes.confidence as ScoreConfidence,
      algorithm: jsonApiResponse.data.attributes.algorithm,
      rating_count: jsonApiResponse.data.attributes.rating_count,
      tier: jsonApiResponse.data.attributes.tier,
      tier_name: jsonApiResponse.data.attributes.tier_name,
      calculated_at: jsonApiResponse.data.attributes.calculated_at ?? undefined,
      content: jsonApiResponse.data.attributes.content ?? undefined,
    };
  }

  async getBatchNoteScores(noteIds: string[]): Promise<BatchScoreResponse> {
    const batchAttributes = {
      note_ids: noteIds,
    };

    const jsonApiRequest = this.buildJSONAPIRequestBody('batch-score-requests', batchAttributes);

    const jsonApiResponse = await this.fetchWithRetry<JSONAPIListResponse<NoteScoreAttributes>>(
      '/api/v2/scoring/notes/batch-scores',
      {
        method: 'POST',
        body: JSON.stringify(jsonApiRequest),
      }
    );

    const scores: Record<string, NoteScoreResponse> = {};
    for (const resource of jsonApiResponse.data) {
      scores[resource.id] = {
        note_id: resource.id,
        score: resource.attributes.score,
        confidence: resource.attributes.confidence as ScoreConfidence,
        algorithm: resource.attributes.algorithm,
        rating_count: resource.attributes.rating_count,
        tier: resource.attributes.tier,
        tier_name: resource.attributes.tier_name,
        calculated_at: resource.attributes.calculated_at ?? undefined,
        content: resource.attributes.content ?? undefined,
      };
    }

    const meta = (jsonApiResponse as JSONAPIListResponse<NoteScoreAttributes> & { meta?: Record<string, unknown> }).meta;

    return {
      scores,
      total_requested: (meta?.total_requested as number) ?? noteIds.length,
      total_found: (meta?.total_found as number) ?? Object.keys(scores).length,
      not_found: (meta?.not_found as string[]) ?? [],
    };
  }

  async getTopNotes(
    limit?: number,
    minConfidence?: ScoreConfidence,
    tier?: number
  ): Promise<TopNotesResponse> {
    const params = new URLSearchParams();
    if (limit) { params.append('limit', limit.toString()); }
    if (minConfidence) { params.append('min_confidence', minConfidence); }
    if (tier !== undefined) { params.append('tier', tier.toString()); }

    const queryString = params.toString();
    const endpoint = queryString ? `/api/v2/scoring/notes/top?${queryString}` : '/api/v2/scoring/notes/top';

    const jsonApiResponse = await this.fetchWithRetry<JSONAPIListResponse<NoteScoreAttributes>>(endpoint);

    const notes: NoteScoreResponse[] = jsonApiResponse.data.map((resource) => ({
      note_id: resource.id,
      score: resource.attributes.score,
      confidence: resource.attributes.confidence as ScoreConfidence,
      algorithm: resource.attributes.algorithm,
      rating_count: resource.attributes.rating_count,
      tier: resource.attributes.tier,
      tier_name: resource.attributes.tier_name,
      calculated_at: resource.attributes.calculated_at ?? undefined,
      content: resource.attributes.content ?? undefined,
    }));

    const meta = (jsonApiResponse as JSONAPIListResponse<NoteScoreAttributes> & { meta?: Record<string, unknown> }).meta;

    return {
      notes,
      total_count: (meta?.total_count as number) ?? notes.length,
      current_tier: (meta?.current_tier as number) ?? 0,
      filters_applied: (meta?.filters_applied as Record<string, unknown>) ?? undefined,
    };
  }

  async getScoringStatus(): Promise<ScoringStatusResponse> {
    const jsonApiResponse = await this.fetchWithRetry<JSONAPISingleResponse<ScoringStatusAttributes>>(
      '/api/v2/scoring/status'
    );

    return {
      current_note_count: jsonApiResponse.data.attributes.current_note_count,
      active_tier: jsonApiResponse.data.attributes.active_tier,
      data_confidence: jsonApiResponse.data.attributes.data_confidence as components['schemas']['DataConfidence'],
      tier_thresholds: jsonApiResponse.data.attributes.tier_thresholds,
      next_tier_upgrade: jsonApiResponse.data.attributes.next_tier_upgrade ?? undefined,
      performance_metrics: jsonApiResponse.data.attributes.performance_metrics,
      warnings: jsonApiResponse.data.attributes.warnings,
      configuration: jsonApiResponse.data.attributes.configuration,
    };
  }

  async listMonitoredChannels(
    communityServerId?: string,
    enabledOnly: boolean = true
  ): Promise<MonitoredChannelListResponseExtended> {
    const params = new URLSearchParams();
    if (communityServerId) {
      params.append('filter[community_server_id]', communityServerId);
    }
    if (enabledOnly) {
      params.append('filter[enabled]', 'true');
    }
    params.append('page[size]', '100');

    const queryString = params.toString();
    const endpoint = `/api/v2/monitored-channels?${queryString}`;

    const jsonApiResponse = await this.fetchWithRetry<JSONAPIListResponse<MonitoredChannelJSONAPIAttributes>>(endpoint);

    const channels: MonitoredChannelResponseExtended[] = jsonApiResponse.data.map((resource) => ({
      id: resource.id,
      community_server_id: resource.attributes.community_server_id,
      channel_id: resource.attributes.channel_id,
      enabled: resource.attributes.enabled,
      similarity_threshold: resource.attributes.similarity_threshold,
      dataset_tags: resource.attributes.dataset_tags,
      previously_seen_autopublish_threshold: resource.attributes.previously_seen_autopublish_threshold ?? null,
      previously_seen_autorequest_threshold: resource.attributes.previously_seen_autorequest_threshold ?? null,
      created_at: resource.attributes.created_at ?? null,
      updated_at: resource.attributes.updated_at ?? null,
      updated_by: resource.attributes.updated_by ?? null,
    }));

    return {
      channels,
      total: jsonApiResponse.meta?.count ?? channels.length,
    };
  }

  async similaritySearch(
    text: string,
    communityServerId: string,
    datasetTags: string[] = ['snopes'],
    similarityThreshold?: number,
    limit: number = 5
  ): Promise<SimilaritySearchResponse> {
    const jsonApiRequest = this.buildJSONAPIRequestBody('similarity-searches', {
      text,
      community_server_id: communityServerId,
      dataset_tags: datasetTags,
      similarity_threshold: similarityThreshold,
      limit,
    });

    const jsonApiResponse = await this.fetchWithRetry<JSONAPISingleResponse<SimilaritySearchResultAttributes>>(
      '/api/v2/similarity-searches',
      {
        method: 'POST',
        body: JSON.stringify(jsonApiRequest),
      }
    );

    const attrs = jsonApiResponse.data.attributes;
    return {
      matches: attrs.matches.map((match) => ({
        id: match.id,
        dataset_name: match.dataset_name,
        dataset_tags: match.dataset_tags,
        title: match.title,
        content: match.content,
        summary: match.summary ?? null,
        rating: match.rating ?? null,
        source_url: match.source_url ?? null,
        published_date: match.published_date ?? null,
        author: match.author ?? null,
        embedding_provider: match.embedding_provider ?? null,
        embedding_model: match.embedding_model ?? null,
        similarity_score: match.similarity_score,
      })),
      query_text: attrs.query_text,
      dataset_tags: attrs.dataset_tags,
      similarity_threshold: attrs.similarity_threshold,
      rrf_score_threshold: attrs.rrf_score_threshold,
      total_matches: attrs.total_matches,
    };
  }

  async createMonitoredChannel(
    request: MonitoredChannelCreate,
    context?: UserContext
  ): Promise<MonitoredChannelResponseExtended | null> {
    try {
      const jsonApiRequest = this.buildJSONAPIRequestBody('monitored-channels', {
        community_server_id: request.community_server_id,
        channel_id: request.channel_id,
        enabled: request.enabled ?? true,
        similarity_threshold: request.similarity_threshold,
        dataset_tags: request.dataset_tags,
        updated_by: request.updated_by,
      });

      const jsonApiResponse = await this.fetchWithRetry<JSONAPISingleResponse<MonitoredChannelJSONAPIAttributes>>(
        '/api/v2/monitored-channels',
        {
          method: 'POST',
          body: JSON.stringify(jsonApiRequest),
        },
        1,
        context
      );

      return {
        id: jsonApiResponse.data.id,
        community_server_id: jsonApiResponse.data.attributes.community_server_id,
        channel_id: jsonApiResponse.data.attributes.channel_id,
        enabled: jsonApiResponse.data.attributes.enabled,
        similarity_threshold: jsonApiResponse.data.attributes.similarity_threshold,
        dataset_tags: jsonApiResponse.data.attributes.dataset_tags,
        previously_seen_autopublish_threshold: jsonApiResponse.data.attributes.previously_seen_autopublish_threshold ?? null,
        previously_seen_autorequest_threshold: jsonApiResponse.data.attributes.previously_seen_autorequest_threshold ?? null,
        created_at: jsonApiResponse.data.attributes.created_at ?? null,
        updated_at: jsonApiResponse.data.attributes.updated_at ?? null,
        updated_by: jsonApiResponse.data.attributes.updated_by ?? null,
      };
    } catch (error) {
      if (error instanceof ApiError && error.statusCode === 409) {
        logger.debug('Channel already monitored', {
          channelId: request.channel_id,
          communityServerId: request.community_server_id,
        });
        return null;
      }
      throw error;
    }
  }

  async listLLMConfigs(communityServerId: string): Promise<LLMConfigResponse[]> {
    return this.fetchWithRetry<LLMConfigResponse[]>(`/api/v1/community-servers/${communityServerId}/llm-config`);
  }

  async createLLMConfig(communityServerId: string, config: LLMConfigCreate, context?: UserContext): Promise<LLMConfigResponse> {
    return this.fetchWithRetry<LLMConfigResponse>(
      `/api/v1/community-servers/${communityServerId}/llm-config`,
      {
        method: 'POST',
        body: JSON.stringify(config),
      },
      1,
      context
    );
  }

  async getMonitoredChannelByUuid(uuid: string): Promise<MonitoredChannelResponseExtended> {
    const jsonApiResponse = await this.fetchWithRetry<JSONAPISingleResponse<MonitoredChannelJSONAPIAttributes>>(
      `/api/v2/monitored-channels/${uuid}`
    );

    return {
      id: jsonApiResponse.data.id,
      community_server_id: jsonApiResponse.data.attributes.community_server_id,
      channel_id: jsonApiResponse.data.attributes.channel_id,
      enabled: jsonApiResponse.data.attributes.enabled,
      similarity_threshold: jsonApiResponse.data.attributes.similarity_threshold,
      dataset_tags: jsonApiResponse.data.attributes.dataset_tags,
      previously_seen_autopublish_threshold: jsonApiResponse.data.attributes.previously_seen_autopublish_threshold ?? null,
      previously_seen_autorequest_threshold: jsonApiResponse.data.attributes.previously_seen_autorequest_threshold ?? null,
      created_at: jsonApiResponse.data.attributes.created_at ?? null,
      updated_at: jsonApiResponse.data.attributes.updated_at ?? null,
      updated_by: jsonApiResponse.data.attributes.updated_by ?? null,
    };
  }

  async getMonitoredChannel(channelId: string, communityServerId?: string): Promise<MonitoredChannelResponseExtended | null> {
    const response = await this.listMonitoredChannels(communityServerId, false);
    const channel = response.channels.find((ch) => ch.channel_id === channelId);
    return channel ?? null;
  }

  async updateMonitoredChannel(
    channelId: string,
    update: MonitoredChannelUpdate,
    context?: UserContext,
    communityServerId?: string
  ): Promise<MonitoredChannelResponseExtended | null> {
    const existing = await this.getMonitoredChannel(channelId, communityServerId);
    if (!existing) {
      return null;
    }

    const jsonApiRequest = {
      data: {
        type: 'monitored-channels',
        id: existing.id,
        attributes: {
          enabled: update.enabled,
          similarity_threshold: update.similarity_threshold,
          dataset_tags: update.dataset_tags,
          previously_seen_autopublish_threshold: update.previously_seen_autopublish_threshold,
          previously_seen_autorequest_threshold: update.previously_seen_autorequest_threshold,
          updated_by: update.updated_by,
        },
      },
    };

    const jsonApiResponse = await this.fetchWithRetry<JSONAPISingleResponse<MonitoredChannelJSONAPIAttributes>>(
      `/api/v2/monitored-channels/${existing.id}`,
      {
        method: 'PATCH',
        body: JSON.stringify(jsonApiRequest),
      },
      1,
      context
    );

    return {
      id: jsonApiResponse.data.id,
      community_server_id: jsonApiResponse.data.attributes.community_server_id,
      channel_id: jsonApiResponse.data.attributes.channel_id,
      enabled: jsonApiResponse.data.attributes.enabled,
      similarity_threshold: jsonApiResponse.data.attributes.similarity_threshold,
      dataset_tags: jsonApiResponse.data.attributes.dataset_tags,
      previously_seen_autopublish_threshold: jsonApiResponse.data.attributes.previously_seen_autopublish_threshold ?? null,
      previously_seen_autorequest_threshold: jsonApiResponse.data.attributes.previously_seen_autorequest_threshold ?? null,
      created_at: jsonApiResponse.data.attributes.created_at ?? null,
      updated_at: jsonApiResponse.data.attributes.updated_at ?? null,
      updated_by: jsonApiResponse.data.attributes.updated_by ?? null,
    };
  }

  async deleteMonitoredChannel(
    channelId: string,
    context?: UserContext,
    communityServerId?: string
  ): Promise<boolean> {
    const existing = await this.getMonitoredChannel(channelId, communityServerId);
    if (!existing) {
      return false;
    }

    await this.fetchWithRetry<void>(
      `/api/v2/monitored-channels/${existing.id}`,
      {
        method: 'DELETE',
      },
      1,
      context
    );

    return true;
  }

  async forcePublishNote(noteId: string, context?: UserContext): Promise<NoteResponse> {
    const jsonApiResponse = await this.fetchWithRetry<JSONAPISingleResponse<NoteAttributes>>(
      `/api/v2/notes/${noteId}/force-publish`,
      {
        method: 'POST',
      },
      1,
      context
    );

    return {
      id: jsonApiResponse.data.id,
      summary: jsonApiResponse.data.attributes.summary,
      classification: jsonApiResponse.data.attributes.classification as components['schemas']['NoteClassification'],
      status: jsonApiResponse.data.attributes.status,
      helpfulness_score: jsonApiResponse.data.attributes.helpfulness_score,
      author_participant_id: jsonApiResponse.data.attributes.author_participant_id,
      community_server_id: jsonApiResponse.data.attributes.community_server_id,
      channel_id: jsonApiResponse.data.attributes.channel_id ?? null,
      request_id: jsonApiResponse.data.attributes.request_id ?? null,
      ratings_count: jsonApiResponse.data.attributes.ratings_count,
      force_published: jsonApiResponse.data.attributes.force_published,
      force_published_by: null,
      force_published_at: jsonApiResponse.data.attributes.force_published_at ?? null,
      created_at: jsonApiResponse.data.attributes.created_at,
      updated_at: jsonApiResponse.data.attributes.updated_at ?? null,
      ratings: [],
      request: null,
    };
  }

  async addCommunityAdmin(
    communityServerId: string,
    userDiscordId: string,
    userMetadata?: {
      username?: string;
      display_name?: string;
      avatar_url?: string;
    },
    context?: UserContext
  ): Promise<CommunityAdminResponse> {
    const request: AddCommunityAdminRequest = {
      user_discord_id: userDiscordId,
      ...(userMetadata?.username && { username: userMetadata.username }),
      ...(userMetadata?.display_name && { display_name: userMetadata.display_name }),
      ...(userMetadata?.avatar_url && { avatar_url: userMetadata.avatar_url }),
    };

    return this.fetchWithRetry<CommunityAdminResponse>(
      `/api/v1/community-servers/${communityServerId}/admins`,
      {
        method: 'POST',
        body: JSON.stringify(request),
      },
      1,
      context
    );
  }

  async removeCommunityAdmin(
    communityServerId: string,
    userDiscordId: string,
    context?: UserContext
  ): Promise<RemoveCommunityAdminResponse> {
    return this.fetchWithRetry<RemoveCommunityAdminResponse>(
      `/api/v1/community-servers/${communityServerId}/admins/${userDiscordId}`,
      {
        method: 'DELETE',
      },
      1,
      context
    );
  }

  async listCommunityAdmins(communityServerId: string): Promise<CommunityAdminResponse[]> {
    return this.fetchWithRetry<CommunityAdminResponse[]>(
      `/api/v1/community-servers/${communityServerId}/admins`
    );
  }

  async checkPreviouslySeen(
    messageText: string,
    guildId: string,
    channelId: string
  ): Promise<PreviouslySeenCheckResponseExtended> {
    const jsonApiRequest = this.buildJSONAPIRequestBody('previously-seen-check', {
      message_text: messageText,
      guild_id: guildId,
      channel_id: channelId,
    });

    const jsonApiResponse = await this.fetchWithRetry<JSONAPISingleResponse<PreviouslySeenCheckResultAttributes>>(
      '/api/v2/previously-seen-messages/check',
      {
        method: 'POST',
        body: JSON.stringify(jsonApiRequest),
      }
    );

    const attrs = jsonApiResponse.data.attributes;

    const convertMatch = (m: PreviouslySeenMatchResource): PreviouslySeenMatchExtended => ({
      id: m.id,
      community_server_id: m.community_server_id,
      original_message_id: m.original_message_id,
      published_note_id: m.published_note_id,
      embedding_provider: m.embedding_provider ?? undefined,
      embedding_model: m.embedding_model ?? undefined,
      extra_metadata: m.extra_metadata as { [key: string]: string | number | boolean | null } | undefined,
      created_at: m.created_at ?? new Date().toISOString(),
      similarity_score: m.similarity_score,
    });

    return {
      shouldAutoPublish: attrs.should_auto_publish,
      shouldAutoRequest: attrs.should_auto_request,
      autopublishThreshold: attrs.autopublish_threshold,
      autorequestThreshold: attrs.autorequest_threshold,
      matches: attrs.matches.map(convertMatch),
      topMatch: attrs.top_match ? convertMatch(attrs.top_match) : undefined,
    };
  }

  async recordNotePublisher(
    request: NotePublisherRecordRequest
  ): Promise<void> {
    const jsonApiRequest = this.buildJSONAPIRequestBody('note-publisher-posts', {
      note_id: request.noteId,
      original_message_id: request.originalMessageId,
      channel_id: request.channelId,
      community_server_id: request.guildId,
      score_at_post: request.scoreAtPost,
      confidence_at_post: request.confidenceAtPost,
      success: request.success,
      error_message: request.errorMessage ?? null,
    });

    await this.fetchWithRetry<JSONAPISingleResponse<NotePublisherPostJSONAPIAttributes>>(
      '/api/v2/note-publisher-posts',
      {
        method: 'POST',
        body: JSON.stringify(jsonApiRequest),
      }
    );
  }

  async checkNoteDuplicate(originalMessageId: string, communityServerId: string): Promise<DuplicateCheckResponseExtended> {
    const params = new URLSearchParams();
    params.append('filter[community_server_id]', communityServerId);
    params.append('filter[original_message_id]', originalMessageId);
    params.append('page[size]', '1');

    const jsonApiResponse = await this.fetchWithRetry<JSONAPIListResponse<NotePublisherPostJSONAPIAttributes>>(
      `/api/v2/note-publisher-posts?${params.toString()}`
    );

    const existingPost = jsonApiResponse.data[0];

    return {
      exists: !!existingPost,
      note_publisher_post_id: existingPost?.id ?? null,
    };
  }

  async getLastNotePost(channelId: string, communityServerId: string): Promise<LastPostResponseExtended> {
    const params = new URLSearchParams();
    params.append('filter[community_server_id]', communityServerId);
    params.append('filter[channel_id]', channelId);
    params.append('filter[success]', 'true');
    params.append('page[size]', '1');
    params.append('sort', '-posted_at');

    const jsonApiResponse = await this.fetchWithRetry<JSONAPIListResponse<NotePublisherPostJSONAPIAttributes>>(
      `/api/v2/note-publisher-posts?${params.toString()}`
    );

    if (jsonApiResponse.data.length === 0) {
      const error = new Error('No previous post found');
      (error as Error & { statusCode?: number }).statusCode = 404;
      throw error;
    }

    const post = jsonApiResponse.data[0];
    return {
      posted_at: post.attributes.posted_at ?? new Date().toISOString(),
      note_id: post.attributes.note_id,
      channel_id: post.attributes.channel_id,
    };
  }

  async getNotePublisherConfig(
    guildId: string,
    channelId?: string
  ): Promise<NotePublisherConfigResponseExtended> {
    const params = new URLSearchParams();
    params.append('filter[community_server_id]', guildId);
    if (channelId) {
      params.append('page[size]', '100');
    } else {
      params.append('page[size]', '1');
    }

    const jsonApiResponse = await this.fetchWithRetry<JSONAPIListResponse<NotePublisherConfigJSONAPIAttributes>>(
      `/api/v2/note-publisher-configs?${params.toString()}`
    );

    const config = channelId
      ? jsonApiResponse.data.find((c) => c.attributes.channel_id === channelId)
        ?? jsonApiResponse.data.find((c) => c.attributes.channel_id === null)
      : jsonApiResponse.data.find((c) => c.attributes.channel_id === null)
        ?? jsonApiResponse.data[0];

    if (!config) {
      return {
        id: null,
        community_server_id: guildId,
        channel_id: channelId ?? null,
        enabled: false,
        threshold: null,
        updated_at: null,
        updated_by: null,
      };
    }

    return {
      id: config.id,
      community_server_id: config.attributes.community_server_id,
      channel_id: config.attributes.channel_id ?? null,
      enabled: config.attributes.enabled,
      threshold: config.attributes.threshold ?? null,
      updated_at: config.attributes.updated_at ?? null,
      updated_by: config.attributes.updated_by ?? null,
    };
  }

  async setNotePublisherConfig(
    guildId: string,
    enabled: boolean,
    threshold?: number,
    channelId?: string,
    updatedBy?: string,
    context?: UserContext
  ): Promise<NotePublisherConfigResponseExtended> {
    const existingConfig = await this.getNotePublisherConfig(guildId, channelId);

    if (existingConfig.id) {
      const jsonApiRequest = {
        data: {
          type: 'note-publisher-configs',
          id: existingConfig.id,
          attributes: {
            enabled,
            threshold: threshold ?? null,
            updated_by: updatedBy ?? null,
          },
        },
      };

      const jsonApiResponse = await this.fetchWithRetry<JSONAPISingleResponse<NotePublisherConfigJSONAPIAttributes>>(
        `/api/v2/note-publisher-configs/${existingConfig.id}`,
        {
          method: 'PATCH',
          body: JSON.stringify(jsonApiRequest),
        },
        1,
        context
      );

      return {
        id: jsonApiResponse.data.id,
        community_server_id: jsonApiResponse.data.attributes.community_server_id,
        channel_id: jsonApiResponse.data.attributes.channel_id ?? null,
        enabled: jsonApiResponse.data.attributes.enabled,
        threshold: jsonApiResponse.data.attributes.threshold ?? null,
        updated_at: jsonApiResponse.data.attributes.updated_at ?? null,
        updated_by: jsonApiResponse.data.attributes.updated_by ?? null,
      };
    } else {
      const jsonApiRequest = this.buildJSONAPIRequestBody('note-publisher-configs', {
        community_server_id: guildId,
        channel_id: channelId ?? null,
        enabled,
        threshold: threshold ?? null,
        updated_by: updatedBy ?? null,
      });

      const jsonApiResponse = await this.fetchWithRetry<JSONAPISingleResponse<NotePublisherConfigJSONAPIAttributes>>(
        '/api/v2/note-publisher-configs',
        {
          method: 'POST',
          body: JSON.stringify(jsonApiRequest),
        },
        1,
        context
      );

      return {
        id: jsonApiResponse.data.id,
        community_server_id: jsonApiResponse.data.attributes.community_server_id,
        channel_id: jsonApiResponse.data.attributes.channel_id ?? null,
        enabled: jsonApiResponse.data.attributes.enabled,
        threshold: jsonApiResponse.data.attributes.threshold ?? null,
        updated_at: jsonApiResponse.data.attributes.updated_at ?? null,
        updated_by: jsonApiResponse.data.attributes.updated_by ?? null,
      };
    }
  }

  async listNotesRatedByUser(
    raterParticipantId: string,
    page: number,
    size: number,
    communityServerId: string,
    statusFilter?: NoteStatus,
    context?: UserContext
  ): Promise<NoteListResponse> {
    const params = new URLSearchParams();
    params.append('rated_by_participant_id', raterParticipantId);
    params.append('page', page.toString());
    params.append('size', size.toString());
    params.append('community_server_id', communityServerId);

    if (statusFilter) {
      params.append('status', statusFilter);
    }

    const response = await this.fetchWithRetry<NoteListResponse>(
      `/api/v1/notes?${params.toString()}`,
      {},
      1,
      context
    );
    validateNoteListResponse(response);
    return response;
  }

  async initiateBulkScan(
    communityServerId: string,
    scanWindowDays: number
  ): Promise<{
    scan_id: string;
    status: string;
  }> {
    const response = await this.fetchWithRetry<{
      data: {
        type: string;
        id: string;
        attributes: {
          status: string;
          initiated_at: string;
          completed_at: string | null;
          messages_scanned: number;
          messages_flagged: number;
        };
      };
      jsonapi: { version: string };
    }>('/api/v2/bulk-scans', {
      method: 'POST',
      body: JSON.stringify({
        data: {
          type: 'bulk-scans',
          attributes: {
            community_server_id: communityServerId,
            scan_window_days: scanWindowDays,
          },
        },
      }),
    });
    return {
      scan_id: response.data.id,
      status: response.data.attributes.status,
    };
  }

  async getBulkScanResults(scanId: string): Promise<{
    scan_id: string;
    status: 'pending' | 'in_progress' | 'completed' | 'failed';
    messages_scanned: number;
    flagged_messages: Array<{
      message_id: string;
      channel_id: string;
      content: string;
      author_id: string;
      timestamp: string;
      match_score: number;
      matched_claim: string;
      matched_source: string;
    }>;
  }> {
    const response = await this.fetchWithRetry<{
      data: {
        type: string;
        id: string;
        attributes: {
          status: 'pending' | 'in_progress' | 'completed' | 'failed';
          messages_scanned: number;
          messages_flagged: number;
        };
      };
      included: Array<{
        type: string;
        id: string;
        attributes: {
          channel_id: string;
          content: string;
          author_id: string;
          timestamp: string;
          match_score: number;
          matched_claim: string;
          matched_source: string;
          scan_type: string;
        };
      }>;
      jsonapi: { version: string };
    }>(`/api/v2/bulk-scans/${scanId}`);

    return {
      scan_id: response.data.id,
      status: response.data.attributes.status,
      messages_scanned: response.data.attributes.messages_scanned,
      flagged_messages: (response.included || []).map((item) => ({
        message_id: item.id,
        channel_id: item.attributes.channel_id,
        content: item.attributes.content,
        author_id: item.attributes.author_id,
        timestamp: item.attributes.timestamp,
        match_score: item.attributes.match_score,
        matched_claim: item.attributes.matched_claim,
        matched_source: item.attributes.matched_source,
      })),
    };
  }

  async createNoteRequestsFromScan(
    scanId: string,
    messageIds: string[],
    generateAiNotes: boolean
  ): Promise<{
    created_count: number;
    request_ids: string[];
  }> {
    const response = await this.fetchWithRetry<{
      data: {
        type: string;
        id: string;
        attributes: {
          created_count: number;
          request_ids: string[];
        };
      };
      jsonapi: { version: string };
    }>(`/api/v2/bulk-scans/${scanId}/note-requests`, {
      method: 'POST',
      body: JSON.stringify({
        data: {
          type: 'note-requests',
          attributes: {
            message_ids: messageIds,
            generate_ai_notes: generateAiNotes,
          },
        },
      }),
    });
    return {
      created_count: response.data.attributes.created_count,
      request_ids: response.data.attributes.request_ids,
    };
  }

  async checkRecentScan(communityServerId: string): Promise<boolean> {
    const response = await this.fetchWithRetry<{
      data: {
        type: string;
        id: string;
        attributes: {
          has_recent_scan: boolean;
        };
      };
      jsonapi: { version: string };
    }>(`/api/v2/bulk-scans/communities/${communityServerId}/recent`);
    return response.data.attributes.has_recent_scan;
  }
}
