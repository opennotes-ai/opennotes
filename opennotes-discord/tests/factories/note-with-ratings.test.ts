import { describe, it, expect } from '@jest/globals';
import {
  noteWithRatingsFactory,
  ratingResponseFactory,
  requestInfoFactory,
} from './index.js';

describe('noteWithRatingsFactory', () => {
  it('should create a note with default values', () => {
    const note = noteWithRatingsFactory.build();

    expect(note.id).toBeDefined();
    expect(note.author_id).toBeDefined();
    expect(note.summary).toBeDefined();
    expect(note.classification).toBe('MISINFORMED_OR_POTENTIALLY_MISLEADING');
    expect(note.helpfulness_score).toBe(0.5);
    expect(note.status).toBe('NEEDS_MORE_RATINGS');
    expect(note.created_at).toBeDefined();
    expect(note.ratings).toEqual([]);
    expect(note.ratings_count).toBe(0);
    expect(note.request).toBeNull();
  });

  it('should create a note with custom values', () => {
    const note = noteWithRatingsFactory.build({
      id: 'custom-note-id',
      summary: 'Custom summary',
      status: 'CURRENTLY_RATED_HELPFUL',
    });

    expect(note.id).toBe('custom-note-id');
    expect(note.summary).toBe('Custom summary');
    expect(note.status).toBe('CURRENTLY_RATED_HELPFUL');
  });

  it('should create a note with ratings using transient params', () => {
    const note = noteWithRatingsFactory.build({}, { transient: { withRatings: 3 } });

    expect(note.ratings.length).toBe(3);
    expect(note.ratings_count).toBe(3);
  });

  it('should create a note with a request using transient params', () => {
    const note = noteWithRatingsFactory.build({}, { transient: { withRequest: true } });

    expect(note.request).not.toBeNull();
    expect(note.request?.request_id).toBeDefined();
    expect(note.request?.content).toBeDefined();
  });

  it('should create a note rated by specific user using transient params', () => {
    const note = noteWithRatingsFactory.build({}, { transient: { ratedByUser: 'user-123' } });

    expect(note.ratings.length).toBe(1);
    expect(note.ratings[0].rater_id).toBe('user-123');
  });

  it('should create a force-published note using transient params', () => {
    const note = noteWithRatingsFactory.build({}, { transient: { forcePublished: true } });

    expect((note as any).force_published).toBe(true);
    expect((note as any).force_published_at).toBeDefined();
  });

  it('should create multiple unique notes with buildList', () => {
    const notes = noteWithRatingsFactory.buildList(3);

    expect(notes.length).toBe(3);
    expect(notes[0].id).not.toBe(notes[1].id);
    expect(notes[1].id).not.toBe(notes[2].id);
  });
});

describe('ratingResponseFactory', () => {
  it('should create a rating with default values', () => {
    const rating = ratingResponseFactory.build();

    expect(rating.id).toBeDefined();
    expect(rating.note_id).toBeDefined();
    expect(rating.rater_id).toBeDefined();
    expect(rating.helpfulness_level).toBe('HELPFUL');
    expect(rating.created_at).toBeDefined();
    expect(rating.updated_at).toBeDefined();
  });

  it('should create a rating with custom values', () => {
    const rating = ratingResponseFactory.build({
      id: 'custom-rating-id',
      helpfulness_level: 'NOT_HELPFUL',
    });

    expect(rating.id).toBe('custom-rating-id');
    expect(rating.helpfulness_level).toBe('NOT_HELPFUL');
  });

  it('should create a rating with specific note_id using transient params', () => {
    const rating = ratingResponseFactory.build({}, { transient: { noteId: 'specific-note' } });

    expect(rating.note_id).toBe('specific-note');
  });
});

describe('requestInfoFactory', () => {
  it('should create a request with default values', () => {
    const request = requestInfoFactory.build();

    expect(request.request_id).toBeDefined();
    expect(request.content).toBeDefined();
    expect(request.requested_by).toBeDefined();
    expect(request.requested_at).toBeDefined();
  });

  it('should create a request with custom values', () => {
    const request = requestInfoFactory.build({
      request_id: 'custom-req-id',
      content: 'Custom content',
    });

    expect(request.request_id).toBe('custom-req-id');
    expect(request.content).toBe('Custom content');
  });
});
