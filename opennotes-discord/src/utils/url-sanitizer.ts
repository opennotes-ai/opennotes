/**
 * Sanitizes connection URLs by redacting credentials.
 *
 * Supports various URL formats:
 * - redis://user:password@host:port -> redis://user:****@host:port
 * - nats://user:password@host:port -> nats://user:****@host:port
 * - https://user:password@host -> https://user:****@host
 *
 * @param url - The connection URL to sanitize
 * @returns The sanitized URL with password redacted
 */
export function sanitizeConnectionUrl(url: string): string {
  try {
    const urlObj = new URL(url);

    if (urlObj.password) {
      urlObj.password = '****';
    }

    return urlObj.toString();
  } catch {
    return url.replace(/:\/\/([^:]+):([^@]+)@/, '://$1:****@');
  }
}
