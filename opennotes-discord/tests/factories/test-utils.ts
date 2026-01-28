/**
 * Generate deterministic UUIDs for testing based on a prefix and sequence number.
 * These are valid UUID v4 format strings that can be used in tests.
 * Note: UUID format requires hex digits (0-9, a-f only)
 */
export function testUuid(prefix: string, sequence: number): string {
  // Convert prefix to hex-safe value (a=author, b=rater, c=note, d=community, e=user)
  const prefixMap: Record<string, string> = {
    'a001': 'aaaa',  // author
    'r001': 'bbbb',  // rater
    'n001': 'cccc',  // note
    'c001': 'dddd',  // community
    'u001': 'eeee',  // user
  };
  const prefixPart = prefixMap[prefix] || prefix.padStart(4, '0').slice(0, 4).replace(/[^0-9a-f]/gi, 'a');
  const seqPart = sequence.toString().padStart(12, '0').slice(0, 12);
  return `00000000-0000-0001-${prefixPart}-${seqPart}`;
}

/**
 * Generate a random UUID for tests where the value doesn't matter.
 */
export function randomTestUuid(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = Math.floor(Math.random() * 16);
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

// Pre-defined UUIDs for common test entities
export const TEST_UUIDS = {
  AUTHOR_1: testUuid('a001', 1),
  AUTHOR_2: testUuid('a001', 2),
  RATER_1: testUuid('r001', 1),
  RATER_2: testUuid('r001', 2),
  NOTE_1: testUuid('n001', 1),
  NOTE_2: testUuid('n001', 2),
  COMMUNITY_1: testUuid('c001', 1),
  USER_1: testUuid('u001', 1),
  USER_2: testUuid('u001', 2),
};
