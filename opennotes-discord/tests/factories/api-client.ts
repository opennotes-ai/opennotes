import { Factory } from 'fishery';
import { jest } from '@jest/globals';
import type {
  NoteJSONAPIResponse,
  NoteListJSONAPIResponse,
  NoteListJSONAPIResponseWithPagination,
  RatingJSONAPIResponse,
  RatingListJSONAPIResponse,
  ScoringResultJSONAPIResponse,
  NoteScoreJSONAPIResponse,
  BatchScoreJSONAPIResponse,
  TopNotesJSONAPIResponse,
  ScoringStatusJSONAPIResponse,
  CommunityServerJSONAPIResponse,
  JSONAPIListResponse,
  JSONAPISingleResponse,
  MonitoredChannelJSONAPIAttributes,
  NotePublisherConfigJSONAPIAttributes,
  NotePublisherPostJSONAPIAttributes,
  RequestAttributes,
  RatingThresholdsResponse,
  WelcomeMessageUpdateResponse,
  LLMConfigResponse,
  CommunityAdminResponse,
  RemoveCommunityAdminResponse,
  PreviouslySeenCheckJSONAPIResponse,
  SimilaritySearchResultAttributes,
  BulkScanSingleResponse,
  BulkScanResultsResponse,
  RecentScanResponse,
  LatestScanResponse,
  NoteRequestsResultResponse,
  ExplanationResultResponse,
  NoteStatus,
  ScoreConfidence,
} from '../../src/lib/api-client.js';

export interface MockApiClient {
  healthCheck: jest.Mock<() => Promise<{ status: string; version: string }>>;
  scoreNotes: jest.Mock<() => Promise<ScoringResultJSONAPIResponse>>;
  getNotes: jest.Mock<() => Promise<NoteListJSONAPIResponse>>;
  getNote: jest.Mock<() => Promise<NoteJSONAPIResponse>>;
  createNote: jest.Mock<() => Promise<NoteJSONAPIResponse>>;
  rateNote: jest.Mock<() => Promise<RatingJSONAPIResponse>>;
  requestNote: jest.Mock<() => Promise<void>>;
  listRequests: jest.Mock<() => Promise<JSONAPIListResponse<RequestAttributes>>>;
  getRequest: jest.Mock<() => Promise<JSONAPISingleResponse<RequestAttributes>>>;
  generateAiNote: jest.Mock<() => Promise<NoteJSONAPIResponse>>;
  getCommunityServerByPlatformId: jest.Mock<() => Promise<CommunityServerJSONAPIResponse>>;
  updateWelcomeMessageId: jest.Mock<() => Promise<WelcomeMessageUpdateResponse>>;
  getRatingThresholds: jest.Mock<() => Promise<RatingThresholdsResponse>>;
  listNotesWithStatus: jest.Mock<() => Promise<NoteListJSONAPIResponseWithPagination>>;
  getRatingsForNote: jest.Mock<() => Promise<RatingListJSONAPIResponse>>;
  updateRating: jest.Mock<() => Promise<RatingJSONAPIResponse>>;
  getGuildConfig: jest.Mock<() => Promise<Record<string, unknown>>>;
  setGuildConfig: jest.Mock<() => Promise<void>>;
  resetGuildConfig: jest.Mock<() => Promise<void>>;
  getNoteScore: jest.Mock<() => Promise<NoteScoreJSONAPIResponse>>;
  getBatchNoteScores: jest.Mock<() => Promise<BatchScoreJSONAPIResponse>>;
  getTopNotes: jest.Mock<() => Promise<TopNotesJSONAPIResponse>>;
  getScoringStatus: jest.Mock<() => Promise<ScoringStatusJSONAPIResponse>>;
  listMonitoredChannels: jest.Mock<() => Promise<JSONAPIListResponse<MonitoredChannelJSONAPIAttributes>>>;
  similaritySearch: jest.Mock<() => Promise<JSONAPISingleResponse<SimilaritySearchResultAttributes>>>;
  createMonitoredChannel: jest.Mock<() => Promise<JSONAPISingleResponse<MonitoredChannelJSONAPIAttributes> | null>>;
  listLLMConfigs: jest.Mock<() => Promise<LLMConfigResponse[]>>;
  createLLMConfig: jest.Mock<() => Promise<LLMConfigResponse>>;
  getMonitoredChannelByUuid: jest.Mock<() => Promise<JSONAPISingleResponse<MonitoredChannelJSONAPIAttributes>>>;
  getMonitoredChannel: jest.Mock<() => Promise<JSONAPISingleResponse<MonitoredChannelJSONAPIAttributes> | null>>;
  updateMonitoredChannel: jest.Mock<() => Promise<JSONAPISingleResponse<MonitoredChannelJSONAPIAttributes> | null>>;
  deleteMonitoredChannel: jest.Mock<() => Promise<boolean>>;
  forcePublishNote: jest.Mock<() => Promise<NoteJSONAPIResponse>>;
  addCommunityAdmin: jest.Mock<() => Promise<CommunityAdminResponse>>;
  removeCommunityAdmin: jest.Mock<() => Promise<RemoveCommunityAdminResponse>>;
  listCommunityAdmins: jest.Mock<() => Promise<CommunityAdminResponse[]>>;
  checkPreviouslySeen: jest.Mock<() => Promise<PreviouslySeenCheckJSONAPIResponse>>;
  recordNotePublisher: jest.Mock<() => Promise<void>>;
  checkNoteDuplicate: jest.Mock<() => Promise<JSONAPIListResponse<NotePublisherPostJSONAPIAttributes>>>;
  getLastNotePost: jest.Mock<() => Promise<JSONAPIListResponse<NotePublisherPostJSONAPIAttributes>>>;
  getNotePublisherConfig: jest.Mock<() => Promise<JSONAPIListResponse<NotePublisherConfigJSONAPIAttributes>>>;
  setNotePublisherConfig: jest.Mock<() => Promise<JSONAPISingleResponse<NotePublisherConfigJSONAPIAttributes>>>;
  listNotesRatedByUser: jest.Mock<() => Promise<NoteListJSONAPIResponseWithPagination>>;
  initiateBulkScan: jest.Mock<() => Promise<BulkScanSingleResponse>>;
  getBulkScanResults: jest.Mock<() => Promise<BulkScanResultsResponse>>;
  createNoteRequestsFromScan: jest.Mock<() => Promise<NoteRequestsResultResponse>>;
  checkRecentScan: jest.Mock<() => Promise<RecentScanResponse>>;
  getLatestScan: jest.Mock<() => Promise<LatestScanResponse>>;
  generateScanExplanation: jest.Mock<() => Promise<ExplanationResultResponse>>;
}

