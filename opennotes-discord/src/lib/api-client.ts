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
import { sanitizeObject } from './sanitize.js';
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

export type NoteAttributes = components['schemas']['NoteJSONAPIAttributes'];
export type NoteJSONAPIResponse = components['schemas']['NoteSingleResponse'];
export type NoteListJSONAPIResponse = components['schemas']['NoteListResponse'];

export interface NoteListJSONAPIResponseWithPagination extends NoteListJSONAPIResponse {
  total: number;
  page: number;
  size: number;
}

export type CommunityServerAttributes = components['schemas']['CommunityServerAttributes'];
export type WelcomeMessageUpdateResponse = components['schemas']['WelcomeMessageUpdateResponse'];
export type CommunityServerJSONAPIResponse = components['schemas']['CommunityServerSingleResponse'];

export type UserProfileLookupResponse = components['schemas']['UserProfileLookupResponse'];

export type RatingAttributes = components['schemas']['RatingAttributes'];
export type RatingJSONAPIResponse = components['schemas']['RatingSingleResponse'];
export type RatingListJSONAPIResponse = components['schemas']['RatingListResponse'];

export type PreviouslySeenCheckJSONAPIResponse = components['schemas']['PreviouslySeenCheckResultResponse'];

export type RequestAttributes = components['schemas']['RequestAttributes'];

export type NoteScoreAttributes = components['schemas']['NoteScoreAttributes'];
export type ScoringStatusAttributes = components['schemas']['ScoringStatusAttributes'];
export type NoteScoreJSONAPIResponse = components['schemas']['NoteScoreSingleResponse'];
export type ScoringResultJSONAPIResponse = components['schemas']['ScoringResultResponse'];
export type ScoringStatusJSONAPIResponse = components['schemas']['ScoringStatusJSONAPIResponse'];

export type BatchScoreJSONAPIResponse = Omit<components['schemas']['NoteScoreListResponse'], 'meta'> & {
  meta?: {
    [key: string]: unknown;
    count?: number;
    total_requested?: number;
    total_found?: number;
    not_found?: string[];
  } | null;
};

export type TopNotesJSONAPIResponse = Omit<components['schemas']['NoteScoreListResponse'], 'meta'> & {
  meta?: {
    [key: string]: unknown;
    count?: number;
    total_count?: number;
    current_tier?: number;
    filters_applied?: Record<string, unknown>;
  } | null;
};

export type MonitoredChannelJSONAPIAttributes = components['schemas']['MonitoredChannelAttributes'];
export type MonitoredChannelJSONAPIResponse = components['schemas']['MonitoredChannelSingleResponse'];
export type MonitoredChannelListJSONAPIResponse = components['schemas']['MonitoredChannelListJSONAPIResponse'];

export type NotePublisherConfigJSONAPIAttributes = components['schemas']['NotePublisherConfigAttributes'];
export type NotePublisherPostJSONAPIAttributes = components['schemas']['NotePublisherPostAttributes'];

export type PreviouslySeenCheckResultAttributes = components['schemas']['PreviouslySeenCheckResultAttributes'];
export type SimilaritySearchResultAttributes = components['schemas']['SimilaritySearchResultAttributes'];
export type ScoringResultAttributes = components['schemas']['ScoringResultAttributes'];

export type JSONAPILinks = components['schemas']['JSONAPILinks'];

export type JSONAPIMeta = components['schemas']['JSONAPIMeta'];

export interface JSONAPIResource<T> {
  type: string;
  id: string;
  attributes: T;
}

export interface JSONAPIListResponse<T> {
  data: JSONAPIResource<T>[];
  jsonapi: { [key: string]: string };
  links?: JSONAPILinks | null;
  meta?: JSONAPIMeta | null;
}

