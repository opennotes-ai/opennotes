import { ApiClient, type RequestAttributes, type JSONAPIResource } from '../lib/api-client.js';
import { logger } from '../logger.js';
import {
  ServiceResult,
  ListRequestsInput,
  ListRequestsResult,
  ErrorCode,
  ServiceError,
} from './types.js';
import type { RateLimiterInterface } from './RateLimitFactory.js';
import { getErrorMessage, getErrorStack, hasMessage } from '../utils/error-handlers.js';
import type { RequestItem, RequestStatus } from '../lib/types.js';

export class ListRequestsService {
  constructor(
    private apiClient: ApiClient,
    private rateLimiter: RateLimiterInterface
  ) {}

  async execute(input: ListRequestsInput): Promise<ServiceResult<ListRequestsResult>> {
    const validationError = this.validate(input);
    if (validationError) {
      return { success: false, error: validationError };
    }

    const rateLimit = await this.rateLimiter.check(input.userId);
    if (!rateLimit.allowed) {
      return {
        success: false,
        error: this.rateLimiter.createError(rateLimit.resetAt),
      };
    }

    try {
      const response = await this.apiClient.listRequests({
        page: input.page,
        size: input.size,
        status: input.status,
        requestedBy: input.myRequestsOnly ? input.userId : undefined,
        communityServerId: input.communityServerId,
      });

      const requests: RequestItem[] = response.data.map(
        (resource: JSONAPIResource<RequestAttributes>) => ({
          id: resource.id,
          request_id: resource.attributes.request_id,
          requested_by: resource.attributes.requested_by,
          requested_at: resource.attributes.requested_at ?? new Date().toISOString(),
          status: resource.attributes.status as RequestStatus,
          note_id: resource.attributes.note_id ?? undefined,
          created_at: resource.attributes.created_at ?? new Date().toISOString(),
          updated_at: resource.attributes.updated_at ?? undefined,
          platform_message_id: resource.attributes.platform_message_id ?? undefined,
          content: resource.attributes.content ?? undefined,
          community_server_id: resource.attributes.community_server_id ?? undefined,
          metadata: resource.attributes.metadata ?? undefined,
        })
      );

      const total = response.meta?.count ?? requests.length;

      logger.info('Requests listed via service', {
        userId: input.userId,
        page: input.page,
        size: input.size,
        status: input.status,
        myRequestsOnly: input.myRequestsOnly,
        communityServerId: input.communityServerId,
        total,
      });

      return {
        success: true,
        data: {
          requests,
          total,
          page: input.page ?? 1,
          size: input.size ?? 20,
        },
      };
    } catch (error: unknown) {
      logger.error('Failed to list requests in service', {
        errorMessage: getErrorMessage(error),
        errorStack: getErrorStack(error),
        userId: input.userId,
        page: input.page,
        status: input.status,
      });

      return {
        success: false,
        error: this.mapError(error),
      };
    }
  }

  private validate(input: ListRequestsInput): ServiceError | null {
    if (!input.userId || input.userId.trim().length === 0) {
      return {
        code: ErrorCode.VALIDATION_ERROR,
        message: 'User ID is required',
      };
    }

    if (input.page !== undefined && input.page < 1) {
      return {
        code: ErrorCode.VALIDATION_ERROR,
        message: 'Page must be at least 1',
      };
    }

    if (input.size !== undefined && (input.size < 1 || input.size > 100)) {
      return {
        code: ErrorCode.VALIDATION_ERROR,
        message: 'Page size must be between 1 and 100',
      };
    }

    return null;
  }

  private mapError(error: unknown): ServiceError {
    const message = hasMessage(error) ? error.message : '';

    if (message.includes('401') || message.includes('403')) {
      return {
        code: ErrorCode.UNAUTHORIZED,
        message: 'Unauthorized to list requests',
      };
    }

    return {
      code: ErrorCode.API_ERROR,
      message: 'Failed to retrieve requests. Please try again later.',
    };
  }
}