export interface ApiClientTransientParams {
  healthCheckStatus?: string;
  healthCheckVersion?: string;
  healthCheckShouldFail?: boolean;
  defaultNoteId?: string;
  defaultNoteSummary?: string;
  defaultNoteStatus?: NoteStatus;
  defaultCommunityServerId?: string;
  defaultScore?: number;
  defaultConfidence?: ScoreConfidence;
  defaultRatingId?: string;
  defaultHelpfulnessLevel?: 'HELPFUL' | 'NOT_HELPFUL';
}

function createMockNoteJSONAPIResponse(params: {
  id?: string;
  summary?: string;
  status?: NoteStatus;
  communityServerId?: string;
  sequence?: number;
}): NoteJSONAPIResponse {
  const seq = params.sequence ?? 1;
  return {
    data: {
      type: 'notes',
      id: params.id ?? `note-${seq}`,
      attributes: {
        summary: params.summary ?? 'Test note summary',
        classification: 'NOT_MISLEADING',
        status: params.status ?? 'NEEDS_MORE_RATINGS',
        helpfulness_score: 0.5,
        author_participant_id: `author-${seq}`,
        community_server_id: params.communityServerId ?? `community-${seq}`,
        channel_id: null,
        request_id: null,
        ratings_count: 0,
        force_published: false,
        force_published_at: null,
        created_at: new Date().toISOString(),
        updated_at: null,
      },
    },
    jsonapi: { version: '1.1' },
  };
}

function createMockNoteListJSONAPIResponse(params: {
  noteId?: string;
  summary?: string;
  status?: NoteStatus;
  communityServerId?: string;
  sequence?: number;
}): NoteListJSONAPIResponse {
  const noteResponse = createMockNoteJSONAPIResponse(params);
  return {
    data: [noteResponse.data],
    jsonapi: { version: '1.1' },
    meta: { count: 1 },
  };
}