export interface JSONAPISingleResponse<T> {
  data: JSONAPIResource<T>;
  jsonapi: { [key: string]: string };
  links?: JSONAPILinks | null;
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

type TypedClient = ReturnType<typeof createClient<paths>>;

function handleError<T>(result: { data?: T; error?: unknown; response: Response }, endpoint: string): T {
  if (result.error !== undefined) {
    throw new ApiError(
      `API request failed: ${result.response.status} ${result.response.statusText}`,
      endpoint,
      result.response.status,
      sanitizeObject(result.error),
    );
  }
  return result.data as T;
}

function handleVoidResponse(result: { error?: unknown; response: Response }, endpoint: string): void {
  if (result.error !== undefined) {
    throw new ApiError(
      `API request failed: ${result.response.status} ${result.response.statusText}`,
      endpoint,
      result.response.status,
      sanitizeObject(result.error),
    );
  }
}

export class ApiClient {
  private client: TypedClient;
  private retryFetch: (input: Request) => Promise<Response>;
  private middleware: Middleware[];

  constructor(config: ApiClientConfig) {
    const environment = config.environment ?? 'production';
    validateHttps(config.serverUrl, environment);

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

  async healthCheck(): Promise<components['schemas']['HealthCheckResponse']> {
    const result = await this.client.GET('/health');
    return handleError(result, '/health');
  }

  async scoreNotes(request: ScoringRequest): Promise<ScoringResultJSONAPIResponse> {
    const result = await this.client.POST('/api/v2/scoring/score', {
      body: {
        data: {
          type: 'scoring-requests',
          attributes: request,
        },
      },
    });
    return handleError(result, '/api/v2/scoring/score')
  }

  async getNotes(messageId: string): Promise<NoteListJSONAPIResponse> {
    const result = await this.client.GET('/api/v2/notes', {
      params: {
        query: {
          'filter[platform_message_id]': messageId,
        },
      },
    });
    return handleError(result, '/api/v2/notes')
  }

  async getNote(noteId: string): Promise<NoteJSONAPIResponse> {
    const result = await this.client.GET('/api/v2/notes/{note_id}', {
      params: { path: { note_id: noteId } },
    });
    return handleError(result, `/api/v2/notes/${noteId}`)
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

    if (!community_server_id) {
      throw new ApiError(
        'Community server ID is required. Please provide a guild context.',
        '/api/v2/notes',
        400
      );
    }

    const noteAttributes: components['schemas']['NoteCreateAttributes'] = {
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
      },
      headers: this.profileHeaders(context),
    });
    return handleError(result, '/api/v2/notes')
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

