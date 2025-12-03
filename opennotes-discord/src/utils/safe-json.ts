import { logger } from '../logger.js';

const DANGEROUS_KEYS = ['__proto__', 'constructor', 'prototype'];

export class SafeJSONError extends Error {
  constructor(message: string, public readonly cause?: unknown) {
    super(message);
    this.name = 'SafeJSONError';
  }
}

function isDangerousKey(key: string): boolean {
  return DANGEROUS_KEYS.includes(key);
}

function reviverFunction(_key: string, value: unknown): unknown {
  if (_key && isDangerousKey(_key)) {
    logger.warn('Blocked dangerous key during JSON parsing', { key: _key });
    return undefined;
  }
  return value;
}

function sanitizeObject(obj: unknown): unknown {
  if (obj === null || typeof obj !== 'object') {
    return obj;
  }

  if (Array.isArray(obj)) {
    return obj.map(item => sanitizeObject(item));
  }

  const sanitized: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(obj)) {
    if (!isDangerousKey(key)) {
      sanitized[key] = sanitizeObject(value);
    } else {
      logger.warn('Removed dangerous key during object sanitization', { key });
    }
  }

  return sanitized;
}

export function safeJSONParse<T = unknown>(
  text: string,
  options: {
    validate?: (data: unknown) => boolean;
    sanitize?: boolean;
  } = {}
): T {
  const { validate, sanitize = true } = options;

  try {
    let parsed: T = JSON.parse(text, reviverFunction) as T;

    if (sanitize) {
      parsed = sanitizeObject(parsed) as T;
    }

    if (validate && !validate(parsed)) {
      throw new SafeJSONError('JSON validation failed');
    }

    return parsed;
  } catch (error) {
    if (error instanceof SafeJSONError) {
      throw error;
    }

    const message = error instanceof Error ? error.message : String(error);
    throw new SafeJSONError(`Failed to parse JSON: ${message}`, error);
  }
}

export function safeJSONStringify(value: unknown): string {
  try {
    return JSON.stringify(value);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    throw new SafeJSONError(`Failed to stringify JSON: ${message}`, error);
  }
}

export function isValidJSON(text: string): boolean {
  try {
    JSON.parse(text);
    return true;
  } catch {
    return false;
  }
}
