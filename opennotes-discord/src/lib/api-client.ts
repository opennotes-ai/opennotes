import type { components, paths } from './generated-types.js';
import type { Middleware } from 'openapi-fetch';
import createClient from 'openapi-fetch';
import {
  NoteRequest,
  CreateNoteRequest,
  CreateRatingRequest,
  ListRequestsFilters,
} from './types.js';
import { ApiError } from './errors.js';
import { logger } from '../logger.js';
import { resolveUserProfileId } from './user-profile-resolver.js';
import {
  createAuthMiddleware,
  createTracingMiddleware,
  createLoggingMiddleware,
  createResponseSizeMiddleware,
  createRetryFetch,
  validateHttps,
  buildProfileHeaders,
  initGCPDetection,
  type UserContext,
} from './api-middleware.js';

export type { UserContext } from './api-middleware.js';

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

export interface NoteResponse {
  id: string;
  summary: string;
  classification: NoteClassification;
  status: NoteStatus;
  helpfulness_score: number;
  author_id: string;
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
  rater_id: string;
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

export type NoteCreateRequest = components['schemas']['NoteCreateRequest'];
export type NoteCreateAttributes = components['schemas']['NoteCreateAttributes'];
export type RatingCreateRequest = components['schemas']['RatingCreateRequest'];
export type RatingCreateAttributes = components['schemas']['RatingCreateAttributes'];

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

export interface NoteAttributes {
  summary: string;
  classification: string;
  status: NoteStatus;
  helpfulness_score: number;
  author_id: string;
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

export type NoteJSONAPIResponse = JSONAPISingleResponse<NoteAttributes>;
export type NoteListJSONAPIResponse = JSONAPIListResponse<NoteAttributes>;

export interface NoteListJSONAPIResponseWithPagination extends NoteListJSONAPIResponse {
  total: number;
  page: number;
  size: number;
}

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

export type CommunityServerJSONAPIResponse = JSONAPISingleResponse<CommunityServerAttributes>;

export interface UserProfileLookupAttributes {
  platform: string;
  platform_user_id: string;
  display_name: string | null;
}

export type UserProfileLookupResponse = JSONAPISingleResponse<UserProfileLookupAttributes>;

export interface RatingAttributes {
  note_id: string;
  rater_id: string;
  helpfulness_level: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export type RatingJSONAPIResponse = JSONAPISingleResponse<RatingAttributes>;
export type RatingListJSONAPIResponse = JSONAPIListResponse<RatingAttributes>;

export type PreviouslySeenCheckJSONAPIResponse = JSONAPISingleResponse<PreviouslySeenCheckResultAttributes>;

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

export type NoteScoreJSONAPIResponse = JSONAPISingleResponse<NoteScoreAttributes>;
export type ScoringResultJSONAPIResponse = JSONAPISingleResponse<ScoringResultAttributes>;

export interface BatchScoreJSONAPIResponse extends Omit<JSONAPIListResponse<NoteScoreAttributes>, 'meta'> {
  meta?: JSONAPIMeta & BatchScoreMeta;
}

export interface TopNotesJSONAPIResponse extends Omit<JSONAPIListResponse<NoteScoreAttributes>, 'meta'> {
  meta?: JSONAPIMeta & TopNotesMeta;
}

export type ScoringStatusJSONAPIResponse = JSONAPISingleResponse<ScoringStatusAttributes>;

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

export interface NotePublisherConfigJSONAPIAttributes {
  community_server_id: string;
  channel_id?: string | null;
  enabled: boolean;
  threshold?: number | null;
  updated_at?: string | null;
  updated_by?: string | null;
}

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

export interface PreviouslySeenMessageJSONAPIAttributes {
  community_server_id: string;
  original_message_id: string;
  published_note_id: string;
  embedding_provider?: string | null;
  embedding_model?: string | null;
  extra_metadata?: Record<string, unknown> | null;
  created_at?: string | null;
}

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

export interface PreviouslySeenCheckResultAttributes {
  should_auto_publish: boolean;
  should_auto_request: boolean;
  autopublish_threshold: number;
  autorequest_threshold: number;
  matches: PreviouslySeenMatchResource[];
  top_match?: PreviouslySeenMatchResource | null;
}

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

export interface SimilaritySearchResultAttributes {
  matches: FactCheckMatchResource[];
  query_text: string;
  dataset_tags: string[];
  similarity_threshold: number;
  score_threshold: number;
  total_matches: number;
}

export interface ScoringResultAttributes {
  scored_notes: { [key: string]: unknown }[];
  helpful_scores: { [key: string]: unknown }[];
  auxiliary_info: { [key: string]: unknown }[];
}

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

type TypedClient = ReturnType<typeof createClient<paths>>;

function handleError<T>(result: { data?: T; error?: unknown; response: Response }, endpoint: string): T {
  if (result.error !== undefined) {
    throw new ApiError(
      `API request failed: ${result.response.status} ${result.response.statusText}`,
      endpoint,
      result.response.status,
      result.error,
    );
  }
  return result.data as T;
}

export class ApiClient {
  private client: TypedClient;
  private retryFetch: (input: Request) => Promise<Response>;
  private baseUrl: string;
  private middleware: Middleware[];

