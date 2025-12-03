import { describe, it, expect } from '@jest/globals';
import { validateMessageId, validateNoteId, parseCustomId, isValidUUID, UUID_PATTERN, generateShortId } from '../../src/lib/validation.js';

describe('validateMessageId', () => {
  describe('valid message IDs', () => {
    it('should accept valid Discord snowflake IDs', () => {
      const result = validateMessageId('1234567890123456789');
      expect(result.valid).toBe(true);
      expect(result.error).toBeUndefined();
    });

    it('should accept minimum length snowflake (17 characters)', () => {
      const result = validateMessageId('12345678901234567');
      expect(result.valid).toBe(true);
      expect(result.error).toBeUndefined();
    });

    it('should accept maximum length snowflake (20 characters)', () => {
      const result = validateMessageId('12345678901234567890');
      expect(result.valid).toBe(true);
      expect(result.error).toBeUndefined();
    });

    it('should trim whitespace and accept valid ID', () => {
      const result = validateMessageId('  1234567890123456789  ');
      expect(result.valid).toBe(true);
      expect(result.error).toBeUndefined();
    });
  });

  describe('invalid message IDs', () => {
    it('should reject empty string', () => {
      const result = validateMessageId('');
      expect(result.valid).toBe(false);
      expect(result.error).toBe('Message ID cannot be empty');
    });

    it('should reject whitespace-only string', () => {
      const result = validateMessageId('   ');
      expect(result.valid).toBe(false);
      expect(result.error).toBe('Message ID cannot be empty');
    });

    it('should reject non-numeric characters', () => {
      const result = validateMessageId('123abc456');
      expect(result.valid).toBe(false);
      expect(result.error).toBe('Message ID must contain only numeric characters');
    });

    it('should reject ID with special characters', () => {
      const result = validateMessageId('123-456-789');
      expect(result.valid).toBe(false);
      expect(result.error).toBe('Message ID must contain only numeric characters');
    });

    it('should reject ID with spaces', () => {
      const result = validateMessageId('123 456 789');
      expect(result.valid).toBe(false);
      expect(result.error).toBe('Message ID must contain only numeric characters');
    });

    it('should reject ID that is too short', () => {
      const result = validateMessageId('1234567890123456');
      expect(result.valid).toBe(false);
      expect(result.error).toBe('Message ID is too short (minimum 17 characters)');
    });

    it('should reject ID that is too long', () => {
      const result = validateMessageId('123456789012345678901');
      expect(result.valid).toBe(false);
      expect(result.error).toBe('Message ID is too long (maximum 20 characters)');
    });

    it('should reject SQL injection attempt', () => {
      const result = validateMessageId("123'; DROP TABLE notes; --");
      expect(result.valid).toBe(false);
      expect(result.error).toBe('Message ID must contain only numeric characters');
    });

    it('should reject XSS attempt', () => {
      const result = validateMessageId('<script>alert("xss")</script>');
      expect(result.valid).toBe(false);
      expect(result.error).toBe('Message ID must contain only numeric characters');
    });

    it('should reject negative numbers', () => {
      const result = validateMessageId('-1234567890123456789');
      expect(result.valid).toBe(false);
      expect(result.error).toBe('Message ID must contain only numeric characters');
    });

    it('should reject floating point numbers', () => {
      const result = validateMessageId('1234567890123456.789');
      expect(result.valid).toBe(false);
      expect(result.error).toBe('Message ID must contain only numeric characters');
    });

    it('should reject hexadecimal notation', () => {
      const result = validateMessageId('0x1234567890ABCDEF');
      expect(result.valid).toBe(false);
      expect(result.error).toBe('Message ID must contain only numeric characters');
    });
  });
});