    const ratingAttributes: components['schemas']['RatingCreateAttributes'] = {
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
      },
      headers: this.profileHeaders(context),
    });
    return handleError(result, '/api/v2/ratings')
  }

  async requestNote(request: NoteRequest, context?: UserContext): Promise<void> {
    const requestId = `discord-${request.messageId}-${Date.now()}`;

    const requestAttributes: components['schemas']['RequestCreateAttributes'] = {
      request_id: requestId,
      community_server_id: request.community_server_id,
      original_message_content: request.originalMessageContent ?? null,
      requested_by: request.userId,
      platform_message_id: request.messageId,
      platform_channel_id: request.discord_channel_id ?? null,
      platform_author_id: request.discord_author_id ?? null,
      platform_timestamp: request.discord_timestamp?.toISOString() ?? null,
      ...(request.fact_check_metadata && {
        metadata: request.fact_check_metadata,
        similarity_score: request.fact_check_metadata.similarity_score,
        dataset_name: request.fact_check_metadata.dataset_name,
        dataset_item_id: request.fact_check_metadata.dataset_item_id,
      }),
    };

    const result = await this.client.POST('/api/v2/requests', {
      body: {
        data: {
          type: 'requests',
          attributes: requestAttributes,
        },
      },
      headers: this.profileHeaders(context),
    });
    handleVoidResponse(result, '/api/v2/requests');
  }

  async listRequests(filters?: ListRequestsFilters, context?: UserContext): Promise<JSONAPIListResponse<RequestAttributes>> {
    const query: Record<string, unknown> = {};
    if (filters?.page) { query['page[number]'] = filters.page; }
    if (filters?.size) { query['page[size]'] = filters.size; }
    if (filters?.status) { query['filter[status]'] = filters.status; }
    if (filters?.requestedBy) { query['filter[requested_by]'] = filters.requestedBy; }
    if (filters?.communityServerId) { query['filter[community_server_id]'] = filters.communityServerId; }

    const result = await this.client.GET('/api/v2/requests', {
      params: { query: query },
      headers: this.profileHeaders(context),
    });
    return handleError(result, '/api/v2/requests')
  }

  async getRequest(requestId: string, context?: UserContext): Promise<JSONAPISingleResponse<RequestAttributes>> {
    const result = await this.client.GET('/api/v2/requests/{request_id}', {
      params: { path: { request_id: requestId } },
      headers: this.profileHeaders(context),
    });
    return handleError(result, `/api/v2/requests/${requestId}`)
  }

  async generateAiNote(requestId: string, context?: UserContext): Promise<NoteJSONAPIResponse> {
    const result = await this.client.POST('/api/v2/requests/{request_id}/ai-notes', {
      params: { path: { request_id: requestId } },
      headers: this.profileHeaders(context),
    });
    return handleError(result, `/api/v2/requests/${requestId}/ai-notes`)
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
    return handleError(result, '/api/v2/community-servers/lookup')
  }

  async updateCommunityServerName(
    platformId: string,
    name: string,
    serverStats?: Record<string, unknown>
  ): Promise<void> {
    const body: components['schemas']['CommunityServerNameUpdateRequest'] = {
      name,
      server_stats: serverStats ?? null,
    };
    const result = await this.client.PATCH('/api/v1/community-servers/{platform_community_server_id}/name', {
      params: { path: { platform_community_server_id: platformId } },
      body,
    });
    handleVoidResponse(result, `/api/v1/community-servers/${platformId}/name`);
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
    return handleError(result, '/api/v2/user-profiles/lookup')
  }

  async updateWelcomeMessageId(
    platformId: string,
    welcomeMessageId: string | null
  ): Promise<WelcomeMessageUpdateResponse> {
    const result = await this.client.PATCH('/api/v1/community-servers/{platform_community_server_id}/welcome-message', {
      params: { path: { platform_community_server_id: platformId } },
      body: { welcome_message_id: welcomeMessageId },
    });
    return handleError(result, `/api/v1/community-servers/${platformId}/welcome-message`)
  }

  async getRatingThresholds(): Promise<RatingThresholdsResponse> {
    const result = await this.client.GET('/api/v1/config/rating-thresholds');
    return handleError(result, '/api/v1/config/rating-thresholds')
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
      params: { query: query },
      headers: this.profileHeaders(context),
    });
    const jsonApiResponse = handleError(result, '/api/v2/notes')

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
    return handleError(result, `/api/v2/notes/${noteId}/ratings`)
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
      },
      headers: this.profileHeaders(context),
    });
    return handleError(result, `/api/v2/ratings/${ratingId}`)
  }

  async getGuildConfig(guildId: string): Promise<Record<string, unknown>> {
    const result = await this.client.GET('/api/v1/community-config/{community_server_id}', {
      params: { path: { community_server_id: guildId } },
    });
    const response = handleError(result, `/api/v1/community-config/${guildId}`);
    return (response as { config: Record<string, unknown> }).config;
  }

  async setGuildConfig(guildId: string, key: string, value: string | boolean | number, updatedBy: string, context?: UserContext): Promise<void> {
    const result = await this.client.PUT('/api/v1/community-config/{community_server_id}', {
      params: { path: { community_server_id: guildId } },
      body: { key, value: String(value), updated_by: updatedBy },
      headers: this.profileHeaders(context),
    });
    handleVoidResponse(result, `/api/v1/community-config/${guildId}`);
  }

  async resetGuildConfig(guildId: string, context?: UserContext): Promise<void> {
    const result = await this.client.DELETE('/api/v1/community-config/{community_server_id}', {
      params: { path: { community_server_id: guildId } },
      headers: this.profileHeaders(context),
    });
    handleVoidResponse(result, `/api/v1/community-config/${guildId}`);
  }

  async getNoteScore(noteId: string): Promise<NoteScoreJSONAPIResponse> {
    const result = await this.client.GET('/api/v2/scoring/notes/{note_id}/score', {
      params: { path: { note_id: noteId } },
    });
    return handleError(result, `/api/v2/scoring/notes/${noteId}/score`)
  }

  async getBatchNoteScores(noteIds: string[]): Promise<BatchScoreJSONAPIResponse> {
    const result = await this.client.POST('/api/v2/scoring/notes/batch-scores', {
      body: {
        data: {
          type: 'batch-score-requests',
          attributes: { note_ids: noteIds },
        },
      },
    });
    return handleError(result, '/api/v2/scoring/notes/batch-scores')
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
      params: { query: query },
    });
    return handleError(result, '/api/v2/scoring/notes/top')
  }

  async getScoringStatus(): Promise<ScoringStatusJSONAPIResponse> {
    const result = await this.client.GET('/api/v2/scoring/status');
    return handleError(result, '/api/v2/scoring/status')
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
      params: { query: query },
    });
    return handleError(result, '/api/v2/monitored-channels')
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
            score_threshold: 0.1,
            limit,
          },
        },
      },
    });
    return handleError(result, '/api/v2/similarity-searches')
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
        },
        headers: this.profileHeaders(context),
      });
      return handleError(result, '/api/v2/monitored-channels')
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
    return handleError(result, `/api/v1/community-servers/${communityServerId}/llm-config`)
  }

  async createLLMConfig(communityServerId: string, config: LLMConfigCreate, context?: UserContext): Promise<LLMConfigResponse> {
    const result = await this.client.POST('/api/v1/community-servers/{community_server_id}/llm-config', {
      params: { path: { community_server_id: communityServerId } },
      body: config,
      headers: this.profileHeaders(context),
    });
    return handleError(result, `/api/v1/community-servers/${communityServerId}/llm-config`)
  }

  async getMonitoredChannelByUuid(uuid: string): Promise<JSONAPISingleResponse<MonitoredChannelJSONAPIAttributes>> {
    const result = await this.client.GET('/api/v2/monitored-channels/{channel_uuid}', {
      params: { path: { channel_uuid: uuid } },
    });
    return handleError(result, `/api/v2/monitored-channels/${uuid}`)
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
      },
      headers: this.profileHeaders(context),
    });
    return handleError(result, `/api/v2/monitored-channels/${existing.data.id}`)
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
    handleVoidResponse(result, `/api/v2/monitored-channels/${existing.data.id}`);
    return true;
  }

  async forcePublishNote(noteId: string, context?: UserContext): Promise<NoteJSONAPIResponse> {
    const result = await this.client.POST('/api/v2/notes/{note_id}/force-publish', {
      params: { path: { note_id: noteId } },
      headers: this.profileHeaders(context),
    });
    return handleError(result, `/api/v2/notes/${noteId}/force-publish`)
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
      body: body,
      headers: this.profileHeaders(context),
    });
    return handleError(result, `/api/v1/community-servers/${communityServerId}/admins`)
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
    return handleError(result, `/api/v1/community-servers/${communityServerId}/admins/${userDiscordId}`)
  }

  async listCommunityAdmins(communityServerId: string): Promise<CommunityAdminResponse[]> {
    const result = await this.client.GET('/api/v1/community-servers/{community_server_id}/admins', {
      params: { path: { community_server_id: communityServerId } },
    });
    return handleError(result, `/api/v1/community-servers/${communityServerId}/admins`)
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
      },
    });
    return handleError(result, '/api/v2/previously-seen-messages/check')
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
      },
    });
    handleVoidResponse(result, '/api/v2/note-publisher-posts');
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
      params: { query: query },
    });
    return handleError(result, '/api/v2/note-publisher-posts')
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
      params: { query: query },
    });
    return handleError(result, '/api/v2/note-publisher-posts')
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
      params: { query: query },
    });
    return handleError(result, '/api/v2/note-publisher-configs')
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
        },
        headers: this.profileHeaders(context),
      });
      return handleError(result, `/api/v2/note-publisher-configs/${existingConfig.id}`)
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
        },
        headers: this.profileHeaders(context),
      });
      return handleError(result, '/api/v2/note-publisher-configs')
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
      params: { query: query },
      headers: this.profileHeaders(context),
    });
    const jsonApiResponse = handleError(result, '/api/v2/notes')

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
      },
    });
    return handleError(result, '/api/v2/bulk-scans')
  }

  async getBulkScanResults(scanId: string): Promise<BulkScanResultsResponse> {
    const result = await this.client.GET('/api/v2/bulk-scans/{scan_id}', {
      params: { path: { scan_id: scanId } },
    });
    return handleError(result, `/api/v2/bulk-scans/${scanId}`)
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
      },
    });
    return handleError(result, `/api/v2/bulk-scans/${scanId}/note-requests`)
  }

  async checkRecentScan(communityServerId: string): Promise<RecentScanResponse> {
    const result = await this.client.GET('/api/v2/bulk-scans/communities/{community_server_id}/recent', {
      params: { path: { community_server_id: communityServerId } },
    });
    return handleError(result, `/api/v2/bulk-scans/communities/${communityServerId}/recent`)
  }

  async getLatestScan(communityServerId: string): Promise<LatestScanResponse> {
    const result = await this.client.GET('/api/v2/bulk-scans/communities/{community_server_id}/latest', {
      params: { path: { community_server_id: communityServerId } },
    });
    return handleError(result, `/api/v2/bulk-scans/communities/${communityServerId}/latest`)
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
      },
    });
    return handleError(result, '/api/v2/bulk-scans/explanations')
  }

  async getClearPreview(
    communityServerId: string,
    type: 'requests' | 'notes',
    mode: string,
    context?: UserContext
  ): Promise<ClearPreviewResult> {
    const headers = this.profileHeaders(context);
    const params = { path: { community_server_id: communityServerId }, query: { mode } };

    if (type === 'requests') {
      const result = await this.client.GET(
        '/api/v2/community-servers/{community_server_id}/clear-requests/preview',
        { params, headers }
      );
      const data = handleError(result, `/api/v2/community-servers/${communityServerId}/clear-requests/preview`);
      return { wouldDeleteCount: data.would_delete_count, message: data.message };
    }

    const result = await this.client.GET(
      '/api/v2/community-servers/{community_server_id}/clear-notes/preview',
      { params, headers }
    );
    const data = handleError(result, `/api/v2/community-servers/${communityServerId}/clear-notes/preview`);
    return { wouldDeleteCount: data.would_delete_count, message: data.message };
  }

  async executeClear(
    communityServerId: string,
    type: 'requests' | 'notes',
    mode: string,
    context?: UserContext
  ): Promise<ClearResult> {
    const headers = this.profileHeaders(context);
    const params = { path: { community_server_id: communityServerId }, query: { mode } };

    if (type === 'requests') {
      const result = await this.client.DELETE(
        '/api/v2/community-servers/{community_server_id}/clear-requests',
        { params, headers }
      );
      const data = handleError(result, `/api/v2/community-servers/${communityServerId}/clear-requests`);
      return { deletedCount: data.deleted_count, message: data.message };
    }

    const result = await this.client.DELETE(
      '/api/v2/community-servers/{community_server_id}/clear-notes',
      { params, headers }
    );
    const data = handleError(result, `/api/v2/community-servers/${communityServerId}/clear-notes`);
    return { deletedCount: data.deleted_count, message: data.message };
  }

  async updateFlashpointDetection(
    platformCommunityServerId: string,
    enabled: boolean,
    context?: UserContext
  ): Promise<FlashpointDetectionUpdateResponse> {
    const result = await this.client.PATCH('/api/v1/community-servers/{platform_community_server_id}/flashpoint-detection', {
      params: { path: { platform_community_server_id: platformCommunityServerId } },
      body: { enabled },
      headers: this.profileHeaders(context),
    });
    return handleError(result, `/api/v1/community-servers/${platformCommunityServerId}/flashpoint-detection`)
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
        },
      });
      const response = handleError(result, '/api/v2/claim-relevance-checks')

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