  constructor(config: ApiClientConfig) {
    const environment = config.environment ?? 'production';
    validateHttps(config.serverUrl, environment);
    this.baseUrl = config.serverUrl;

    initGCPDetection();

    this.retryFetch = createRetryFetch({
      retryAttempts: config.retryAttempts ?? 3,
      retryDelayMs: config.retryDelayMs ?? 1000,
      requestTimeout: config.requestTimeout ?? 30000,
    });

    this.middleware = [
      createAuthMiddleware({
        baseUrl: config.serverUrl,
        apiKey: config.apiKey,
        internalServiceSecret: config.internalServiceSecret,
      }),
      createTracingMiddleware(),
      createResponseSizeMiddleware({
        maxResponseSize: config.maxResponseSize ?? 10 * 1024 * 1024,
      }),
      createLoggingMiddleware(),
    ];

    this.client = createClient<paths>({
      baseUrl: config.serverUrl,
      fetch: this.retryFetch,
    });

    for (const mw of this.middleware) {
      this.client.use(mw);
    }
  }

  private profileHeaders(context?: UserContext): Record<string, string> {
    return buildProfileHeaders(context);
  }

  async healthCheck(): Promise<{ status: string; version: string }> {
    const result = await this.client.GET('/health');
    return handleError(result, '/health') as { status: string; version: string };
  }

  async scoreNotes(request: ScoringRequest): Promise<ScoringResultJSONAPIResponse> {
    const result = await this.client.POST('/api/v2/scoring/score', {
      body: {
        data: {
          type: 'scoring-requests',
          attributes: request as never,
        },
      } as never,
    });
    return handleError(result, '/api/v2/scoring/score') as unknown as ScoringResultJSONAPIResponse;
  }

  async getNotes(messageId: string): Promise<NoteListJSONAPIResponse> {
    const result = await this.client.GET('/api/v2/notes', {
      params: {
        query: {
          'filter[platform_message_id]': messageId,
        },
      },
    });
    return handleError(result, '/api/v2/notes') as unknown as NoteListJSONAPIResponse;
  }

  async getNote(noteId: string): Promise<NoteJSONAPIResponse> {
    const result = await this.client.GET('/api/v2/notes/{note_id}', {
      params: { path: { note_id: noteId } },
    });
    return handleError(result, `/api/v2/notes/${noteId}`) as unknown as NoteJSONAPIResponse;
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

    const result = await this.client.POST('/api/v2/notes', {
      body: {
        data: {
          type: 'notes',
          attributes: noteAttributes,
        },
      } as never,
      headers: this.profileHeaders(context),
    });
    return handleError(result, '/api/v2/notes') as unknown as NoteJSONAPIResponse;
  }

  async rateNote(request: CreateRatingRequest, context?: UserContext): Promise<RatingJSONAPIResponse> {
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

    const result = await this.client.POST('/api/v2/ratings', {
      body: {
        data: {
          type: 'ratings',
          attributes: ratingAttributes,
        },
      } as never,
      headers: this.profileHeaders(context),
    });
    return handleError(result, '/api/v2/ratings') as unknown as RatingJSONAPIResponse;
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

    const result = await this.client.POST('/api/v2/requests', {
      body: {
        data: {
          type: 'requests',
          attributes: requestAttributes,
        },
      } as never,
      headers: this.profileHeaders(context),
    });
    handleError(result, '/api/v2/requests');
  }

