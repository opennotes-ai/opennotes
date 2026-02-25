import type { Middleware } from 'openapi-fetch';
import { logger } from '../logger.js';
import { getIdentityToken, isRunningOnGCP } from '../utils/gcp-auth.js';
import { createDiscordClaimsToken } from '../utils/discord-claims.js';
import { ApiError } from './errors.js';
import { nanoid } from 'nanoid';

export interface AuthMiddlewareConfig {
  baseUrl: string;
  apiKey?: string;
  internalServiceSecret?: string;
}

export interface RetryConfig {
  retryAttempts: number;
  retryDelayMs: number;
}

export interface TimeoutConfig {
  requestTimeout: number;
}

export interface ResponseSizeConfig {
  maxResponseSize: number;
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

let onGCP: boolean | null = null;
let gcpDetectionPromise: Promise<void> | null = null;

export function initGCPDetection(): void {
  gcpDetectionPromise = detectGCPEnvironment();
}

async function detectGCPEnvironment(): Promise<void> {
  try {
    const result = await isRunningOnGCP();
    onGCP = result;
    if (result) {
      logger.info('Running on GCP - will use IAM authentication for server calls');
    } else {
      logger.info('Not running on GCP - using API key authentication only');
    }
  } catch {
    onGCP = false;
    logger.info('GCP detection failed - using API key authentication only');
  }
}

async function ensureGCPDetectionComplete(): Promise<void> {
  if (gcpDetectionPromise) {
    await gcpDetectionPromise;
    gcpDetectionPromise = null;
  }
}

export function resetGCPState(): void {
  onGCP = null;
  gcpDetectionPromise = null;
}

export function createAuthMiddleware(config: AuthMiddlewareConfig): Middleware {
  return {
    async onRequest({ request }) {
      if (config.apiKey) {
        request.headers.set('X-API-Key', config.apiKey);
      }

      if (config.internalServiceSecret) {
        request.headers.set('X-Internal-Auth', config.internalServiceSecret);
      }

      await ensureGCPDetectionComplete();
      if (onGCP) {
        const identityToken = await getIdentityToken(config.baseUrl);
        if (identityToken) {
          request.headers.set('Authorization', `Bearer ${identityToken}`);
        } else {
          logger.warn('Failed to get IAM identity token', {
            url: request.url,
          });
        }
      }

      return request;
    },
  };
}

export function createTracingMiddleware(): Middleware {
  return {
    async onRequest({ request }) {
      const requestId = nanoid();
      request.headers.set('X-Request-Id', requestId);
      return request;
    },
  };
}

export function createLoggingMiddleware(): Middleware {
  return {
    async onRequest({ request, schemaPath }) {
      logger.debug('API request', {
        method: request.method,
        schemaPath,
        url: request.url,
      });
      return request;
    },
    async onResponse({ request, response, schemaPath }) {
      if (response.ok) {
        logger.debug('API request successful', {
          method: request.method,
          schemaPath,
          statusCode: response.status,
        });
      } else {
        logger.error('API request failed', {
          method: request.method,
          schemaPath,
          statusCode: response.status,
          statusText: response.statusText,
        });
      }
      return response;
    },
  };
}

export function createResponseSizeMiddleware(config: ResponseSizeConfig): Middleware {
  return {
    async onResponse({ request, response }) {
      const contentLength = response.headers.get('content-length');
      if (contentLength) {
        const size = parseInt(contentLength, 10);
        if (!isNaN(size) && size > config.maxResponseSize) {
          throw new ApiError(
            `Response size ${size} bytes exceeds maximum allowed size of ${config.maxResponseSize} bytes`,
            request.url,
            response.status,
          );
        }
        if (!isNaN(size) && size > config.maxResponseSize * 0.8) {
          logger.warn('Response size approaching limit', {
            contentLength: size,
            maxResponseSize: config.maxResponseSize,
            url: request.url,
          });
        }
      }
      return response;
    },
  };
}

export function validateHttps(serverUrl: string, environment: 'development' | 'production'): void {
  const url = new URL(serverUrl);
  if (url.protocol !== 'https:') {
    const isLocalhost = url.hostname === 'localhost' || url.hostname === '127.0.0.1' || url.hostname === '::1';
    if (environment === 'production' && !isLocalhost) {
      throw new Error(
        `HTTPS is required for production API connections. Current URL: ${serverUrl}`
      );
    }
    if (!isLocalhost && environment === 'development') {
      logger.warn('Non-HTTPS API connection detected in development', {
        serverUrl,
        protocol: url.protocol,
        environment,
      });
    }
  }
}

function shouldRetry(statusCode: number): boolean {
  return statusCode >= 500 || statusCode === 429 || statusCode === 408;
}

function getRetryDelay(response: Response, attempt: number, baseDelayMs: number): number {
  const retryAfter = response.headers.get('retry-after');
  if (retryAfter) {
    const seconds = parseInt(retryAfter, 10);
    if (!isNaN(seconds)) {
      return Math.min(seconds * 1000, 60000);
    }
    const retryDate = new Date(retryAfter);
    if (!isNaN(retryDate.getTime())) {
      return Math.min(Math.max(0, retryDate.getTime() - Date.now()), 60000);
    }
  }
  return Math.min(baseDelayMs * Math.pow(2, attempt - 1), 60000);
}

function delay(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

export function createRetryFetch(config: RetryConfig & TimeoutConfig): (input: Request) => Promise<Response> {
  return async (input: Request): Promise<Response> => {
    const request = input;

    for (let attempt = 1; attempt <= config.retryAttempts; attempt++) {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), config.requestTimeout);

      try {
        const clonedRequest = request.clone();
        const response = await globalThis.fetch(
          new Request(clonedRequest, { signal: controller.signal })
        );
        clearTimeout(timeout);

        if (!response.ok && attempt < config.retryAttempts && shouldRetry(response.status)) {
          const delayMs = getRetryDelay(response, attempt, config.retryDelayMs);
          logger.info('Retrying API request', {
            url: request.url,
            attempt: attempt + 1,
            maxAttempts: config.retryAttempts,
            delayMs,
            statusCode: response.status,
          });
          await delay(delayMs);
          continue;
        }

        return response;
      } catch (error) {
        clearTimeout(timeout);

        if (error instanceof Error && error.name === 'AbortError') {
          if (attempt < config.retryAttempts) {
            logger.info('Retrying after timeout', {
              url: request.url,
              attempt: attempt + 1,
              maxAttempts: config.retryAttempts,
              timeout: config.requestTimeout,
            });
            await delay(config.retryDelayMs * attempt);
            continue;
          }
          throw new ApiError(
            `API request timeout after ${config.requestTimeout}ms`,
            request.url,
            0,
          );
        }

        if (attempt < config.retryAttempts) {
          logger.info('Retrying after exception', {
            url: request.url,
            attempt: attempt + 1,
            maxAttempts: config.retryAttempts,
            error: error instanceof Error ? error.message : String(error),
          });
          await delay(config.retryDelayMs * attempt);
          continue;
        }

        throw new ApiError(
          `API request failed: ${error instanceof Error ? error.message : String(error)}`,
          request.url,
          0,
        );
      }
    }

    throw new ApiError('Max retry attempts exhausted', request.url, 0);
  };
}

export function buildProfileHeaders(context?: UserContext): Record<string, string> {
  const headers: Record<string, string> = {};
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
