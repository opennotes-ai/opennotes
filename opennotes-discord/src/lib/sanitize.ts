import { createHash } from 'node:crypto';

const SENSITIVE_KEYS = new Set([
  'password',
  'token',
  'secret',
  'api_key',
  'apikey',
  'authorization',
  'credential',
  'access_token',
  'refresh_token',
]);

function isSensitiveKey(key: string): boolean {
  return SENSITIVE_KEYS.has(key.toLowerCase());
}

export function sanitizeValue(key: string, value: string): string {
  if (!isSensitiveKey(key)) {
    return value;
  }

  if (value.length <= 4) {
    return '****';
  }

  const lowerKey = key.toLowerCase();
  if (lowerKey === 'password' || lowerKey === 'credential') {
    const hash = createHash('sha256').update(value).digest('hex').slice(0, 8);
    return `[sha256:${hash}]`;
  }

  return `${value.slice(0, 2)}****${value.slice(-2)}`;
}

export function sanitizeObject(obj: unknown): unknown {
  if (obj === null || obj === undefined) {
    return obj;
  }

  if (typeof obj === 'string') {
    return obj;
  }

  if (Array.isArray(obj)) {
    return obj.map(item => sanitizeObject(item));
  }

  if (typeof obj === 'object') {
    const result: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(obj as Record<string, unknown>)) {
      if (typeof value === 'string') {
        result[key] = sanitizeValue(key, value);
      } else {
        result[key] = sanitizeObject(value);
      }
    }
    return result;
  }

  return obj;
}