  async listRequests(filters?: ListRequestsFilters, context?: UserContext): Promise<JSONAPIListResponse<RequestAttributes>> {
    const query: Record<string, unknown> = {};
    if (filters?.page) { query['page[number]'] = filters.page; }
    if (filters?.size) { query['page[size]'] = filters.size; }
    if (filters?.status) { query['filter[status]'] = filters.status; }
    if (filters?.requestedBy) { query['filter[requested_by]'] = filters.requestedBy; }
    if (filters?.communityServerId) { query['filter[community_server_id]'] = filters.communityServerId; }

    const result = await this.client.GET('/api/v2/requests', {
      params: { query: query as never },
      headers: this.profileHeaders(context),
    });
    return handleError(result, '/api/v2/requests') as unknown as JSONAPIListResponse<RequestAttributes>;
  }

  async getRequest(requestId: string, context?: UserContext): Promise<JSONAPISingleResponse<RequestAttributes>> {
    const result = await this.client.GET('/api/v2/requests/{request_id}', {
      params: { path: { request_id: requestId } },
      headers: this.profileHeaders(context),
    });
    return handleError(result, `/api/v2/requests/${requestId}`) as unknown as JSONAPISingleResponse<RequestAttributes>;
  }

  async generateAiNote(requestId: string, context?: UserContext): Promise<NoteJSONAPIResponse> {
    const result = await this.client.POST('/api/v2/requests/{request_id}/ai-notes', {
      params: { path: { request_id: requestId } },
      headers: this.profileHeaders(context),
    });
    return handleError(result, `/api/v2/requests/${requestId}/ai-notes`) as unknown as NoteJSONAPIResponse;
  }

  async getCommunityServerByPlatformId(
    platformId: string,
    platform: string = 'discord'
  ): Promise<CommunityServerJSONAPIResponse> {
    const result = await this.client.GET('/api/v2/community-servers/lookup', {
      params: {
        query: {
          platform,
          platform_community_server_id: platformId,
        },
      },
    });
    return handleError(result, '/api/v2/community-servers/lookup') as unknown as CommunityServerJSONAPIResponse;
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
    const result = await this.client.PATCH('/api/v1/community-servers/{platform_community_server_id}/name', {
      params: { path: { platform_community_server_id: platformId } },
      body: body as never,
    });
    handleError(result, `/api/v1/community-servers/${platformId}/name`);
  }

  async getUserProfileByPlatformId(
    platformUserId: string,
    platform: string = 'discord'
  ): Promise<UserProfileLookupResponse> {
    const result = await this.client.GET('/api/v2/user-profiles/lookup', {
      params: {
        query: {
          platform,
          platform_user_id: platformUserId,
        },
      },
    });
    return handleError(result, '/api/v2/user-profiles/lookup') as unknown as UserProfileLookupResponse;
  }

  async updateWelcomeMessageId(
    platformId: string,
    welcomeMessageId: string | null
  ): Promise<WelcomeMessageUpdateResponse> {
    const result = await this.client.PATCH('/api/v1/community-servers/{platform_community_server_id}/welcome-message', {
      params: { path: { platform_community_server_id: platformId } },
      body: { welcome_message_id: welcomeMessageId } as never,
    });
    return handleError(result, `/api/v1/community-servers/${platformId}/welcome-message`) as unknown as WelcomeMessageUpdateResponse;
  }

  async getRatingThresholds(): Promise<RatingThresholdsResponse> {
    const result = await this.client.GET('/api/v1/config/rating-thresholds');
    return handleError(result, '/api/v1/config/rating-thresholds') as unknown as RatingThresholdsResponse;
  }