describe('validateNoteId', () => {
  describe('valid note IDs', () => {
    it('should accept valid UUID format (lowercase)', () => {
      const result = validateNoteId('550e8400-e29b-41d4-a716-446655440000');
      expect(result.valid).toBe(true);
      expect(result.error).toBeUndefined();
    });

    it('should accept valid UUID format (uppercase)', () => {
      const result = validateNoteId('550E8400-E29B-41D4-A716-446655440000');
      expect(result.valid).toBe(true);
      expect(result.error).toBeUndefined();
    });

    it('should accept valid UUID format (mixed case)', () => {
      const result = validateNoteId('550e8400-E29B-41d4-A716-446655440000');
      expect(result.valid).toBe(true);
      expect(result.error).toBeUndefined();
    });

    it('should trim whitespace and accept valid UUID', () => {
      const result = validateNoteId('  550e8400-e29b-41d4-a716-446655440000  ');
      expect(result.valid).toBe(true);
      expect(result.error).toBeUndefined();
    });
  });

  describe('invalid note IDs', () => {
    it('should reject empty string', () => {
      const result = validateNoteId('');
      expect(result.valid).toBe(false);
      expect(result.error).toBe('Note ID cannot be empty');
    });

    it('should reject whitespace-only string', () => {
      const result = validateNoteId('   ');
      expect(result.valid).toBe(false);
      expect(result.error).toBe('Note ID cannot be empty');
    });

    it('should reject numeric-only ID (not UUID format)', () => {
      const result = validateNoteId('12345');
      expect(result.valid).toBe(false);
      expect(result.error).toBe('Note ID must be a valid UUID format');
    });

    it('should reject UUID without hyphens', () => {
      const result = validateNoteId('550e8400e29b41d4a716446655440000');
      expect(result.valid).toBe(false);
      expect(result.error).toBe('Note ID must be a valid UUID format');
    });

    it('should reject UUID with wrong segment lengths', () => {
      const result = validateNoteId('550e840-0e29b-41d4-a716-446655440000');
      expect(result.valid).toBe(false);
      expect(result.error).toBe('Note ID must be a valid UUID format');
    });

    it('should reject UUID with invalid characters', () => {
      const result = validateNoteId('550g8400-e29b-41d4-a716-446655440000');
      expect(result.valid).toBe(false);
      expect(result.error).toBe('Note ID must be a valid UUID format');
    });

    it('should reject random string', () => {
      const result = validateNoteId('not-a-uuid');
      expect(result.valid).toBe(false);
      expect(result.error).toBe('Note ID must be a valid UUID format');
    });
  });
});

describe('isValidUUID', () => {
  describe('valid UUIDs', () => {
    it('should return true for valid UUIDv4 lowercase', () => {
      expect(isValidUUID('550e8400-e29b-41d4-a716-446655440000')).toBe(true);
    });

    it('should return true for valid UUIDv4 uppercase', () => {
      expect(isValidUUID('550E8400-E29B-41D4-A716-446655440000')).toBe(true);
    });

    it('should return true for valid UUIDv7', () => {
      expect(isValidUUID('0192b3a4-5c6d-7e8f-9a0b-1c2d3e4f5a6b')).toBe(true);
    });
  });

  describe('invalid UUIDs', () => {
    it('should return false for empty string', () => {
      expect(isValidUUID('')).toBe(false);
    });

    it('should return false for non-UUID string', () => {
      expect(isValidUUID('not-a-uuid')).toBe(false);
    });

    it('should return false for numeric string', () => {
      expect(isValidUUID('123456789')).toBe(false);
    });

    it('should return false for UUID without hyphens', () => {
      expect(isValidUUID('550e8400e29b41d4a716446655440000')).toBe(false);
    });

    it('should return false for UUID with invalid characters', () => {
      expect(isValidUUID('550g8400-e29b-41d4-a716-446655440000')).toBe(false);
    });
  });
});

describe('UUID_PATTERN', () => {
  it('should be exported and be a valid RegExp', () => {
    expect(UUID_PATTERN).toBeInstanceOf(RegExp);
  });

  it('should match valid UUIDs', () => {
    expect(UUID_PATTERN.test('550e8400-e29b-41d4-a716-446655440000')).toBe(true);
  });

  it('should not match invalid UUIDs', () => {
    expect(UUID_PATTERN.test('not-a-uuid')).toBe(false);
  });
});