function createMockRatingJSONAPIResponse(params: {
  id?: string;
  noteId?: string;
  helpfulnessLevel?: 'HELPFUL' | 'NOT_HELPFUL';
  sequence?: number;
}): RatingJSONAPIResponse {
  const seq = params.sequence ?? 1;
  return {
    data: {
      type: 'ratings',
      id: params.id ?? `rating-${seq}`,
      attributes: {
        note_id: params.noteId ?? `note-${seq}`,
        rater_participant_id: `rater-${seq}`,
        helpfulness_level: params.helpfulnessLevel ?? 'HELPFUL',
        created_at: new Date().toISOString(),
        updated_at: null,
      },
    },
    jsonapi: { version: '1.1' },
  };
}

function createMockCommunityServerJSONAPIResponse(params: {
  id?: string;
  platformId?: string;
  sequence?: number;
}): CommunityServerJSONAPIResponse {
  const seq = params.sequence ?? 1;
  return {
    data: {
      type: 'community-servers',
      id: params.id ?? `community-${seq}`,
      attributes: {
        platform: 'discord',
        platform_id: params.platformId ?? `platform-${seq}`,
        name: `Test Community ${seq}`,
        is_active: true,
        is_public: true,
      },
    },
    jsonapi: { version: '1.1' },
  };
}

function createMockNoteScoreJSONAPIResponse(params: {
  noteId?: string;
  score?: number;
  confidence?: ScoreConfidence;
  sequence?: number;
}): NoteScoreJSONAPIResponse {
  const seq = params.sequence ?? 1;
  return {
    data: {
      type: 'note-scores',
      id: params.noteId ?? `note-${seq}`,
      attributes: {
        score: params.score ?? 0.75,
        confidence: params.confidence ?? 'standard',
        algorithm: 'bayesian',
        rating_count: 10,
        tier: 2,
        tier_name: 'Tier 2',
        calculated_at: new Date().toISOString(),
        content: null,
      },
    },
    jsonapi: { version: '1.0' },
  };
}