  async listNotesWithStatus(
    status: NoteStatus,
    page: number = 1,
    size: number = 20,
    communityServerId?: string,
    excludeRatedByParticipantId?: string,
    context?: UserContext
  ): Promise<NoteListJSONAPIResponseWithPagination> {
    const query: Record<string, unknown> = {
      'page[number]': page,
      'page[size]': size,
      'filter[status]': status,
    };
    if (communityServerId) {
      query['filter[community_server_id]'] = communityServerId;
    }
    if (excludeRatedByParticipantId) {
      query['filter[rater_id__not_in]'] = excludeRatedByParticipantId;
    }

    const result = await this.client.GET('/api/v2/notes', {
      params: { query: query as never },
      headers: this.profileHeaders(context),
    });
    const jsonApiResponse = handleError(result, '/api/v2/notes') as unknown as NoteListJSONAPIResponse;

    return {
      ...jsonApiResponse,
      total: jsonApiResponse.meta?.count ?? jsonApiResponse.data.length,
      page,
      size,
    };
  }

  async getRatingsForNote(noteId: string): Promise<RatingListJSONAPIResponse> {
    const result = await this.client.GET('/api/v2/notes/{note_id}/ratings', {
      params: { path: { note_id: noteId } },
    });
    return handleError(result, `/api/v2/notes/${noteId}/ratings`) as unknown as RatingListJSONAPIResponse;
  }

  async updateRating(ratingId: string, helpful: boolean, context?: UserContext): Promise<RatingJSONAPIResponse> {
    const result = await this.client.PUT('/api/v2/ratings/{rating_id}', {
      params: { path: { rating_id: ratingId } },
      body: {
        data: {
          type: 'ratings',
          id: ratingId,
          attributes: {
            helpfulness_level: helpful ? 'HELPFUL' : 'NOT_HELPFUL',
          },
        },
      } as never,
      headers: this.profileHeaders(context),
    });
    return handleError(result, `/api/v2/ratings/${ratingId}`) as unknown as RatingJSONAPIResponse;
  }

  async getGuildConfig(guildId: string): Promise<Record<string, unknown>> {
    const result = await this.client.GET('/api/v1/community-config/{community_server_id}', {
      params: { path: { community_server_id: guildId } },
    });
    const response = handleError(result, `/api/v1/community-config/${guildId}`) as unknown as { community_id: string; config: Record<string, unknown> };
    return response.config;
  }

  async setGuildConfig(guildId: string, key: string, value: string | boolean | number, updatedBy: string, context?: UserContext): Promise<void> {
    const result = await this.client.PUT('/api/v1/community-config/{community_server_id}', {
      params: { path: { community_server_id: guildId } },
      body: { key, value: String(value), updated_by: updatedBy } as never,
      headers: this.profileHeaders(context),
    });
    handleError(result, `/api/v1/community-config/${guildId}`);
  }

  async resetGuildConfig(guildId: string, context?: UserContext): Promise<void> {
    const result = await this.client.DELETE('/api/v1/community-config/{community_server_id}', {
      params: { path: { community_server_id: guildId } },
      headers: this.profileHeaders(context),
    });
    handleError(result, `/api/v1/community-config/${guildId}`);
  }

  async getNoteScore(noteId: string): Promise<NoteScoreJSONAPIResponse> {
    const result = await this.client.GET('/api/v2/scoring/notes/{note_id}/score', {
      params: { path: { note_id: noteId } },
    });
    return handleError(result, `/api/v2/scoring/notes/${noteId}/score`) as unknown as NoteScoreJSONAPIResponse;
  }

  async getBatchNoteScores(noteIds: string[]): Promise<BatchScoreJSONAPIResponse> {
    const result = await this.client.POST('/api/v2/scoring/notes/batch-scores', {
      body: {
        data: {
          type: 'batch-score-requests',
          attributes: { note_ids: noteIds },
        },
      } as never,
    });
    return handleError(result, '/api/v2/scoring/notes/batch-scores') as unknown as BatchScoreJSONAPIResponse;
  }

  async getTopNotes(
    limit?: number,
    minConfidence?: ScoreConfidence,
    tier?: number
  ): Promise<TopNotesJSONAPIResponse> {
    const query: Record<string, unknown> = {};
    if (limit) { query.limit = limit; }
    if (minConfidence) { query.min_confidence = minConfidence; }
    if (tier !== undefined) { query.tier = tier; }

    const result = await this.client.GET('/api/v2/scoring/notes/top', {
      params: { query: query as never },
    });
    return handleError(result, '/api/v2/scoring/notes/top') as unknown as TopNotesJSONAPIResponse;
  }

