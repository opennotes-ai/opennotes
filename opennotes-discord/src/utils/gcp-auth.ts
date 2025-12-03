import { logger } from '../logger.js';

const GCP_METADATA_URL = 'http://metadata.google.internal/computeMetadata/v1';
const IDENTITY_TOKEN_PATH = '/instance/service-accounts/default/identity';

let cachedToken: { token: string; expiry: number } | null = null;
const TOKEN_REFRESH_BUFFER_MS = 60 * 1000;

export async function isRunningOnGCP(): Promise<boolean> {
  // Cloud Run sets K_SERVICE environment variable
  if (process.env.K_SERVICE) {
    logger.debug('Detected Cloud Run environment via K_SERVICE env var', {
      service: process.env.K_SERVICE,
    });
    return true;
  }

  // Fallback: try metadata server with longer timeout
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 2000);

    const response = await fetch(`${GCP_METADATA_URL}/`, {
      method: 'GET',
      headers: { 'Metadata-Flavor': 'Google' },
      signal: controller.signal,
    });

    clearTimeout(timeout);
    logger.debug('Detected GCP environment via metadata server', {
      status: response.status,
    });
    return true;
  } catch (error) {
    logger.debug('GCP metadata server not available', {
      error: error instanceof Error ? error.message : String(error),
    });
    return false;
  }
}

export async function getIdentityToken(audience: string): Promise<string | null> {
  if (cachedToken && Date.now() < cachedToken.expiry - TOKEN_REFRESH_BUFFER_MS) {
    return cachedToken.token;
  }

  try {
    const url = `${GCP_METADATA_URL}${IDENTITY_TOKEN_PATH}?audience=${encodeURIComponent(audience)}`;

    const response = await fetch(url, {
      method: 'GET',
      headers: { 'Metadata-Flavor': 'Google' },
    });

    if (!response.ok) {
      logger.warn('Failed to fetch identity token from metadata server', {
        status: response.status,
        statusText: response.statusText,
      });
      return null;
    }

    const token = await response.text();

    const parts = token.split('.');
    if (parts.length === 3) {
      try {
        const payload = JSON.parse(Buffer.from(parts[1], 'base64').toString()) as { exp?: number };
        if (payload.exp) {
          cachedToken = {
            token,
            expiry: payload.exp * 1000,
          };
        }
      } catch {
        cachedToken = {
          token,
          expiry: Date.now() + 55 * 60 * 1000,
        };
      }
    }

    logger.debug('Fetched new GCP identity token', {
      audience,
      expiresIn: cachedToken ? Math.round((cachedToken.expiry - Date.now()) / 1000) : 'unknown',
    });

    return token;
  } catch (error) {
    logger.warn('Failed to fetch GCP identity token', {
      error: error instanceof Error ? error.message : String(error),
      audience,
    });
    return null;
  }
}

export function clearTokenCache(): void {
  cachedToken = null;
}