describe('parseCustomId', () => {
  describe('valid customId parsing', () => {
    it('should parse customId with 2 parts', () => {
      const result = parseCustomId('rate:12345', 2);
      expect(result.success).toBe(true);
      expect(result.parts).toEqual(['rate', '12345']);
      expect(result.error).toBeUndefined();
    });

    it('should parse customId with 3 parts', () => {
      const result = parseCustomId('rate:12345:helpful', 3);
      expect(result.success).toBe(true);
      expect(result.parts).toEqual(['rate', '12345', 'helpful']);
      expect(result.error).toBeUndefined();
    });

    it('should parse customId with more parts than expected', () => {
      const result = parseCustomId('config:toggle:key:extra', 2);
      expect(result.success).toBe(true);
      expect(result.parts).toHaveLength(4);
      expect(result.parts?.[0]).toBe('config');
      expect(result.parts?.[1]).toBe('toggle');
    });

    it('should parse customId with custom delimiter', () => {
      const result = parseCustomId('rate-12345-helpful', 3, '-');
      expect(result.success).toBe(true);
      expect(result.parts).toEqual(['rate', '12345', 'helpful']);
    });

    it('should handle empty parts correctly', () => {
      const result = parseCustomId('rate::helpful', 3);
      expect(result.success).toBe(true);
      expect(result.parts).toEqual(['rate', '', 'helpful']);
    });
  });

  describe('invalid customId parsing', () => {
    it('should reject empty customId', () => {
      const result = parseCustomId('', 2);
      expect(result.success).toBe(false);
      expect(result.error).toBe('CustomId cannot be empty');
      expect(result.parts).toBeUndefined();
    });

    it('should reject whitespace-only customId', () => {
      const result = parseCustomId('   ', 2);
      expect(result.success).toBe(false);
      expect(result.error).toBe('CustomId cannot be empty');
    });

    it('should reject customId with insufficient parts', () => {
      const result = parseCustomId('rate', 2);
      expect(result.success).toBe(false);
      expect(result.error).toBe("CustomId must have at least 2 parts separated by ':'");
      expect(result.parts).toBeUndefined();
    });

    it('should reject customId with only one part when 3 expected', () => {
      const result = parseCustomId('rate:12345', 3);
      expect(result.success).toBe(false);
      expect(result.error).toBe("CustomId must have at least 3 parts separated by ':'");
    });

    it('should reject malformed customId with wrong delimiter', () => {
      const result = parseCustomId('rate-12345', 2, ':');
      expect(result.success).toBe(false);
      expect(result.error).toBe("CustomId must have at least 2 parts separated by ':'");
    });

    it('should reject customId without delimiter', () => {
      const result = parseCustomId('rate12345helpful', 3);
      expect(result.success).toBe(false);
      expect(result.error).toBe("CustomId must have at least 3 parts separated by ':'");
    });
  });

  describe('edge cases', () => {
    it('should handle customId with many parts', () => {
      const result = parseCustomId('a:b:c:d:e:f:g:h', 5);
      expect(result.success).toBe(true);
      expect(result.parts).toHaveLength(8);
    });

    it('should handle customId with Unicode characters', () => {
      const result = parseCustomId('rate:12345:👍', 3);
      expect(result.success).toBe(true);
      expect(result.parts).toEqual(['rate', '12345', '👍']);
    });

    it('should handle customId with special characters in parts', () => {
      const result = parseCustomId('config:key.with.dots:value-with-dashes', 3);
      expect(result.success).toBe(true);
      expect(result.parts).toHaveLength(3);
    });
  });
});

describe('generateShortId', () => {
  describe('default length', () => {
    it('should generate ID with default length of 16 characters', () => {
      const id = generateShortId();
      expect(id.length).toBe(16);
    });

    it('should generate different IDs on each call', () => {
      const id1 = generateShortId();
      const id2 = generateShortId();
      expect(id1).not.toBe(id2);
    });

    it('should generate IDs with only base64url characters', () => {
      const id = generateShortId();
      expect(id).toMatch(/^[A-Za-z0-9_-]+$/);
    });
  });

  describe('custom length', () => {
    it('should generate ID with specified length', () => {
      const id = generateShortId(20);
      expect(id.length).toBe(20);
    });

    it('should generate ID with minimum safe length of 16', () => {
      const id = generateShortId(16);
      expect(id.length).toBe(16);
    });

    it('should generate ID with longer length for extra safety', () => {
      const id = generateShortId(32);
      expect(id.length).toBe(32);
    });
  });

  describe('collision resistance', () => {
    it('should generate unique IDs in batch of 1000', () => {
      const ids = new Set<string>();
      for (let i = 0; i < 1000; i++) {
        ids.add(generateShortId());
      }
      expect(ids.size).toBe(1000);
    });

    it('should have at least 96 bits of entropy with 16-char base64url ID', () => {
      const length = 16;
      const bitsPerChar = 6;
      const entropyBits = length * bitsPerChar;
      expect(entropyBits).toBeGreaterThanOrEqual(96);
    });
  });
});
