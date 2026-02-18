import type { components } from './generated-types.js';
import {
  NoteRequest,
  CreateNoteRequest,
  CreateRatingRequest,
  ListRequestsFilters,
} from './types.js';
import {
  validateNoteCreate,
  validateRatingCreate,
  validateRequestCreate,
  validateScoringRequest,
  validateRatingThresholdsResponse,
  validateHealthCheckResponse,
} from './schema-validator.js';
import { ApiError } from './errors.js';
import { logger } from '../logger.js';
import { getIdentityToken, isRunningOnGCP } from '../utils/gcp-auth.js';
import { createDiscordClaimsToken } from '../utils/discord-claims.js';
import { nanoid } from 'nanoid';
import { resolveUserProfileId } from './user-profile-resolver.js';

// Types from generated OpenAPI schema
export type NoteStatus = components['schemas']['NoteStatus'];
export type NoteClassification = components['schemas']['NoteClassification'];
export type HelpfulnessLevel = components['schemas']['HelpfulnessLevel'];
export type RequestStatus = components['schemas']['RequestStatus'];
export type ScoreConfidence = components['schemas']['ScoreConfidence'];
export type RatingThresholdsResponse = components['schemas']['RatingThresholdsResponse'];
export type NoteData = components['schemas']['NoteData'];
export type RatingData = components['schemas']['RatingData'];
export type EnrollmentData = components['schemas']['EnrollmentData'];
export type AddCommunityAdminRequest = components['schemas']['AddCommunityAdminRequest'];
export type CommunityAdminResponse = components['schemas']['CommunityAdminResponse'];
export type RemoveCommunityAdminResponse = components['schemas']['RemoveCommunityAdminResponse'];
export type LLMConfigResponse = components['schemas']['LLMConfigResponse'];
export type LLMConfigCreate = components['schemas']['LLMConfigCreate'];
export type FlashpointDetectionUpdateResponse = components['schemas']['FlashpointDetectionUpdateResponse'];
export type ClaimRelevanceCheckResponse = components['schemas']['ClaimRelevanceCheckResponse'];
export type ClaimRelevanceCheckResultAttributes = components['schemas']['ClaimRelevanceCheckResultAttributes'];

export interface ClaimRelevanceResult {
  outcome: string;
  reasoning: string;
  shouldFlag: boolean;
}

export interface ClearPreviewResult {
  wouldDeleteCount: number;
  message: string;
}

export interface ClearResult {
  deletedCount: number;
  message: string;
}

// Local type definitions for API responses (flattened from JSON:API)
// These are used by services that expect flattened structures

export interface NoteResponse {
  id: string;
  summary: string;
  classification: NoteClassification;
  status: NoteStatus;
  helpfulness_score: number;
  author_id: string;  // User profile UUID
  community_server_id: string;
  channel_id: string | null;
  request_id: string | null;
  ratings_count: number;
  force_published: boolean;
  force_published_by: string | null;
  force_published_at: string | null;
  created_at: string;
  updated_at: string | null;
  ratings: RatingResponse[];
  request: RequestInfo | null;
}

export interface RatingResponse {
  id: string;
  note_id: string;
  rater_id: string;  // User profile UUID
  helpfulness_level: HelpfulnessLevel;
  created_at: string;
  updated_at?: string;
}

export interface RequestResponse {
  id: string;
  request_id: string;
  requested_by: string;
  status: RequestStatus;
  note_id?: string;
  community_server_id: string;
  requested_at: string;
  created_at: string;
  updated_at?: string;
  platform_message_id?: string;
  content?: string;
  metadata?: Record<string, unknown>;
}

export interface RequestInfo {
  request_id: string;
  content?: string | null;
  requested_by: string;
  requested_at: string;
}

export interface RequestListResponse {
  requests: RequestResponse[];
  total: number;
  page: number;
  size: number;
}

export interface NoteListResponse {
  notes: NoteResponse[];
  total: number;
  page: number;
  size: number;
}

export interface ScoringRequest {
  notes: NoteData[];
  ratings: RatingData[];
  enrollment: EnrollmentData[];
  status?: Record<string, unknown>[] | null;
}

export interface MonitoredChannelCreate {
  community_server_id: string;
  channel_id: string;
  name?: string | null;
  enabled?: boolean;
  similarity_threshold?: number;
  dataset_tags?: string[];
  updated_by?: string | null;
}

