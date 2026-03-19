import { describe, it, expect } from '@jest/globals';
import {
  uuidToProquint,
  proquintToHexSuffix,
  isProquint,
  isUuidLike,
  formatIdDisplay,
  resolveId,
} from '../../src/lib/proquint.js';

describe('uuidToProquint', () => {
  it('should encode the last 8 hex chars of a UUID as two proquint words', () => {
    const uuid = '550e8400-e29b-41d4-a716-446655440000';
    const result = uuidToProquint(uuid);
    expect(result).toMatch(/^[a-z]{5}-[a-z]{5}$/);
  });

  it('should produce a known proquint for a known UUID suffix', () => {
    const uuid = '00000000-0000-4000-8000-000000000000';
    const result = uuidToProquint(uuid);
    const decoded = proquintToHexSuffix(result);
    expect(decoded).toBe('00000000');
  });

  it('should encode different UUIDs with different suffixes to different proquints', () => {
    const uuid1 = '550e8400-e29b-41d4-a716-446655440000';
    const uuid2 = '550e8400-e29b-41d4-a716-446655440001';
    expect(uuidToProquint(uuid1)).not.toBe(uuidToProquint(uuid2));
  });

  it('should handle uppercase UUID input', () => {
    const lower = '550e8400-e29b-41d4-a716-446655440000';
    const upper = '550E8400-E29B-41D4-A716-446655440000';
    expect(uuidToProquint(lower)).toBe(uuidToProquint(upper));
  });
});

describe('proquintToHexSuffix', () => {
  it('should decode a proquint back to 8 hex characters', () => {
    const pq = uuidToProquint('550e8400-e29b-41d4-a716-446655440000');
    const hex = proquintToHexSuffix(pq);
    expect(hex).toHaveLength(8);
    expect(hex).toMatch(/^[0-9a-f]{8}$/);
  });

  it('should decode to the last 8 hex chars of the original UUID', () => {
    const uuid = '550e8400-e29b-41d4-a716-446655440000';
    const pq = uuidToProquint(uuid);
    const hex = proquintToHexSuffix(pq);
    const expectedSuffix = uuid.replace(/-/g, '').slice(-8);
    expect(hex).toBe(expectedSuffix);
  });
});

describe('round-trip encoding', () => {
  const testUuids = [
    '550e8400-e29b-41d4-a716-446655440000',
    '0192b3a4-5c6d-7e8f-9a0b-1c2d3e4f5a6b',
    'ffffffff-ffff-4fff-bfff-ffffffffffff',
    '00000000-0000-4000-8000-000000000000',
    'a1b2c3d4-e5f6-4789-abcd-ef0123456789',
  ];

  it.each(testUuids)('should round-trip UUID %s', (uuid) => {
    const pq = uuidToProquint(uuid);
    const hex = proquintToHexSuffix(pq);
    const expectedSuffix = uuid.replace(/-/g, '').slice(-8);
    expect(hex).toBe(expectedSuffix);
  });
});

describe('isProquint', () => {
  it('should accept valid proquint format', () => {
    expect(isProquint('bafod-jusob')).toBe(true);
  });

  it('should accept proquint generated from a UUID', () => {
    const pq = uuidToProquint('550e8400-e29b-41d4-a716-446655440000');
    expect(isProquint(pq)).toBe(true);
  });

  it('should reject "hello-world" since e, w, y are not in proquint alphabet', () => {
    expect(isProquint('hello-world')).toBe(false);
  });

  it('should reject "helloo-world" (too many chars in first word)', () => {
    expect(isProquint('helloo-world')).toBe(false);
  });

  it('should reject strings without hyphen', () => {
    expect(isProquint('abcdefghij')).toBe(false);
  });

  it('should reject single word', () => {
    expect(isProquint('abc')).toBe(false);
  });

  it('should reject empty string', () => {
    expect(isProquint('')).toBe(false);
  });

  it('should reject uppercase letters', () => {
    expect(isProquint('Bafod-Jusob')).toBe(false);
  });

  it('should reject words with wrong length', () => {
    expect(isProquint('abcd-abcde')).toBe(false);
    expect(isProquint('abcdef-abcde')).toBe(false);
  });

  it('should reject numeric characters', () => {
    expect(isProquint('abc12-defgh')).toBe(false);
  });
});