export const apiClientFactory = Factory.define<MockApiClient, ApiClientTransientParams>(
  ({ sequence, transientParams }) => {
    const {
      healthCheckStatus = 'healthy',
      healthCheckVersion = '1.0.0',
      healthCheckShouldFail = false,
      defaultNoteId,
      defaultNoteSummary,
      defaultNoteStatus,
      defaultCommunityServerId,
      defaultScore,
      defaultConfidence,
      defaultRatingId,
      defaultHelpfulnessLevel,
    } = transientParams;

    const noteParams = {
      id: defaultNoteId,
      summary: defaultNoteSummary,
      status: defaultNoteStatus,
      communityServerId: defaultCommunityServerId,
      sequence,
    };

    const ratingParams = {
      id: defaultRatingId,
      noteId: defaultNoteId,
      helpfulnessLevel: defaultHelpfulnessLevel,
      sequence,
    };

    const scoreParams = {
      noteId: defaultNoteId,
      score: defaultScore,
      confidence: defaultConfidence,
      sequence,
    };

    const communityParams = {
      id: defaultCommunityServerId,
      sequence,
    };

    return {
      healthCheck: healthCheckShouldFail
        ? jest.fn<() => Promise<{ status: string; version: string }>>().mockRejectedValue(new Error('Health check failed'))
        : jest.fn<() => Promise<{ status: string; version: string }>>().mockResolvedValue({
            status: healthCheckStatus,
            version: healthCheckVersion,
          }),
      scoreNotes: jest.fn<() => Promise<ScoringResultJSONAPIResponse>>().mockResolvedValue({
        data: {
          type: 'scoring-results',
          id: `scoring-${sequence}`,
          attributes: {
            scored_notes: [],
            helpful_scores: [],
            auxiliary_info: [],
          },
        },
        jsonapi: { version: '1.0' },
      }),
      getNotes: jest.fn<() => Promise<NoteListJSONAPIResponse>>().mockResolvedValue(
        createMockNoteListJSONAPIResponse(noteParams)
      ),
      getNote: jest.fn<() => Promise<NoteJSONAPIResponse>>().mockResolvedValue(
        createMockNoteJSONAPIResponse(noteParams)
      ),
      createNote: jest.fn<() => Promise<NoteJSONAPIResponse>>().mockResolvedValue(
        createMockNoteJSONAPIResponse(noteParams)
      ),
      rateNote: jest.fn<() => Promise<RatingJSONAPIResponse>>().mockResolvedValue(
        createMockRatingJSONAPIResponse(ratingParams)
      ),
      requestNote: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
      listRequests: jest.fn<() => Promise<JSONAPIListResponse<RequestAttributes>>>().mockResolvedValue({
        data: [],
        jsonapi: { version: '1.1' },
        meta: { count: 0 },
      }),
      getRequest: jest.fn<() => Promise<JSONAPISingleResponse<RequestAttributes>>>().mockResolvedValue({
        data: {
          type: 'requests',
          id: `request-${sequence}`,
          attributes: {
            request_id: `req-${sequence}`,
            requested_by: `user-${sequence}`,
            status: 'pending',
            created_at: new Date().toISOString(),
          },
        },
        jsonapi: { version: '1.1' },
      }),
      generateAiNote: jest.fn<() => Promise<NoteJSONAPIResponse>>().mockResolvedValue(
        createMockNoteJSONAPIResponse(noteParams)
      ),
      getCommunityServerByPlatformId: jest.fn<() => Promise<CommunityServerJSONAPIResponse>>().mockResolvedValue(
        createMockCommunityServerJSONAPIResponse(communityParams)
      ),
      updateWelcomeMessageId: jest.fn<() => Promise<WelcomeMessageUpdateResponse>>().mockResolvedValue({
        id: defaultCommunityServerId ?? `community-${sequence}`,
        platform_id: `platform-${sequence}`,
        welcome_message_id: null,
      }),
      getRatingThresholds: jest.fn<() => Promise<RatingThresholdsResponse>>().mockResolvedValue({
        min_ratings_needed: 5,
        min_raters_per_note: 3,
      }),
      listNotesWithStatus: jest.fn<() => Promise<NoteListJSONAPIResponseWithPagination>>().mockResolvedValue({
        ...createMockNoteListJSONAPIResponse(noteParams),
        total: 1,
        page: 1,
        size: 20,
      }),
      getRatingsForNote: jest.fn<() => Promise<RatingListJSONAPIResponse>>().mockResolvedValue({
        data: [createMockRatingJSONAPIResponse(ratingParams).data],
        jsonapi: { version: '1.1' },
      }),
      updateRating: jest.fn<() => Promise<RatingJSONAPIResponse>>().mockResolvedValue(
        createMockRatingJSONAPIResponse(ratingParams)
      ),
      getGuildConfig: jest.fn<() => Promise<Record<string, unknown>>>().mockResolvedValue({}),
      setGuildConfig: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
      resetGuildConfig: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
      getNoteScore: jest.fn<() => Promise<NoteScoreJSONAPIResponse>>().mockResolvedValue(
        createMockNoteScoreJSONAPIResponse(scoreParams)
      ),
      getBatchNoteScores: jest.fn<() => Promise<BatchScoreJSONAPIResponse>>().mockResolvedValue({
        data: [createMockNoteScoreJSONAPIResponse(scoreParams).data],
        jsonapi: { version: '1.0' },
        meta: {
          total_requested: 1,
          total_found: 1,
          not_found: [],
        },
      }),
      getTopNotes: jest.fn<() => Promise<TopNotesJSONAPIResponse>>().mockResolvedValue({
        data: [createMockNoteScoreJSONAPIResponse(scoreParams).data],
        jsonapi: { version: '1.0' },
        meta: {
          total_count: 1,
          current_tier: 2,
        },
      }),
      getScoringStatus: jest.fn<() => Promise<ScoringStatusJSONAPIResponse>>().mockResolvedValue({
        data: {
          type: 'scoring-status',
          id: 'status',
          attributes: {
            current_note_count: 100,
            active_tier: {
              level: 2,
              name: 'Tier 2',
              scorer_components: ['base', 'bayesian'],
            },
            data_confidence: 'medium',
            tier_thresholds: {},
            performance_metrics: {
              avg_scoring_time_ms: 50,
              scorer_success_rate: 0.99,
              total_scoring_operations: 1000,
              failed_scoring_operations: 10,
            },
            warnings: [],
            configuration: {},
          },
        },
        jsonapi: { version: '1.0' },
      }),
      listMonitoredChannels: jest.fn<() => Promise<JSONAPIListResponse<MonitoredChannelJSONAPIAttributes>>>().mockResolvedValue({
        data: [],
        jsonapi: { version: '1.1' },
      }),
      similaritySearch: jest.fn<() => Promise<JSONAPISingleResponse<SimilaritySearchResultAttributes>>>().mockResolvedValue({
        data: {
          type: 'similarity-searches',
          id: `search-${sequence}`,
          attributes: {
            matches: [],
            query_text: '',
            dataset_tags: [],
            similarity_threshold: 0.8,
            score_threshold: 0.0,
            total_matches: 0,
          },
        },
        jsonapi: { version: '1.1' },
      }),
      createMonitoredChannel: jest.fn<() => Promise<JSONAPISingleResponse<MonitoredChannelJSONAPIAttributes> | null>>().mockResolvedValue({
        data: {
          type: 'monitored-channels',
          id: `channel-${sequence}`,
          attributes: {
            community_server_id: defaultCommunityServerId ?? `community-${sequence}`,
            channel_id: `discord-channel-${sequence}`,
            enabled: true,
            similarity_threshold: 0.8,
            dataset_tags: [],
          },
        },
        jsonapi: { version: '1.1' },
      }),
      listLLMConfigs: jest.fn<() => Promise<LLMConfigResponse[]>>().mockResolvedValue([]),
      createLLMConfig: jest.fn<() => Promise<LLMConfigResponse>>().mockResolvedValue({
        id: `llm-config-${sequence}`,
        community_server_id: defaultCommunityServerId ?? `community-${sequence}`,
        provider: 'openai',
        api_key_preview: '****',
        enabled: true,
        settings: {},
        daily_request_limit: null,
        monthly_request_limit: null,
        daily_token_limit: null,
        monthly_token_limit: null,
        daily_spend_limit: null,
        monthly_spend_limit: null,
        current_daily_requests: 0,
        current_monthly_requests: 0,
        current_daily_tokens: 0,
        current_monthly_tokens: 0,
        current_daily_spend: 0,
        current_monthly_spend: 0,
        last_daily_reset: null,
        last_monthly_reset: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        created_by: null,
      }),
      getMonitoredChannelByUuid: jest.fn<() => Promise<JSONAPISingleResponse<MonitoredChannelJSONAPIAttributes>>>().mockResolvedValue({
        data: {
          type: 'monitored-channels',
          id: `channel-${sequence}`,
          attributes: {
            community_server_id: defaultCommunityServerId ?? `community-${sequence}`,
            channel_id: `discord-channel-${sequence}`,
            enabled: true,
            similarity_threshold: 0.8,
            dataset_tags: [],
          },
        },
        jsonapi: { version: '1.1' },
      }),
      getMonitoredChannel: jest.fn<() => Promise<JSONAPISingleResponse<MonitoredChannelJSONAPIAttributes> | null>>().mockResolvedValue(null),
      updateMonitoredChannel: jest.fn<() => Promise<JSONAPISingleResponse<MonitoredChannelJSONAPIAttributes> | null>>().mockResolvedValue(null),
      deleteMonitoredChannel: jest.fn<() => Promise<boolean>>().mockResolvedValue(true),
      forcePublishNote: jest.fn<() => Promise<NoteJSONAPIResponse>>().mockResolvedValue(
        createMockNoteJSONAPIResponse({ ...noteParams, status: 'CURRENTLY_RATED_HELPFUL' })
      ),
      addCommunityAdmin: jest.fn<() => Promise<CommunityAdminResponse>>().mockResolvedValue({
        profile_id: `profile-${sequence}`,
        display_name: `User ${sequence}`,
        avatar_url: null,
        discord_id: `user-${sequence}`,
        admin_sources: ['community_role'],
        is_opennotes_admin: false,
        community_role: 'admin',
        joined_at: new Date().toISOString(),
      }),
      removeCommunityAdmin: jest.fn<() => Promise<RemoveCommunityAdminResponse>>().mockResolvedValue({
        success: true,
        message: 'Admin removed successfully',
        profile_id: `profile-${sequence}`,
        previous_role: 'admin',
        new_role: 'member',
      }),
      listCommunityAdmins: jest.fn<() => Promise<CommunityAdminResponse[]>>().mockResolvedValue([]),
      checkPreviouslySeen: jest.fn<() => Promise<PreviouslySeenCheckJSONAPIResponse>>().mockResolvedValue({
        data: {
          type: 'previously-seen-check',
          id: `check-${sequence}`,
          attributes: {
            should_auto_publish: false,
            should_auto_request: false,
            autopublish_threshold: 0.95,
            autorequest_threshold: 0.85,
            matches: [],
            top_match: null,
          },
        },
        jsonapi: { version: '1.1' },
      }),
      recordNotePublisher: jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
      checkNoteDuplicate: jest.fn<() => Promise<JSONAPIListResponse<NotePublisherPostJSONAPIAttributes>>>().mockResolvedValue({
        data: [],
        jsonapi: { version: '1.1' },
      }),
      getLastNotePost: jest.fn<() => Promise<JSONAPIListResponse<NotePublisherPostJSONAPIAttributes>>>().mockResolvedValue({
        data: [],
        jsonapi: { version: '1.1' },
      }),
      getNotePublisherConfig: jest.fn<() => Promise<JSONAPIListResponse<NotePublisherConfigJSONAPIAttributes>>>().mockResolvedValue({
        data: [],
        jsonapi: { version: '1.1' },
      }),
      setNotePublisherConfig: jest.fn<() => Promise<JSONAPISingleResponse<NotePublisherConfigJSONAPIAttributes>>>().mockResolvedValue({
        data: {
          type: 'note-publisher-configs',
          id: `config-${sequence}`,
          attributes: {
            community_server_id: defaultCommunityServerId ?? `community-${sequence}`,
            channel_id: null,
            enabled: true,
            threshold: null,
          },
        },
        jsonapi: { version: '1.1' },
      }),
      listNotesRatedByUser: jest.fn<() => Promise<NoteListJSONAPIResponseWithPagination>>().mockResolvedValue({
        ...createMockNoteListJSONAPIResponse(noteParams),
        total: 1,
        page: 1,
        size: 20,
      }),
      initiateBulkScan: jest.fn<() => Promise<BulkScanSingleResponse>>().mockResolvedValue({
        data: {
          type: 'bulk-scans',
          id: `scan-${sequence}`,
          attributes: {
            status: 'pending',
            initiated_at: new Date().toISOString(),
            messages_scanned: 0,
            messages_flagged: 0,
          },
        },
        jsonapi: { version: '1.1' },
      } as unknown as BulkScanSingleResponse),
      getBulkScanResults: jest.fn<() => Promise<BulkScanResultsResponse>>().mockResolvedValue({
        data: {
          type: 'bulk-scans',
          id: `scan-${sequence}`,
          attributes: {
            status: 'completed',
            initiated_at: new Date().toISOString(),
            completed_at: new Date().toISOString(),
            messages_scanned: 100,
            messages_flagged: 5,
          },
        },
        jsonapi: { version: '1.1' },
      } as unknown as BulkScanResultsResponse),
      createNoteRequestsFromScan: jest.fn<() => Promise<NoteRequestsResultResponse>>().mockResolvedValue({
        data: {
          type: 'note-requests-results',
          id: `result-${sequence}`,
          attributes: {
            requests_created: 0,
            notes_generated: 0,
            errors: [],
          },
        },
        jsonapi: { version: '1.1' },
      } as unknown as NoteRequestsResultResponse),
      checkRecentScan: jest.fn<() => Promise<RecentScanResponse>>().mockResolvedValue({
        data: {
          type: 'recent-scan-check',
          id: `check-${sequence}`,
          attributes: {
            has_recent_scan: false,
          },
        },
        jsonapi: { version: '1.1' },
      } as unknown as RecentScanResponse),
      getLatestScan: jest.fn<() => Promise<LatestScanResponse>>().mockResolvedValue({
        data: {
          type: 'bulk-scans',
          id: `scan-${sequence}`,
          attributes: {
            status: 'completed',
            initiated_at: new Date().toISOString(),
            messages_scanned: 50,
            messages_flagged: 2,
          },
        },
        jsonapi: { version: '1.1' },
      } as unknown as LatestScanResponse),
      generateScanExplanation: jest.fn<() => Promise<ExplanationResultResponse>>().mockResolvedValue({
        data: {
          type: 'scan-explanations',
          id: `explanation-${sequence}`,
          attributes: {
            explanation: 'Test explanation',
            confidence: 0.8,
          },
        },
        jsonapi: { version: '1.1' },
      } as ExplanationResultResponse),
    };
  }
);