  async getScoringStatus(): Promise<ScoringStatusJSONAPIResponse> {
    const result = await this.client.GET('/api/v2/scoring/status');
    return handleError(result, '/api/v2/scoring/status') as unknown as ScoringStatusJSONAPIResponse;
  }

  async listMonitoredChannels(
    communityServerId?: string,
    enabledOnly: boolean = true
  ): Promise<JSONAPIListResponse<MonitoredChannelJSONAPIAttributes>> {
    const query: Record<string, unknown> = {
      'page[size]': 100,
    };
    if (communityServerId) {
      query['filter[community_server_id]'] = communityServerId;
    }
    if (enabledOnly) {
      query['filter[enabled]'] = true;
    }

    const result = await this.client.GET('/api/v2/monitored-channels', {
      params: { query: query as never },
    });
    return handleError(result, '/api/v2/monitored-channels') as unknown as JSONAPIListResponse<MonitoredChannelJSONAPIAttributes>;
  }

  async similaritySearch(
    text: string,
    communityServerId: string,
    datasetTags: string[] = ['snopes'],
    similarityThreshold?: number,
    limit: number = 5
  ): Promise<JSONAPISingleResponse<SimilaritySearchResultAttributes>> {
    const result = await this.client.POST('/api/v2/similarity-searches', {
      body: {
        data: {
          type: 'similarity-searches',
          attributes: {
            text,
            community_server_id: communityServerId,
            dataset_tags: datasetTags,
            similarity_threshold: similarityThreshold,
            limit,
          },
        },
      } as never,
    });
    return handleError(result, '/api/v2/similarity-searches') as unknown as JSONAPISingleResponse<SimilaritySearchResultAttributes>;
  }