describe('isUuidLike', () => {
  it('should accept valid UUIDv4 lowercase', () => {
    expect(isUuidLike('550e8400-e29b-41d4-a716-446655440000')).toBe(true);
  });

  it('should accept valid UUIDv4 uppercase', () => {
    expect(isUuidLike('550E8400-E29B-41D4-A716-446655440000')).toBe(true);
  });

  it('should accept valid UUIDv7', () => {
    expect(isUuidLike('0192b3a4-5c6d-7e8f-9a0b-1c2d3e4f5a6b')).toBe(true);
  });

  it('should reject empty string', () => {
    expect(isUuidLike('')).toBe(false);
  });

  it('should reject non-UUID string', () => {
    expect(isUuidLike('not-a-uuid')).toBe(false);
  });

  it('should reject UUID without hyphens', () => {
    expect(isUuidLike('550e8400e29b41d4a716446655440000')).toBe(false);
  });

  it('should reject UUID with invalid hex characters', () => {
    expect(isUuidLike('550g8400-e29b-41d4-a716-446655440000')).toBe(false);
  });

  it('should reject numeric-only string', () => {
    expect(isUuidLike('1234567890')).toBe(false);
  });

  it('should reject discord snowflake IDs', () => {
    expect(isUuidLike('discord-123456789012345')).toBe(false);
  });
});

describe('formatIdDisplay', () => {
  it('should return proquint for UUID input', () => {
    const uuid = '550e8400-e29b-41d4-a716-446655440000';
    const result = formatIdDisplay(uuid);
    expect(isProquint(result)).toBe(true);
    expect(result).toBe(uuidToProquint(uuid));
  });

  it('should passthrough non-UUID strings', () => {
    expect(formatIdDisplay('discord-12345')).toBe('discord-12345');
  });

  it('should passthrough numeric strings', () => {
    expect(formatIdDisplay('1234567890')).toBe('1234567890');
  });

  it('should passthrough empty string', () => {
    expect(formatIdDisplay('')).toBe('');
  });

  it('should passthrough proquint strings', () => {
    expect(formatIdDisplay('bafod-jusob')).toBe('bafod-jusob');
  });
});

describe('resolveId', () => {
  const items = [
    { id: '550e8400-e29b-41d4-a716-446655440000' },
    { id: '0192b3a4-5c6d-7e8f-9a0b-1c2d3e4f5a6b' },
    { id: 'a1b2c3d4-e5f6-4789-abcd-ef0123456789' },
  ];

  it('should find item by exact UUID match', () => {
    const result = resolveId('550e8400-e29b-41d4-a716-446655440000', items);
    expect(result).toBe('550e8400-e29b-41d4-a716-446655440000');
  });

  it('should find item by proquint suffix match', () => {
    const pq = uuidToProquint('550e8400-e29b-41d4-a716-446655440000');
    const result = resolveId(pq, items);
    expect(result).toBe('550e8400-e29b-41d4-a716-446655440000');
  });

  it('should return null for non-matching UUID', () => {
    const result = resolveId('ffffffff-ffff-4fff-bfff-ffffffffffff', items);
    expect(result).toBeNull();
  });

  it('should return null for non-matching proquint', () => {
    const pq = uuidToProquint('ffffffff-ffff-4fff-bfff-ffffffffffff');
    const result = resolveId(pq, items);
    expect(result).toBeNull();
  });

  it('should return null for arbitrary string', () => {
    const result = resolveId('random-text', items);
    expect(result).toBeNull();
  });

  it('should return null for empty items list', () => {
    const pq = uuidToProquint('550e8400-e29b-41d4-a716-446655440000');
    const result = resolveId(pq, []);
    expect(result).toBeNull();
  });

  it('should prefer exact UUID match over proquint suffix match', () => {
    const uuid = '550e8400-e29b-41d4-a716-446655440000';
    const result = resolveId(uuid, items);
    expect(result).toBe(uuid);
  });

  it('should resolve proquint for each item in the list', () => {
    for (const item of items) {
      const pq = uuidToProquint(item.id);
      const result = resolveId(pq, items);
      expect(result).toBe(item.id);
    }
  });
});
