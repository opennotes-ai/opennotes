import type { NoteWithRatings } from './types.js';

export function filterNotesAwaitingUserRating(
  notes: NoteWithRatings[],
  userId: string
): NoteWithRatings[] {
  return notes.filter(
    (note) => !note.ratings.some((r) => String(r.rater_participant_id) === String(userId))
  );
}