  async createMonitoredChannel(
    request: MonitoredChannelCreate,
    context?: UserContext
  ): Promise<JSONAPISingleResponse<MonitoredChannelJSONAPIAttributes> | null> {
    try {
      const result = await this.client.POST('/api/v2/monitored-channels', {
        body: {
          data: {
            type: 'monitored-channels',
            attributes: {
              community_server_id: request.community_server_id,
              channel_id: request.channel_id,
              name: request.name ?? null,
              enabled: request.enabled ?? true,
              similarity_threshold: request.similarity_threshold,
              dataset_tags: request.dataset_tags,
              updated_by: request.updated_by,
            },
          },
        } as never,
        headers: this.profileHeaders(context),
      });
      return handleError(result, '/api/v2/monitored-channels') as unknown as JSONAPISingleResponse<MonitoredChannelJSONAPIAttributes>;
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
    const result = await this.client.GET('/api/v1/community-servers/{community_server_id}/llm-config', {
      params: { path: { community_server_id: communityServerId } },
    });
    return handleError(result, `/api/v1/community-servers/${communityServerId}/llm-config`) as unknown as LLMConfigResponse[];
  }

  async createLLMConfig(communityServerId: string, config: LLMConfigCreate, context?: UserContext): Promise<LLMConfigResponse> {
    const result = await this.client.POST('/api/v1/community-servers/{community_server_id}/llm-config', {
      params: { path: { community_server_id: communityServerId } },
      body: config as never,
      headers: this.profileHeaders(context),
    });
    return handleError(result, `/api/v1/community-servers/${communityServerId}/llm-config`) as unknown as LLMConfigResponse;
  }

  async getMonitoredChannelByUuid(uuid: string): Promise<JSONAPISingleResponse<MonitoredChannelJSONAPIAttributes>> {
    const result = await this.client.GET('/api/v2/monitored-channels/{channel_uuid}', {
      params: { path: { channel_uuid: uuid } },
    });
    return handleError(result, `/api/v2/monitored-channels/${uuid}`) as unknown as JSONAPISingleResponse<MonitoredChannelJSONAPIAttributes>;
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

    const result = await this.client.PATCH('/api/v2/monitored-channels/{channel_uuid}', {
      params: { path: { channel_uuid: existing.data.id } },
      body: {
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
      } as never,
      headers: this.profileHeaders(context),
    });
    return handleError(result, `/api/v2/monitored-channels/${existing.data.id}`) as unknown as JSONAPISingleResponse<MonitoredChannelJSONAPIAttributes>;
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

    const result = await this.client.DELETE('/api/v2/monitored-channels/{channel_uuid}', {
      params: { path: { channel_uuid: existing.data.id } },
      headers: this.profileHeaders(context),
    });
    handleError(result, `/api/v2/monitored-channels/${existing.data.id}`);
    return true;
  }

  async forcePublishNote(noteId: string, context?: UserContext): Promise<NoteJSONAPIResponse> {
    const result = await this.client.POST('/api/v2/notes/{note_id}/force-publish', {
      params: { path: { note_id: noteId } },
      headers: this.profileHeaders(context),
    });
    return handleError(result, `/api/v2/notes/${noteId}/force-publish`) as unknown as NoteJSONAPIResponse;
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
    const body: AddCommunityAdminRequest = {
      user_discord_id: userDiscordId,
      ...(userMetadata?.username && { username: userMetadata.username }),
      ...(userMetadata?.display_name && { display_name: userMetadata.display_name }),
      ...(userMetadata?.avatar_url && { avatar_url: userMetadata.avatar_url }),
    };

    const result = await this.client.POST('/api/v1/community-servers/{community_server_id}/admins', {
      params: { path: { community_server_id: communityServerId } },
      body: body as never,
      headers: this.profileHeaders(context),
    });
    return handleError(result, `/api/v1/community-servers/${communityServerId}/admins`) as unknown as CommunityAdminResponse;
  }

  async removeCommunityAdmin(
    communityServerId: string,
    userDiscordId: string,
    context?: UserContext
  ): Promise<RemoveCommunityAdminResponse> {
    const result = await this.client.DELETE('/api/v1/community-servers/{community_server_id}/admins/{user_discord_id}', {
      params: { path: { community_server_id: communityServerId, user_discord_id: userDiscordId } },
      headers: this.profileHeaders(context),
    });
    return handleError(result, `/api/v1/community-servers/${communityServerId}/admins/${userDiscordId}`) as unknown as RemoveCommunityAdminResponse;
  }

  async listCommunityAdmins(communityServerId: string): Promise<CommunityAdminResponse[]> {
    const result = await this.client.GET('/api/v1/community-servers/{community_server_id}/admins', {
      params: { path: { community_server_id: communityServerId } },
    });
    return handleError(result, `/api/v1/community-servers/${communityServerId}/admins`) as unknown as CommunityAdminResponse[];
  }

  async checkPreviouslySeen(
    messageText: string,
    guildId: string,
    channelId: string
  ): Promise<PreviouslySeenCheckJSONAPIResponse> {
    const result = await this.client.POST('/api/v2/previously-seen-messages/check', {
      body: {
        data: {
          type: 'previously-seen-check',
          attributes: {
            message_text: messageText,
            platform_community_server_id: guildId,
            channel_id: channelId,
          },
        },
      } as never,
    });
    return handleError(result, '/api/v2/previously-seen-messages/check') as unknown as PreviouslySeenCheckJSONAPIResponse;
  }

  async recordNotePublisher(
    request: NotePublisherRecordRequest
  ): Promise<void> {
    const result = await this.client.POST('/api/v2/note-publisher-posts', {
      body: {
        data: {
          type: 'note-publisher-posts',
          attributes: {
            note_id: request.noteId,
            original_message_id: request.originalMessageId,
            channel_id: request.channelId,
            community_server_id: request.guildId,
            score_at_post: request.scoreAtPost,
            confidence_at_post: request.confidenceAtPost,
            success: request.success,
            error_message: request.errorMessage ?? null,
          },
        },
      } as never,
    });
    handleError(result, '/api/v2/note-publisher-posts');
  }

  async checkNoteDuplicate(
    originalMessageId: string,
    communityServerId: string
  ): Promise<JSONAPIListResponse<NotePublisherPostJSONAPIAttributes>> {
    const query: Record<string, unknown> = {
      'filter[community_server_id]': communityServerId,
      'filter[original_message_id]': originalMessageId,
      'page[size]': 1,
    };

    const result = await this.client.GET('/api/v2/note-publisher-posts', {
      params: { query: query as never },
    });
    return handleError(result, '/api/v2/note-publisher-posts') as unknown as JSONAPIListResponse<NotePublisherPostJSONAPIAttributes>;
  }

  async getLastNotePost(
    channelId: string,
    communityServerId: string
  ): Promise<JSONAPIListResponse<NotePublisherPostJSONAPIAttributes>> {
    const query: Record<string, unknown> = {
      'filter[community_server_id]': communityServerId,
      'filter[channel_id]': channelId,
      'filter[success]': true,
      'page[size]': 1,
      sort: '-posted_at',
    };

    const result = await this.client.GET('/api/v2/note-publisher-posts', {
      params: { query: query as never },
    });
    return handleError(result, '/api/v2/note-publisher-posts') as unknown as JSONAPIListResponse<NotePublisherPostJSONAPIAttributes>;
  }

  async getNotePublisherConfig(
    guildId: string,
    channelId?: string
  ): Promise<JSONAPIListResponse<NotePublisherConfigJSONAPIAttributes>> {
    const query: Record<string, unknown> = {
      'filter[community_server_id]': guildId,
      'page[size]': channelId ? 100 : 1,
    };

    const result = await this.client.GET('/api/v2/note-publisher-configs', {
      params: { query: query as never },
    });
    return handleError(result, '/api/v2/note-publisher-configs') as unknown as JSONAPIListResponse<NotePublisherConfigJSONAPIAttributes>;
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
      const result = await this.client.PATCH('/api/v2/note-publisher-configs/{config_uuid}', {
        params: { path: { config_uuid: existingConfig.id } },
        body: {
          data: {
            type: 'note-publisher-configs',
            id: existingConfig.id,
            attributes: {
              enabled,
              threshold: threshold ?? null,
              updated_by: updatedBy ?? null,
            },
          },
        } as never,
        headers: this.profileHeaders(context),
      });
      return handleError(result, `/api/v2/note-publisher-configs/${existingConfig.id}`) as unknown as JSONAPISingleResponse<NotePublisherConfigJSONAPIAttributes>;
    } else {
      const result = await this.client.POST('/api/v2/note-publisher-configs', {
        body: {
          data: {
            type: 'note-publisher-configs',
            attributes: {
              community_server_id: guildId,
              channel_id: channelId ?? null,
              enabled,
              threshold: threshold ?? null,
              updated_by: updatedBy ?? null,
            },
          },
        } as never,
        headers: this.profileHeaders(context),
      });
      return handleError(result, '/api/v2/note-publisher-configs') as unknown as JSONAPISingleResponse<NotePublisherConfigJSONAPIAttributes>;
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
    const query: Record<string, unknown> = {
      'page[number]': page,
      'page[size]': size,
      'filter[rater_id]': raterParticipantId,
      'filter[community_server_id]': communityServerId,
    };
    if (statusFilter) {
      query['filter[status]'] = statusFilter;
    }

    const result = await this.client.GET('/api/v2/notes', {
      params: { query: query as never },
      headers: this.profileHeaders(context),
    });
    const jsonApiResponse = handleError(result, '/api/v2/notes') as unknown as NoteListJSONAPIResponse;

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
    const result = await this.client.POST('/api/v2/bulk-scans', {
      body: {
        data: {
          type: 'bulk-scans',
          attributes: {
            community_server_id: communityServerId,
            scan_window_days: scanWindowDays,
          },
        },
      } as never,
    });
    return handleError(result, '/api/v2/bulk-scans') as unknown as BulkScanSingleResponse;
  }

  async getBulkScanResults(scanId: string): Promise<BulkScanResultsResponse> {
    const result = await this.client.GET('/api/v2/bulk-scans/{scan_id}', {
      params: { path: { scan_id: scanId } },
    });
    return handleError(result, `/api/v2/bulk-scans/${scanId}`) as unknown as BulkScanResultsResponse;
  }

  async createNoteRequestsFromScan(
    scanId: string,
    messageIds: string[],
    generateAiNotes: boolean
  ): Promise<NoteRequestsResultResponse> {
    const result = await this.client.POST('/api/v2/bulk-scans/{scan_id}/note-requests', {
      params: { path: { scan_id: scanId } },
      body: {
        data: {
          type: 'note-requests',
          attributes: {
            message_ids: messageIds,
            generate_ai_notes: generateAiNotes,
          },
        },
      } as never,
    });
    return handleError(result, `/api/v2/bulk-scans/${scanId}/note-requests`) as unknown as NoteRequestsResultResponse;
  }

  async checkRecentScan(communityServerId: string): Promise<RecentScanResponse> {
    const result = await this.client.GET('/api/v2/bulk-scans/communities/{community_server_id}/recent', {
      params: { path: { community_server_id: communityServerId } },
    });
    return handleError(result, `/api/v2/bulk-scans/communities/${communityServerId}/recent`) as unknown as RecentScanResponse;
  }

  async getLatestScan(communityServerId: string): Promise<LatestScanResponse> {
    const result = await this.client.GET('/api/v2/bulk-scans/communities/{community_server_id}/latest', {
      params: { path: { community_server_id: communityServerId } },
    });
    return handleError(result, `/api/v2/bulk-scans/communities/${communityServerId}/latest`) as unknown as LatestScanResponse;
  }

  async generateScanExplanation(
    originalMessage: string,
    factCheckItemId: string,
    communityServerId: string
  ): Promise<ExplanationResultResponse> {
    const result = await this.client.POST('/api/v2/bulk-scans/explanations', {
      body: {
        data: {
          type: 'scan-explanations',
          attributes: {
            original_message: originalMessage,
            fact_check_item_id: factCheckItemId,
            community_server_id: communityServerId,
          },
        },
      } as never,
    });
    return handleError(result, '/api/v2/bulk-scans/explanations') as unknown as ExplanationResultResponse;
  }

  async getClearPreview(
    endpoint: string,
    context?: UserContext
  ): Promise<ClearPreviewResult> {
    const url = `${this.baseUrl}${endpoint}`;
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...this.profileHeaders(context),
    };
    const request = new Request(url, { method: 'GET', headers });

    for (const mw of this.middleware) {
      if (mw.onRequest) {
        await mw.onRequest({
          request,
          schemaPath: endpoint,
          params: {},
          id: 'clear-preview',
          options: {} as never,
        });
      }
    }

    const response = await this.retryFetch(request);

    if (!response.ok) {
      throw new ApiError(
        `API request failed: ${response.status} ${response.statusText}`,
        endpoint,
        response.status,
      );
    }

    const data = await response.json() as { would_delete_count: number; message: string };
    return {
      wouldDeleteCount: data.would_delete_count,
      message: data.message,
    };
  }

