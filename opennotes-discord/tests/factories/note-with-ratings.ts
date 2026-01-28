import { Factory } from 'fishery';
import type { NoteWithRatings, RatingResponse, RequestInfo, NoteStatus } from '../../src/lib/types.js';
import { testUuid } from './test-utils.js';

export interface RatingResponseTransientParams {
  noteId?: string;
}

export const ratingResponseFactory = Factory.define<RatingResponse, RatingResponseTransientParams>(
  ({ sequence, transientParams }) => {
    const { noteId } = transientParams;
    return {
      id: testUuid('0001', sequence),
      note_id: noteId ?? testUuid('n001', sequence),
      rater_id: testUuid('r001', sequence),
      helpfulness_level: 'HELPFUL',
      created_at: '2025-10-31T12:00:00Z',
      updated_at: '2025-10-31T12:00:00Z',
    };
  }
);

export interface RequestInfoTransientParams {}

export const requestInfoFactory = Factory.define<RequestInfo, RequestInfoTransientParams>(
  ({ sequence }) => ({
    request_id: `req-${sequence}`,
    content: `Request content ${sequence}`,
    requested_by: `user-${sequence}`,
    requested_at: '2025-10-31T12:00:00Z',
  })
);

export interface NoteWithRatingsTransientParams {
  withRatings?: number;
  withRequest?: boolean;
  ratedByUser?: string;
  forcePublished?: boolean;
}

export const noteWithRatingsFactory = Factory.define<NoteWithRatings, NoteWithRatingsTransientParams>(
  ({ sequence, transientParams }) => {
    const {
      withRatings = 0,
      withRequest = false,
      ratedByUser,
      forcePublished = false,
    } = transientParams;

    const noteId = `note-${sequence}`;
    const ratings: RatingResponse[] = [];

    for (let i = 0; i < withRatings; i++) {
      ratings.push(
        ratingResponseFactory.build(
          {},
          { transient: { noteId } }
        )
      );
    }

    if (ratedByUser) {
      ratings.push(
        ratingResponseFactory.build(
          { rater_id: ratedByUser },
          { transient: { noteId } }
        )
      );
    }

    const base: NoteWithRatings = {
      id: noteId,
      author_id: testUuid('a001', sequence),
      summary: `This is a test note summary ${sequence}`,
      classification: 'MISINFORMED_OR_POTENTIALLY_MISLEADING',
      helpfulness_score: 0.5,
      status: 'NEEDS_MORE_RATINGS' as NoteStatus,
      created_at: '2025-10-31T12:00:00Z',
      updated_at: '2025-10-31T12:00:00Z',
      ratings,
      ratings_count: ratings.length,
      request: withRequest ? requestInfoFactory.build() : null,
    };

    if (forcePublished) {
      (base as any).force_published = true;
      (base as any).force_published_at = '2025-11-08T10:00:00Z';
    }

    return base;
  }
);
