/**
 * Test constants for Discord bot tests
 * These values should match the configuration used in test mocks
 */

/**
 * Valid UUID for testing note operations
 * Used to pass validateNoteId validation in commands
 */
export const TEST_NOTE_UUID = '550e8400-e29b-41d4-a716-446655440000';

/**
 * Additional test UUIDs for scenarios requiring multiple notes
 */
export const TEST_NOTE_UUID_2 = '550e8400-e29b-41d4-a716-446655440001';
export const TEST_NOTE_UUID_3 = '550e8400-e29b-41d4-a716-446655440002';

/**
 * Default score threshold for note publisher tests
 * This should match the value used in NotePublisherConfigService mocks
 */
export const TEST_SCORE_THRESHOLD = 0.7;

/**
 * A score value that exceeds the test threshold
 * Used for testing scenarios where notes meet the publication threshold
 */
export const TEST_SCORE_ABOVE_THRESHOLD = 0.85;

/**
 * A score value that is below the test threshold
 * Used for testing scenarios where notes don't meet the publication threshold
 */
export const TEST_SCORE_BELOW_THRESHOLD = 0.65;