export interface MonitoredChannelUpdate {
  name?: string | null;
  enabled?: boolean;
  similarity_threshold?: number;
  dataset_tags?: string[];
  previously_seen_autopublish_threshold?: number | null;
  previously_seen_autorequest_threshold?: number | null;
  updated_by?: string;
}

export interface NotePublisherRecordRequest {
  noteId: string;
  originalMessageId: string;
  channelId: string;
  guildId: string;
  scoreAtPost: number;
  confidenceAtPost: string;
  success: boolean;
  errorMessage?: string | null;
  messageEmbedding?: unknown;
  embeddingProvider?: string | null;
  embeddingModel?: string | null;
}

// Bulk scan types from generated OpenAPI schema (JSONAPI structures)
export type LatestScanResponse = components['schemas']['LatestScanJSONAPIResponse'];
export type LatestScanResource = components['schemas']['LatestScanResource'];
export type LatestScanAttributes = components['schemas']['LatestScanAttributes'];
export type FlaggedMessageResource = components['schemas']['FlaggedMessageResource'];
export type FlaggedMessageAttributes = components['schemas']['FlaggedMessageAttributes'];
export type BulkScanSingleResponse = components['schemas']['BulkScanSingleResponse'];
export type BulkScanResultsResponse = components['schemas']['BulkScanResultsJSONAPIResponse'];
export type RecentScanResponse = components['schemas']['RecentScanResponse'];
export type NoteRequestsResultResponse = components['schemas']['NoteRequestsResultResponse'];
export type SimilarityMatch = components['schemas']['SimilarityMatch'];
export type OpenAIModerationMatch = components['schemas']['OpenAIModerationMatch'];
export type ConversationFlashpointMatch = components['schemas']['ConversationFlashpointMatch'];
export type MatchResult = SimilarityMatch | OpenAIModerationMatch | ConversationFlashpointMatch;
export type ScanErrorInfoSchema = components['schemas']['ScanErrorInfoSchema'];
export type ScanErrorSummarySchema = components['schemas']['ScanErrorSummarySchema'];
export type ExplanationResultResponse = components['schemas']['ExplanationResultResponse'];

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
  author_id: string;  // User profile UUID
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

// JSONAPI response types for notes - these are the raw structures from the server
export type NoteJSONAPIResponse = JSONAPISingleResponse<NoteAttributes>;
export type NoteListJSONAPIResponse = JSONAPIListResponse<NoteAttributes>;

// Extended list response with pagination info preserved from API
export interface NoteListJSONAPIResponseWithPagination extends NoteListJSONAPIResponse {
  total: number;
  page: number;
  size: number;
}

// Type for community server attributes in JSON:API response
export interface CommunityServerAttributes {
  platform: string;
  platform_community_server_id: string;
  name: string;
  description?: string | null;
  is_active: boolean;
  is_public: boolean;
  welcome_message_id?: string | null;
  flashpoint_detection_enabled: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface WelcomeMessageUpdateResponse {
  id: string;
  platform_community_server_id: string;
  welcome_message_id: string | null;
}

// JSONAPI response type for community servers - raw structure from the server
export type CommunityServerJSONAPIResponse = JSONAPISingleResponse<CommunityServerAttributes>;

// User profile lookup attributes for resolving Discord user IDs to UUIDs
export interface UserProfileLookupAttributes {
  platform: string;
  platform_user_id: string;
  display_name: string | null;
}

export type UserProfileLookupResponse = JSONAPISingleResponse<UserProfileLookupAttributes>;

// Type for rating attributes in JSON:API response
export interface RatingAttributes {
  note_id: string;
  rater_id: string;  // User profile UUID
  helpfulness_level: string;
  created_at?: string | null;
  updated_at?: string | null;
}

// JSONAPI response types for ratings - these are the raw structures from the server
export type RatingJSONAPIResponse = JSONAPISingleResponse<RatingAttributes>;
export type RatingListJSONAPIResponse = JSONAPIListResponse<RatingAttributes>;

// JSONAPI response type for previously-seen check - raw structure from the server
export type PreviouslySeenCheckJSONAPIResponse = JSONAPISingleResponse<PreviouslySeenCheckResultAttributes>;

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

// Meta types for batch and top notes responses
export interface BatchScoreMeta {
  total_requested?: number;
  total_found?: number;
  not_found?: string[];
}

export interface TopNotesMeta {
  total_count?: number;
  current_tier?: number;
  filters_applied?: Record<string, unknown>;
}

// JSONAPI response types for scoring - raw structures from the server
export type NoteScoreJSONAPIResponse = JSONAPISingleResponse<NoteScoreAttributes>;
export type ScoringResultJSONAPIResponse = JSONAPISingleResponse<ScoringResultAttributes>;

// Extended list response types with specific meta
export interface BatchScoreJSONAPIResponse extends Omit<JSONAPIListResponse<NoteScoreAttributes>, 'meta'> {
  meta?: JSONAPIMeta & BatchScoreMeta;
}

export interface TopNotesJSONAPIResponse extends Omit<JSONAPIListResponse<NoteScoreAttributes>, 'meta'> {
  meta?: JSONAPIMeta & TopNotesMeta;
}

export type ScoringStatusJSONAPIResponse = JSONAPISingleResponse<ScoringStatusAttributes>;

// Type for monitored channel attributes in JSON:API response
export interface MonitoredChannelJSONAPIAttributes {
  community_server_id: string;
  channel_id: string;
  name?: string | null;
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
  score_threshold: number;
  total_matches: number;
}

// Type for scoring result attributes in JSON:API v2 response
export interface ScoringResultAttributes {
  scored_notes: { [key: string]: unknown }[];
  helpful_scores: { [key: string]: unknown }[];
  auxiliary_info: { [key: string]: unknown }[];
}

// JSONAPI response type aliases for MonitoredChannel
export type MonitoredChannelJSONAPIResponse = JSONAPISingleResponse<MonitoredChannelJSONAPIAttributes>;
export type MonitoredChannelListJSONAPIResponse = JSONAPIListResponse<MonitoredChannelJSONAPIAttributes>;

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
    const requestId = nanoid();

