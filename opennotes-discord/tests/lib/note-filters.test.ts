import { filterNotesAwaitingUserRating } from '../../src/lib/note-filters.js';
import type { NoteWithRatings, RatingResponse } from '../../src/lib/types.js';

function createMockRating(overrides?: Partial<RatingResponse>): RatingResponse {
  return {
    id: 'rating-1',
    note_id: 'note-1',
    rater_participant_id: 'rater-1',
    helpfulness_level: 'HELPFUL',
    created_at: '2025-11-01T12:00:00Z',
    updated_at: '2025-11-01T12:00:00Z',
    ...overrides,
  };
}

function createMockNote(overrides?: Partial<NoteWithRatings>): NoteWithRatings {
  return {
    id: 'note-1',
    author_participant_id: 'author-1',
    summary: 'Test note summary',
    classification: 'MISINFORMED_OR_POTENTIALLY_MISLEADING',
    helpfulness_score: 0.5,
    status: 'NEEDS_MORE_RATINGS',
    created_at: '2025-11-01T12:00:00Z',
    ratings: [],
    ratings_count: 0,
    ...overrides,
  };
}

describe('note-filters', () => {
  describe('filterNotesAwaitingUserRating', () => {
    const currentUserId = 'user-123';

    describe('Section 1 - Notes Awaiting Your Rating filter', () => {
      it('should return all notes when none have ratings', () => {
        const notes = [
          createMockNote({ id: 'note-1', ratings: [], ratings_count: 0 }),
          createMockNote({ id: 'note-2', ratings: [], ratings_count: 0 }),
          createMockNote({ id: 'note-3', ratings: [], ratings_count: 0 }),
        ];

        const result = filterNotesAwaitingUserRating(notes, currentUserId);

        expect(result).toHaveLength(3);
        expect(result.map(n => n.id)).toEqual(['note-1', 'note-2', 'note-3']);
      });

      it('should return notes where only other users have rated', () => {
        const notes = [
          createMockNote({
            id: 'note-1',
            ratings: [
              createMockRating({ rater_participant_id: 'other-user-1' }),
              createMockRating({ rater_participant_id: 'other-user-2' }),
            ],
            ratings_count: 2,
          }),
          createMockNote({
            id: 'note-2',
            ratings: [
              createMockRating({ rater_participant_id: 'other-user-3' }),
            ],
            ratings_count: 1,
          }),
        ];

        const result = filterNotesAwaitingUserRating(notes, currentUserId);

        expect(result).toHaveLength(2);
        expect(result.map(n => n.id)).toEqual(['note-1', 'note-2']);
      });

      it('should filter out notes where the current user has already rated', () => {
        const notes = [
          createMockNote({
            id: 'note-1',
            ratings: [
              createMockRating({ rater_participant_id: currentUserId }),
            ],
            ratings_count: 1,
          }),
        ];

        const result = filterNotesAwaitingUserRating(notes, currentUserId);

        expect(result).toHaveLength(0);
      });

      it('should handle mixed scenario - some notes rated by user, some not', () => {
        const notes = [
          createMockNote({
            id: 'note-1',
            ratings: [
              createMockRating({ rater_participant_id: 'other-user' }),
            ],
            ratings_count: 1,
          }),
          createMockNote({
            id: 'note-2',
            ratings: [
              createMockRating({ rater_participant_id: currentUserId }),
            ],
            ratings_count: 1,
          }),
          createMockNote({
            id: 'note-3',
            ratings: [],
            ratings_count: 0,
          }),
          createMockNote({
            id: 'note-4',
            ratings: [
              createMockRating({ rater_participant_id: 'other-user' }),
              createMockRating({ rater_participant_id: currentUserId }),
            ],
            ratings_count: 2,
          }),
        ];

        const result = filterNotesAwaitingUserRating(notes, currentUserId);

        expect(result).toHaveLength(2);
        expect(result.map(n => n.id)).toEqual(['note-1', 'note-3']);
      });

      it('should return empty array when all notes are rated by user', () => {
        const notes = [
          createMockNote({
            id: 'note-1',
            ratings: [createMockRating({ rater_participant_id: currentUserId })],
            ratings_count: 1,
          }),
          createMockNote({
            id: 'note-2',
            ratings: [createMockRating({ rater_participant_id: currentUserId })],
            ratings_count: 1,
          }),
        ];

        const result = filterNotesAwaitingUserRating(notes, currentUserId);

        expect(result).toHaveLength(0);
      });

      it('should return empty array when given empty notes array', () => {
        const result = filterNotesAwaitingUserRating([], currentUserId);

        expect(result).toHaveLength(0);
        expect(result).toEqual([]);
      });

      it('should handle numeric participant IDs converted to string', () => {
        const numericUserId = '12345';
        const notes = [
          createMockNote({
            id: 'note-1',
            ratings: [
              createMockRating({ rater_participant_id: '12345' }),
            ],
            ratings_count: 1,
          }),
        ];

        const result = filterNotesAwaitingUserRating(notes, numericUserId);

        expect(result).toHaveLength(0);
      });

      it('should handle string vs numeric comparison correctly (String() conversion)', () => {
        const notes = [
          createMockNote({
            id: 'note-1',
            ratings: [
              { ...createMockRating(), rater_participant_id: 12345 as unknown as string },
            ],
            ratings_count: 1,
          }),
        ];

        const result = filterNotesAwaitingUserRating(notes, '12345');

        expect(result).toHaveLength(0);
      });

      it('should correctly filter when user has rated with HELPFUL rating', () => {
        const notes = [
          createMockNote({
            id: 'note-1',
            ratings: [
              createMockRating({
                rater_participant_id: currentUserId,
                helpfulness_level: 'HELPFUL',
              }),
            ],
            ratings_count: 1,
          }),
        ];

        const result = filterNotesAwaitingUserRating(notes, currentUserId);

        expect(result).toHaveLength(0);
      });

      it('should correctly filter when user has rated with NOT_HELPFUL rating', () => {
        const notes = [
          createMockNote({
            id: 'note-1',
            ratings: [
              createMockRating({
                rater_participant_id: currentUserId,
                helpfulness_level: 'NOT_HELPFUL',
              }),
            ],
            ratings_count: 1,
          }),
        ];

        const result = filterNotesAwaitingUserRating(notes, currentUserId);

        expect(result).toHaveLength(0);
      });

      it('should correctly filter when user has rated with SOMEWHAT_HELPFUL rating', () => {
        const notes = [
          createMockNote({
            id: 'note-1',
            ratings: [
              createMockRating({
                rater_participant_id: currentUserId,
                helpfulness_level: 'SOMEWHAT_HELPFUL',
              }),
            ],
            ratings_count: 1,
          }),
        ];

        const result = filterNotesAwaitingUserRating(notes, currentUserId);

        expect(result).toHaveLength(0);
      });

      it('should handle notes with many ratings from various users', () => {
        const notes = [
          createMockNote({
            id: 'note-1',
            ratings: [
              createMockRating({ rater_participant_id: 'user-a' }),
              createMockRating({ rater_participant_id: 'user-b' }),
              createMockRating({ rater_participant_id: 'user-c' }),
              createMockRating({ rater_participant_id: 'user-d' }),
              createMockRating({ rater_participant_id: 'user-e' }),
            ],
            ratings_count: 5,
          }),
        ];

        const result = filterNotesAwaitingUserRating(notes, currentUserId);

        expect(result).toHaveLength(1);
        expect(result[0].id).toBe('note-1');
      });

      it('should filter out note when user is among many raters', () => {
        const notes = [
          createMockNote({
            id: 'note-1',
            ratings: [
              createMockRating({ rater_participant_id: 'user-a' }),
              createMockRating({ rater_participant_id: 'user-b' }),
              createMockRating({ rater_participant_id: currentUserId }),
              createMockRating({ rater_participant_id: 'user-d' }),
              createMockRating({ rater_participant_id: 'user-e' }),
            ],
            ratings_count: 5,
          }),
        ];

        const result = filterNotesAwaitingUserRating(notes, currentUserId);

        expect(result).toHaveLength(0);
      });

      it('should preserve order of notes after filtering', () => {
        const notes = [
          createMockNote({ id: 'note-a', ratings: [] }),
          createMockNote({
            id: 'note-b',
            ratings: [createMockRating({ rater_participant_id: currentUserId })],
          }),
          createMockNote({ id: 'note-c', ratings: [] }),
          createMockNote({
            id: 'note-d',
            ratings: [createMockRating({ rater_participant_id: currentUserId })],
          }),
          createMockNote({ id: 'note-e', ratings: [] }),
        ];

        const result = filterNotesAwaitingUserRating(notes, currentUserId);

        expect(result).toHaveLength(3);
        expect(result.map(n => n.id)).toEqual(['note-a', 'note-c', 'note-e']);
      });

      it('should not modify the original notes array', () => {
        const originalNotes = [
          createMockNote({
            id: 'note-1',
            ratings: [createMockRating({ rater_participant_id: currentUserId })],
          }),
          createMockNote({ id: 'note-2', ratings: [] }),
        ];
        const notesCopy = [...originalNotes];

        filterNotesAwaitingUserRating(originalNotes, currentUserId);

        expect(originalNotes).toEqual(notesCopy);
        expect(originalNotes).toHaveLength(2);
      });
    });
  });
});
