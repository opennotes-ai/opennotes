import { logger } from '../logger.js';
import { randomBytes } from 'crypto';

export interface ValidationResult {
  valid: boolean;
  error?: string;
}

const DISCORD_SNOWFLAKE_MIN_LENGTH = 17;
const DISCORD_SNOWFLAKE_MAX_LENGTH = 20;
const NUMERIC_PATTERN = /^\d+$/;
export const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isValidUUID(id: string): boolean {
  return UUID_PATTERN.test(id);
}

export function validateMessageId(messageId: string): ValidationResult {
  if (!messageId || messageId.trim().length === 0) {
    return {
      valid: false,
      error: 'Message ID cannot be empty',
    };
  }

  const trimmedId = messageId.trim();

  if (!NUMERIC_PATTERN.test(trimmedId)) {
    return {
      valid: false,
      error: 'Message ID must contain only numeric characters',
    };
  }

  if (trimmedId.length < DISCORD_SNOWFLAKE_MIN_LENGTH) {
    return {
      valid: false,
      error: `Message ID is too short (minimum ${DISCORD_SNOWFLAKE_MIN_LENGTH} characters)`,
    };
  }

  if (trimmedId.length > DISCORD_SNOWFLAKE_MAX_LENGTH) {
    return {
      valid: false,
      error: `Message ID is too long (maximum ${DISCORD_SNOWFLAKE_MAX_LENGTH} characters)`,
    };
  }

  return { valid: true };
}

export function validateNoteId(noteId: string): ValidationResult {
  if (!noteId || noteId.trim().length === 0) {
    return {
      valid: false,
      error: 'Note ID cannot be empty',
    };
  }

  const trimmedId = noteId.trim();

  if (!UUID_PATTERN.test(trimmedId)) {
    return {
      valid: false,
      error: 'Note ID must be a valid UUID format',
    };
  }

  return { valid: true };
}

export interface CustomIdParseResult<T = string> {
  success: boolean;
  parts?: T[];
  error?: string;
}

export function parseCustomId(
  customId: string,
  expectedParts: number,
  delimiter: string = ':'
): CustomIdParseResult {
  if (!customId || customId.trim().length === 0) {
    logger.error('CustomId is empty', { customId });
    return {
      success: false,
      error: 'CustomId cannot be empty',
    };
  }

  const parts = customId.split(delimiter);

  if (parts.length < expectedParts) {
    logger.error('Malformed customId: insufficient parts', {
      customId,
      expectedParts,
      actualParts: parts.length,
      parts,
    });
    return {
      success: false,
      error: `CustomId must have at least ${expectedParts} parts separated by '${delimiter}'`,
    };
  }

  return {
    success: true,
    parts,
  };
}

export function generateShortId(length: number = 16): string {
  const bytes = randomBytes(Math.ceil(length * 0.75));
  return bytes.toString('base64url').substring(0, length);
}