    let headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'X-Request-Id': requestId,
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
        logger.debug('Added IAM identity token to request', { endpoint, requestId });
      } else {
        logger.warn('Failed to get IAM identity token', { endpoint, requestId });
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
        requestId,
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
          requestId,
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
            requestId,
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
          requestId,
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
        requestId,
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
          requestId,
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
        requestId,
      });

      if (attempt < this.retryAttempts) {
        logger.info('Retrying after exception', {
          endpoint,
          attempt: attempt + 1,
          maxAttempts: this.retryAttempts,
          requestId,
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

    if (context.channelId) {
      headers['X-Channel-Id'] = context.channelId;
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

  async scoreNotes(request: ScoringRequest): Promise<ScoringResultJSONAPIResponse> {
    validateScoringRequest(request);

    const jsonApiRequest = this.buildJSONAPIRequestBody('scoring-requests', request);

    return this.fetchWithRetry<ScoringResultJSONAPIResponse>(
      '/api/v2/scoring/score',
      {
        method: 'POST',
        body: JSON.stringify(jsonApiRequest),
      }
    );
  }

  async getNotes(messageId: string): Promise<NoteListJSONAPIResponse> {
    const params = new URLSearchParams();
    params.append('filter[platform_message_id]', messageId);

    return this.fetchWithRetry<NoteListJSONAPIResponse>(
      `/api/v2/notes?${params.toString()}`
    );
  }

  async getNote(noteId: string): Promise<NoteJSONAPIResponse> {
    return this.fetchWithRetry<NoteJSONAPIResponse>(`/api/v2/notes/${noteId}`);
  }

  async createNote(request: CreateNoteRequest, context?: UserContext): Promise<NoteJSONAPIResponse> {
    let community_server_id: string | undefined;
    if (context?.guildId) {
      try {
        const communityServer = await this.getCommunityServerByPlatformId(context.guildId);
        community_server_id = communityServer.data.id;
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

    // Resolve Discord user ID to user profile UUID
    let author_id: string;
    try {
      author_id = await resolveUserProfileId(request.authorId, this);
    } catch (error) {
      logger.error('Failed to resolve author user profile', {
        authorId: request.authorId,
        error: error instanceof Error ? error.message : String(error),
      });
      throw new ApiError(
        'Failed to resolve user profile. Please try again.',
        '/api/v2/notes',
        400
      );
    }

    const noteAttributes = {
      author_id,
      channel_id: request.channelId || null,
      community_server_id,
      request_id: request.requestId || null,
      summary: request.content,
      classification: request.classification || 'NOT_MISLEADING',
    };

    validateNoteCreate(noteAttributes);

    const jsonApiRequest = this.buildJSONAPIRequestBody('notes', noteAttributes);

    return this.fetchWithRetry<NoteJSONAPIResponse>(
      '/api/v2/notes',
      {
        method: 'POST',
        body: JSON.stringify(jsonApiRequest),
      },
      1,
      context
    );
  }

  async rateNote(request: CreateRatingRequest, context?: UserContext): Promise<RatingJSONAPIResponse> {
    // Resolve Discord user ID to user profile UUID
    let rater_id: string;
    try {
      rater_id = await resolveUserProfileId(request.userId, this);
    } catch (error) {
      logger.error('Failed to resolve rater user profile', {
        userId: request.userId,
        error: error instanceof Error ? error.message : String(error),
      });
      throw new ApiError(
        'Failed to resolve user profile. Please try again.',
        '/api/v2/ratings',
        400
      );
    }

    const ratingAttributes = {
      note_id: request.noteId,
      rater_id,
      helpfulness_level: request.helpful ? 'HELPFUL' : 'NOT_HELPFUL',
    };

    validateRatingCreate(ratingAttributes);

    const jsonApiRequest = this.buildJSONAPIRequestBody('ratings', ratingAttributes);

    return await this.fetchWithRetry<RatingJSONAPIResponse>(
      '/api/v2/ratings',
      {
        method: 'POST',
        body: JSON.stringify(jsonApiRequest),
      },
      1,
      context
    );
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
      requestAttributes.similarity_score = request.fact_check_metadata.similarity_score;
      requestAttributes.dataset_name = request.fact_check_metadata.dataset_name;
      requestAttributes.dataset_item_id = request.fact_check_metadata.dataset_item_id;
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

  async listRequests(filters?: ListRequestsFilters, context?: UserContext): Promise<JSONAPIListResponse<RequestAttributes>> {
    const params = new URLSearchParams();

    if (filters?.page) { params.append('page[number]', filters.page.toString()); }
    if (filters?.size) { params.append('page[size]', filters.size.toString()); }
    if (filters?.status) { params.append('filter[status]', filters.status); }
    if (filters?.requestedBy) { params.append('filter[requested_by]', filters.requestedBy); }
    if (filters?.communityServerId) { params.append('filter[community_server_id]', filters.communityServerId); }

    const queryString = params.toString();
    const endpoint = queryString ? `/api/v2/requests?${queryString}` : '/api/v2/requests';

    return this.fetchWithRetry<JSONAPIListResponse<RequestAttributes>>(
      endpoint,
      {},
      1,
      context
    );
  }

  async getRequest(requestId: string, context?: UserContext): Promise<JSONAPISingleResponse<RequestAttributes>> {
    const endpoint = `/api/v2/requests/${encodeURIComponent(requestId)}`;
    return this.fetchWithRetry<JSONAPISingleResponse<RequestAttributes>>(
      endpoint,
      {},
      1,
      context
    );
  }

  async generateAiNote(requestId: string, context?: UserContext): Promise<NoteJSONAPIResponse> {
    const endpoint = `/api/v2/requests/${encodeURIComponent(requestId)}/ai-notes`;

    return this.fetchWithRetry<NoteJSONAPIResponse>(
      endpoint,
      {
        method: 'POST',
      },
      1,
      context
    );
  }

  async getCommunityServerByPlatformId(
    platformId: string,
    platform: string = 'discord'
  ): Promise<CommunityServerJSONAPIResponse> {
    const params = new URLSearchParams();
    params.append('platform', platform);
    params.append('platform_community_server_id', platformId);

    const endpoint = `/api/v2/community-servers/lookup?${params.toString()}`;
    return this.fetchWithRetry<CommunityServerJSONAPIResponse>(endpoint);
  }

  async updateCommunityServerName(
    platformId: string,
    name: string,
    serverStats?: Record<string, unknown>
  ): Promise<void> {
    const body: Record<string, unknown> = { name };
    if (serverStats) {
      body.server_stats = serverStats;
    }
    await this.fetchWithRetry<void>(
      `/api/v2/community-servers/${encodeURIComponent(platformId)}/name`,
      {
        method: 'PATCH',
        body: JSON.stringify(body),
      }
    );
  }

  async getUserProfileByPlatformId(
    platformUserId: string,
    platform: string = 'discord'
  ): Promise<UserProfileLookupResponse> {
    const params = new URLSearchParams();
    params.append('platform', platform);
    params.append('platform_user_id', platformUserId);

    const endpoint = `/api/v2/user-profiles/lookup?${params.toString()}`;
    return this.fetchWithRetry<UserProfileLookupResponse>(endpoint);
  }

  async updateWelcomeMessageId(
    platformId: string,
    welcomeMessageId: string | null
  ): Promise<WelcomeMessageUpdateResponse> {
    const endpoint = `/api/v1/community-servers/${platformId}/welcome-message`;
    return this.fetchWithRetry<WelcomeMessageUpdateResponse>(endpoint, {
      method: 'PATCH',
      body: JSON.stringify({ welcome_message_id: welcomeMessageId }),
    });
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
  ): Promise<NoteListJSONAPIResponseWithPagination> {
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

    const jsonApiResponse = await this.fetchWithRetry<NoteListJSONAPIResponse>(
      `/api/v2/notes?${params.toString()}`,
      {},
      1,
      context
    );

    return {
      ...jsonApiResponse,
      total: jsonApiResponse.meta?.count ?? jsonApiResponse.data.length,
      page,
      size,
    };
  }

  async getRatingsForNote(noteId: string): Promise<RatingListJSONAPIResponse> {
    return await this.fetchWithRetry<RatingListJSONAPIResponse>(
      `/api/v2/notes/${noteId}/ratings`
    );
  }

  async updateRating(ratingId: string, helpful: boolean, context?: UserContext): Promise<RatingJSONAPIResponse> {
    const updateAttributes = {
      helpfulness_level: helpful ? 'HELPFUL' : 'NOT_HELPFUL',
    };

    const jsonApiRequest = this.buildJSONAPIUpdateBody('ratings', ratingId, updateAttributes);

    return await this.fetchWithRetry<RatingJSONAPIResponse>(
      `/api/v2/ratings/${ratingId}`,
      {
        method: 'PUT',
        body: JSON.stringify(jsonApiRequest),
      },
      1,
      context
    );
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

  async getNoteScore(noteId: string): Promise<NoteScoreJSONAPIResponse> {
    return this.fetchWithRetry<NoteScoreJSONAPIResponse>(
      `/api/v2/scoring/notes/${noteId}/score`
    );
  }

  async getBatchNoteScores(noteIds: string[]): Promise<BatchScoreJSONAPIResponse> {
    const batchAttributes = {
      note_ids: noteIds,
    };

    const jsonApiRequest = this.buildJSONAPIRequestBody('batch-score-requests', batchAttributes);

    return this.fetchWithRetry<BatchScoreJSONAPIResponse>(
      '/api/v2/scoring/notes/batch-scores',
      {
        method: 'POST',
        body: JSON.stringify(jsonApiRequest),
      }
    );
  }

  async getTopNotes(
    limit?: number,
    minConfidence?: ScoreConfidence,
    tier?: number
  ): Promise<TopNotesJSONAPIResponse> {
    const params = new URLSearchParams();
    if (limit) { params.append('limit', limit.toString()); }
    if (minConfidence) { params.append('min_confidence', minConfidence); }
    if (tier !== undefined) { params.append('tier', tier.toString()); }

    const queryString = params.toString();
    const endpoint = queryString ? `/api/v2/scoring/notes/top?${queryString}` : '/api/v2/scoring/notes/top';

    return this.fetchWithRetry<TopNotesJSONAPIResponse>(endpoint);
  }

  async getScoringStatus(): Promise<ScoringStatusJSONAPIResponse> {
    return this.fetchWithRetry<ScoringStatusJSONAPIResponse>(
      '/api/v2/scoring/status'
    );
  }

  async listMonitoredChannels(
    communityServerId?: string,
    enabledOnly: boolean = true
  ): Promise<JSONAPIListResponse<MonitoredChannelJSONAPIAttributes>> {
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

    return this.fetchWithRetry<JSONAPIListResponse<MonitoredChannelJSONAPIAttributes>>(endpoint);
  }

  async similaritySearch(
    text: string,
    communityServerId: string,
    datasetTags: string[] = ['snopes'],
    similarityThreshold?: number,
    limit: number = 5
  ): Promise<JSONAPISingleResponse<SimilaritySearchResultAttributes>> {
    const jsonApiRequest = this.buildJSONAPIRequestBody('similarity-searches', {
      text,
      community_server_id: communityServerId,
      dataset_tags: datasetTags,
      similarity_threshold: similarityThreshold,
      limit,
    });

    return this.fetchWithRetry<JSONAPISingleResponse<SimilaritySearchResultAttributes>>(
      '/api/v2/similarity-searches',
      {
        method: 'POST',
        body: JSON.stringify(jsonApiRequest),
      }
    );
  }

  async createMonitoredChannel(
    request: MonitoredChannelCreate,
    context?: UserContext
  ): Promise<JSONAPISingleResponse<MonitoredChannelJSONAPIAttributes> | null> {
    try {
      const jsonApiRequest = this.buildJSONAPIRequestBody('monitored-channels', {
        community_server_id: request.community_server_id,
        channel_id: request.channel_id,
        name: request.name ?? null,
        enabled: request.enabled ?? true,
        similarity_threshold: request.similarity_threshold,
        dataset_tags: request.dataset_tags,
        updated_by: request.updated_by,
      });

      return await this.fetchWithRetry<JSONAPISingleResponse<MonitoredChannelJSONAPIAttributes>>(
        '/api/v2/monitored-channels',
        {
          method: 'POST',
          body: JSON.stringify(jsonApiRequest),
        },
        1,
        context
      );
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

  async getMonitoredChannelByUuid(uuid: string): Promise<JSONAPISingleResponse<MonitoredChannelJSONAPIAttributes>> {
    return this.fetchWithRetry<JSONAPISingleResponse<MonitoredChannelJSONAPIAttributes>>(
      `/api/v2/monitored-channels/${uuid}`
    );
  }

  async getMonitoredChannel(channelId: string, communityServerId?: string): Promise<JSONAPISingleResponse<MonitoredChannelJSONAPIAttributes> | null> {
    const response = await this.listMonitoredChannels(communityServerId, false);
    const resource = response.data.find((r) => r.attributes.channel_id === channelId);
    if (!resource) {
      return null;
    }
    return {
      data: resource,
      jsonapi: response.jsonapi,
      links: response.links,
    };
  }

  async updateMonitoredChannel(
    channelId: string,
    update: MonitoredChannelUpdate,
    context?: UserContext,
    communityServerId?: string
  ): Promise<JSONAPISingleResponse<MonitoredChannelJSONAPIAttributes> | null> {
    const existing = await this.getMonitoredChannel(channelId, communityServerId);
    if (!existing) {
      return null;
    }

    const jsonApiRequest = {
      data: {
        type: 'monitored-channels',
        id: existing.data.id,
        attributes: {
          name: update.name,
          enabled: update.enabled,
          similarity_threshold: update.similarity_threshold,
          dataset_tags: update.dataset_tags,
          previously_seen_autopublish_threshold: update.previously_seen_autopublish_threshold,
          previously_seen_autorequest_threshold: update.previously_seen_autorequest_threshold,
          updated_by: update.updated_by,
        },
      },
    };

    return this.fetchWithRetry<JSONAPISingleResponse<MonitoredChannelJSONAPIAttributes>>(
      `/api/v2/monitored-channels/${existing.data.id}`,
      {
        method: 'PATCH',
        body: JSON.stringify(jsonApiRequest),
      },
      1,
      context
    );
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
      `/api/v2/monitored-channels/${existing.data.id}`,
      {
        method: 'DELETE',
      },
      1,
      context
    );

    return true;
  }

  async forcePublishNote(noteId: string, context?: UserContext): Promise<NoteJSONAPIResponse> {
    return this.fetchWithRetry<NoteJSONAPIResponse>(
      `/api/v2/notes/${noteId}/force-publish`,
      {
        method: 'POST',
      },
      1,
      context
    );
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
  ): Promise<PreviouslySeenCheckJSONAPIResponse> {
    const jsonApiRequest = this.buildJSONAPIRequestBody('previously-seen-check', {
      message_text: messageText,
      platform_community_server_id: guildId,
      channel_id: channelId,
    });

    return this.fetchWithRetry<PreviouslySeenCheckJSONAPIResponse>(
      '/api/v2/previously-seen-messages/check',
      {
        method: 'POST',
        body: JSON.stringify(jsonApiRequest),
      }
    );
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

  async checkNoteDuplicate(
    originalMessageId: string,
    communityServerId: string
  ): Promise<JSONAPIListResponse<NotePublisherPostJSONAPIAttributes>> {
    const params = new URLSearchParams();
    params.append('filter[community_server_id]', communityServerId);
    params.append('filter[original_message_id]', originalMessageId);
    params.append('page[size]', '1');

    return this.fetchWithRetry<JSONAPIListResponse<NotePublisherPostJSONAPIAttributes>>(
      `/api/v2/note-publisher-posts?${params.toString()}`
    );
  }

  async getLastNotePost(
    channelId: string,
    communityServerId: string
  ): Promise<JSONAPIListResponse<NotePublisherPostJSONAPIAttributes>> {
    const params = new URLSearchParams();
    params.append('filter[community_server_id]', communityServerId);
    params.append('filter[channel_id]', channelId);
    params.append('filter[success]', 'true');
    params.append('page[size]', '1');
    params.append('sort', '-posted_at');

    return this.fetchWithRetry<JSONAPIListResponse<NotePublisherPostJSONAPIAttributes>>(
      `/api/v2/note-publisher-posts?${params.toString()}`
    );
  }

  async getNotePublisherConfig(
    guildId: string,
    channelId?: string
  ): Promise<JSONAPIListResponse<NotePublisherConfigJSONAPIAttributes>> {
    const params = new URLSearchParams();
    params.append('filter[community_server_id]', guildId);
    if (channelId) {
      params.append('page[size]', '100');
    } else {
      params.append('page[size]', '1');
    }

    return this.fetchWithRetry<JSONAPIListResponse<NotePublisherConfigJSONAPIAttributes>>(
      `/api/v2/note-publisher-configs?${params.toString()}`
    );
  }

  async setNotePublisherConfig(
    guildId: string,
    enabled: boolean,
    threshold?: number,
    channelId?: string,
    updatedBy?: string,
    context?: UserContext
  ): Promise<JSONAPISingleResponse<NotePublisherConfigJSONAPIAttributes>> {
    const existingConfigResponse = await this.getNotePublisherConfig(guildId, channelId);

    const existingConfig = channelId
      ? existingConfigResponse.data.find((c) => c.attributes.channel_id === channelId)
        ?? existingConfigResponse.data.find((c) => c.attributes.channel_id === null)
      : existingConfigResponse.data.find((c) => c.attributes.channel_id === null)
        ?? existingConfigResponse.data[0];

    if (existingConfig) {
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

      return this.fetchWithRetry<JSONAPISingleResponse<NotePublisherConfigJSONAPIAttributes>>(
        `/api/v2/note-publisher-configs/${existingConfig.id}`,
        {
          method: 'PATCH',
          body: JSON.stringify(jsonApiRequest),
        },
        1,
        context
      );
    } else {
      const jsonApiRequest = this.buildJSONAPIRequestBody('note-publisher-configs', {
        community_server_id: guildId,
        channel_id: channelId ?? null,
        enabled,
        threshold: threshold ?? null,
        updated_by: updatedBy ?? null,
      });

      return this.fetchWithRetry<JSONAPISingleResponse<NotePublisherConfigJSONAPIAttributes>>(
        '/api/v2/note-publisher-configs',
        {
          method: 'POST',
          body: JSON.stringify(jsonApiRequest),
        },
        1,
        context
      );
    }
  }

  async listNotesRatedByUser(
    raterParticipantId: string,
    page: number,
    size: number,
    communityServerId: string,
    statusFilter?: NoteStatus,
    context?: UserContext
  ): Promise<NoteListJSONAPIResponseWithPagination> {
    const params = new URLSearchParams();
    params.append('page[number]', page.toString());
    params.append('page[size]', size.toString());
    params.append('filter[rated_by_participant_id]', raterParticipantId);
    params.append('filter[community_server_id]', communityServerId);

    if (statusFilter) {
      params.append('filter[status]', statusFilter);
    }

    const jsonApiResponse = await this.fetchWithRetry<NoteListJSONAPIResponse>(
      `/api/v2/notes?${params.toString()}`,
      {},
      1,
      context
    );

    return {
      ...jsonApiResponse,
      total: jsonApiResponse.meta?.count ?? jsonApiResponse.data.length,
      page,
      size,
    };
  }

  async initiateBulkScan(
    communityServerId: string,
    scanWindowDays: number
  ): Promise<BulkScanSingleResponse> {
    return this.fetchWithRetry<BulkScanSingleResponse>('/api/v2/bulk-scans', {
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
  }

  async getBulkScanResults(scanId: string): Promise<BulkScanResultsResponse> {
    return this.fetchWithRetry<BulkScanResultsResponse>(`/api/v2/bulk-scans/${scanId}`);
  }

  async createNoteRequestsFromScan(
    scanId: string,
    messageIds: string[],
    generateAiNotes: boolean
  ): Promise<NoteRequestsResultResponse> {
    return this.fetchWithRetry<NoteRequestsResultResponse>(`/api/v2/bulk-scans/${scanId}/note-requests`, {
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
  }

  async checkRecentScan(communityServerId: string): Promise<RecentScanResponse> {
    return this.fetchWithRetry<RecentScanResponse>(`/api/v2/bulk-scans/communities/${communityServerId}/recent`);
  }

  async getLatestScan(communityServerId: string): Promise<LatestScanResponse> {
    return this.fetchWithRetry<LatestScanResponse>(
      `/api/v2/bulk-scans/communities/${communityServerId}/latest`
    );
  }

  async generateScanExplanation(
    originalMessage: string,
    factCheckItemId: string,
    communityServerId: string
  ): Promise<ExplanationResultResponse> {
    return this.fetchWithRetry<ExplanationResultResponse>('/api/v2/bulk-scans/explanations', {
      method: 'POST',
      body: JSON.stringify({
        data: {
          type: 'scan-explanations',
          attributes: {
            original_message: originalMessage,
            fact_check_item_id: factCheckItemId,
            community_server_id: communityServerId,
          },
        },
      }),
    });
  }

  async getClearPreview(
    endpoint: string,
    context?: UserContext
  ): Promise<ClearPreviewResult> {
    const response = await this.fetchWithRetry<{ would_delete_count: number; message: string }>(
      endpoint,
      {},
      1,
      context
    );

    return {
      wouldDeleteCount: response.would_delete_count,
      message: response.message,
    };
  }

  async executeClear(
    endpoint: string,
    context?: UserContext
  ): Promise<ClearResult> {
    const response = await this.fetchWithRetry<{ deleted_count: number; message: string }>(
      endpoint,
      {
        method: 'DELETE',
      },
      1,
      context
    );

    return {
      deletedCount: response.deleted_count,
      message: response.message,
    };
  }

  async updateFlashpointDetection(
    platformCommunityServerId: string,
    enabled: boolean,
    context?: UserContext
  ): Promise<FlashpointDetectionUpdateResponse> {
    return this.fetchWithRetry<FlashpointDetectionUpdateResponse>(
      `/api/v1/community-servers/${platformCommunityServerId}/flashpoint-detection`,
      {
        method: 'PATCH',
        body: JSON.stringify({ enabled }),
      },
      1,
      context
    );
  }

  async getFlashpointDetectionStatus(
    platformCommunityServerId: string,
    platform: string = 'discord'
  ): Promise<FlashpointDetectionUpdateResponse> {
    const serverResponse = await this.getCommunityServerByPlatformId(platformCommunityServerId, platform);
    return {
      id: serverResponse.data.id,
      platform_community_server_id: serverResponse.data.attributes.platform_community_server_id,
      flashpoint_detection_enabled: serverResponse.data.attributes.flashpoint_detection_enabled,
    };
  }

  async checkClaimRelevance(params: {
    originalMessage: string;
    matchedContent: string;
    matchedSource: string;
    similarityScore: number;
  }): Promise<ClaimRelevanceResult | null> {
    try {
      const jsonApiRequest = this.buildJSONAPIRequestBody('claim-relevance-checks', {
        original_message: params.originalMessage,
        matched_content: params.matchedContent,
        matched_source: params.matchedSource,
        similarity_score: params.similarityScore,
      });

      const response = await this.fetchWithRetry<ClaimRelevanceCheckResponse>(
        '/api/v2/claim-relevance-checks',
        {
          method: 'POST',
          body: JSON.stringify(jsonApiRequest),
        }
      );

      return {
        outcome: response.data.attributes.outcome,
        reasoning: response.data.attributes.reasoning,
        shouldFlag: response.data.attributes.should_flag,
      };
    } catch (error) {
      logger.error('Claim relevance check failed, failing open', {
        error: error instanceof Error ? error.message : String(error),
        originalMessage: params.originalMessage.substring(0, 100),
        matchedSource: params.matchedSource,
        similarityScore: params.similarityScore,
      });
      return null;
    }
  }
}