  async executeClear(
    endpoint: string,
    context?: UserContext
  ): Promise<ClearResult> {
    const url = `${this.baseUrl}${endpoint}`;
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...this.profileHeaders(context),
    };
    const request = new Request(url, { method: 'DELETE', headers });

    for (const mw of this.middleware) {
      if (mw.onRequest) {
        await mw.onRequest({
          request,
          schemaPath: endpoint,
          params: {},
          id: 'clear-execute',
          options: {} as never,
        });
      }
    }

    const response = await this.retryFetch(request);

    if (!response.ok) {
      throw new ApiError(
        `API request failed: ${response.status} ${response.statusText}`,
        endpoint,
        response.status,
      );
    }

    const data = await response.json() as { deleted_count: number; message: string };
    return {
      deletedCount: data.deleted_count,
      message: data.message,
    };
  }

  async updateFlashpointDetection(
    platformCommunityServerId: string,
    enabled: boolean,
    context?: UserContext
  ): Promise<FlashpointDetectionUpdateResponse> {
    const result = await this.client.PATCH('/api/v1/community-servers/{platform_community_server_id}/flashpoint-detection', {
      params: { path: { platform_community_server_id: platformCommunityServerId } },
      body: { enabled } as never,
      headers: this.profileHeaders(context),
    });
    return handleError(result, `/api/v1/community-servers/${platformCommunityServerId}/flashpoint-detection`) as unknown as FlashpointDetectionUpdateResponse;
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
      const result = await this.client.POST('/api/v2/claim-relevance-checks', {
        body: {
          data: {
            type: 'claim-relevance-checks',
            attributes: {
              original_message: params.originalMessage,
              matched_content: params.matchedContent,
              matched_source: params.matchedSource,
              similarity_score: params.similarityScore,
            },
          },
        } as never,
      });
      const response = handleError(result, '/api/v2/claim-relevance-checks') as unknown as ClaimRelevanceCheckResponse;

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
