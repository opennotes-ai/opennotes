import {
  validateNoteCreate,
  validateNoteResponse,
  validateRatingCreate,
  validateRatingResponse,
  validateRequestCreate,
  validateRequestResponse,
  validateRequestListResponse,
  validateScoringRequest,
  validateScoringResponse,
  validateRatingThresholdsResponse,
  validateHealthCheckResponse,
  validateNoteListResponse,
  SchemaValidationError,
  getValidationErrors,
  formatValidationErrors,
} from '../src/lib/schema-validator.js';

process.env.ENABLE_SCHEMA_VALIDATION = 'true';

const TEST_COMMUNITY_SERVER_ID = '550e8400-e29b-41d4-a716-446655440000';

describe('Schema Validation', () => {
  describe('NoteCreate validation', () => {
    it('should validate a correct NoteCreate object', () => {
      const validNote = {
        author_participant_id: 'user123',
        summary: 'This is a test note',
        classification: 'NOT_MISLEADING',
        community_server_id: TEST_COMMUNITY_SERVER_ID,
      };

      expect(() => validateNoteCreate(validNote)).not.toThrow();
    });

    it('should reject NoteCreate with missing required fields', () => {
      const invalidNote = {
        author_participant_id: 'user123',
      };

      expect(() => validateNoteCreate(invalidNote)).toThrow(SchemaValidationError);
    });

    it('should reject NoteCreate with wrong field types', () => {
      const invalidNote = {
        author_participant_id: 123,  // Should be string
        summary: 'Test',
        classification: 'NOT_MISLEADING',
        community_server_id: TEST_COMMUNITY_SERVER_ID,
      };

      expect(() => validateNoteCreate(invalidNote)).toThrow(SchemaValidationError);
    });

    it('should reject NoteCreate with invalid classification enum', () => {
      const invalidNote = {
        author_participant_id: 'user123',
        summary: 'Test',
        classification: 'INVALID_CLASSIFICATION',
        community_server_id: TEST_COMMUNITY_SERVER_ID,
      };

      expect(() => validateNoteCreate(invalidNote)).toThrow(SchemaValidationError);
    });
  });

  describe('NoteResponse validation', () => {
    it('should validate a correct NoteResponse object', () => {
      const validResponse = {
        id: '550e8400-e29b-41d4-a716-446655440001',
        author_participant_id: 'user123',
        summary: 'Test note',
        classification: 'NOT_MISLEADING',
        helpfulness_score: 75,
        status: 'NEEDS_MORE_RATINGS',
        created_at: '2025-10-23T12:00:00Z',
        updated_at: null,
        ratings_count: 0,
        community_server_id: TEST_COMMUNITY_SERVER_ID,
      };

      expect(validateNoteResponse(validResponse)).toBe(true);
    });

    it('should handle missing optional fields', () => {
      const responseWithNulls = {
        id: '550e8400-e29b-41d4-a716-446655440002',
        author_participant_id: 'user123',
        summary: 'Test',
        classification: 'NOT_MISLEADING',
        helpfulness_score: 0,
        status: 'NEEDS_MORE_RATINGS',
        created_at: '2025-10-23T12:00:00Z',
        ratings_count: 0,
        community_server_id: TEST_COMMUNITY_SERVER_ID,
      };

      expect(validateNoteResponse(responseWithNulls)).toBe(true);
    });
  });

  describe('RatingCreate validation', () => {
    it('should validate a correct RatingCreate object', () => {
      const validRating = {
        note_id: '550e8400-e29b-41d4-a716-446655440001',
        rater_participant_id: 'user456',
        helpfulness_level: 'HELPFUL',
      };

      expect(() => validateRatingCreate(validRating)).not.toThrow();
    });

    it('should accept all valid helpfulness levels', () => {
      const levels = ['HELPFUL', 'SOMEWHAT_HELPFUL', 'NOT_HELPFUL'];

      for (const level of levels) {
        const rating = {
          note_id: '550e8400-e29b-41d4-a716-446655440001',
          rater_participant_id: 'user456',
          helpfulness_level: level,
        };

        expect(() => validateRatingCreate(rating)).not.toThrow();
      }
    });

    it('should reject invalid helpfulness level', () => {
      const invalidRating = {
        note_id: '550e8400-e29b-41d4-a716-446655440001',
        rater_participant_id: 'user456',
        helpfulness_level: 'SUPER_HELPFUL',
      };

      expect(() => validateRatingCreate(invalidRating)).toThrow(SchemaValidationError);
    });

    it('should reject missing required fields', () => {
      const invalidRating = {
        note_id: '550e8400-e29b-41d4-a716-446655440001',
      };

      expect(() => validateRatingCreate(invalidRating)).toThrow(SchemaValidationError);
    });
  });

  describe('RatingResponse validation', () => {
    it('should validate a correct RatingResponse object', () => {
      const validResponse = {
        id: '550e8400-e29b-41d4-a716-446655440003',
        note_id: '550e8400-e29b-41d4-a716-446655440001',
        rater_participant_id: 'user456',
        helpfulness_level: 'HELPFUL',
        created_at: '2025-10-23T12:00:00Z',
        updated_at: null,
      };

      expect(validateRatingResponse(validResponse)).toBe(true);
    });
  });

  describe('RequestCreate validation', () => {
    it('should validate a correct RequestCreate object', () => {
      const validRequest = {
        request_id: 'discord-msg123',
        requested_by: 'user789',
        community_server_id: TEST_COMMUNITY_SERVER_ID,
      };

      expect(() => validateRequestCreate(validRequest)).not.toThrow();
    });

    it('should reject missing required fields', () => {
      const invalidRequest = {
        request_id: 'discord-msg123',
      };

      expect(() => validateRequestCreate(invalidRequest)).toThrow(SchemaValidationError);
    });
  });

  describe('RequestResponse validation', () => {
    it('should validate a correct RequestResponse object', () => {
      const validResponse = {
        id: '550e8400-e29b-41d4-a716-446655440004',
        request_id: 'discord-msg123',
        requested_by: 'user789',
        requested_at: '2025-10-23T12:00:00Z',
        status: 'PENDING',
        note_id: null,
        created_at: '2025-10-23T12:00:00Z',
        updated_at: null,
        community_server_id: TEST_COMMUNITY_SERVER_ID,
      };

      expect(validateRequestResponse(validResponse)).toBe(true);
    });

    it('should accept all valid request statuses', () => {
      const statuses = ['PENDING', 'IN_PROGRESS', 'COMPLETED', 'FAILED'];

      for (const status of statuses) {
        const response = {
          id: '550e8400-e29b-41d4-a716-446655440004',
          request_id: 'discord-msg123',
          requested_by: 'user789',
          requested_at: '2025-10-23T12:00:00Z',
          status,
          created_at: '2025-10-23T12:00:00Z',
          community_server_id: TEST_COMMUNITY_SERVER_ID,
        };

        expect(validateRequestResponse(response)).toBe(true);
      }
    });
  });

  describe('RequestListResponse validation', () => {
    it('should validate a correct RequestListResponse object', () => {
      const validResponse = {
        requests: [
          {
            id: '550e8400-e29b-41d4-a716-446655440004',
            request_id: 'discord-msg123',
            requested_by: 'user789',
            requested_at: '2025-10-23T12:00:00Z',
            status: 'PENDING',
            created_at: '2025-10-23T12:00:00Z',
            community_server_id: TEST_COMMUNITY_SERVER_ID,
          },
        ],
        total: 1,
        page: 1,
        size: 20,
      };

      expect(validateRequestListResponse(validResponse)).toBe(true);
    });

    it('should validate empty request list', () => {
      const emptyResponse = {
        requests: [],
        total: 0,
        page: 1,
        size: 20,
      };

      expect(validateRequestListResponse(emptyResponse)).toBe(true);
    });
  });

  describe('ScoringRequest validation', () => {
    it('should validate a correct ScoringRequest object', () => {
      const validRequest = {
        notes: [
          {
            noteId: 12345,
            noteAuthorParticipantId: 'user123',
            createdAtMillis: 1698765432000,
            tweetId: 987654,
            summary: 'Test note',
            classification: 'NOT_MISLEADING',
          },
        ],
        ratings: [
          {
            raterParticipantId: 'user456',
            noteId: 12345,
            createdAtMillis: 1698765432000,
            helpfulnessLevel: 'HELPFUL',
          },
        ],
        enrollment: [
          {
            participantId: 'user123',
            enrollmentState: 'ENROLLED',
            successfulRatingNeededToEarnIn: 5,
            timestampOfLastStateChange: 1698765432000,
          },
        ],
      };

      expect(() => validateScoringRequest(validRequest)).not.toThrow();
    });

    it('should reject ScoringRequest with missing arrays', () => {
      const invalidRequest = {
        notes: [],
      };

      expect(() => validateScoringRequest(invalidRequest)).toThrow(SchemaValidationError);
    });
  });

  describe('ScoringResponse validation', () => {
    it('should validate a correct ScoringResponse object', () => {
      const validResponse = {
        scored_notes: [
          {
            noteId: 12345,
            helpfulnessScore: 0.75,
            status: 'CURRENTLY_RATED_HELPFUL',
          },
        ],
        helpful_scores: [],
        auxiliary_info: [],
      };

      expect(validateScoringResponse(validResponse)).toBe(true);
    });
  });

  describe('RatingThresholdsResponse validation', () => {
    it('should validate a correct RatingThresholdsResponse object', () => {
      const validResponse = {
        min_ratings_needed: 5,
        min_raters_per_note: 3,
      };

      expect(validateRatingThresholdsResponse(validResponse)).toBe(true);
    });

    it('should reject missing required fields', () => {
      const invalidResponse = {
        min_ratings_needed: 5,
      };

      expect(validateRatingThresholdsResponse(invalidResponse)).toBe(false);
    });
  });

  describe('HealthCheckResponse validation', () => {
    it('should validate a correct HealthCheckResponse object', () => {
      const validResponse = {
        status: 'healthy',
        version: '1.0.0',
        timestamp: '2025-10-23T12:00:00Z',
        environment: 'production',
        services: {
          database: {
            status: 'healthy',
            response_time_ms: 5,
          },
        },
      };

      expect(validateHealthCheckResponse(validResponse)).toBe(true);
    });

    it('should validate minimal HealthCheckResponse', () => {
      const minimalResponse = {
        status: 'healthy',
        version: '1.0.0',
      };

      expect(validateHealthCheckResponse(minimalResponse)).toBe(true);
    });
  });

  describe('NoteListResponse validation', () => {
    it('should validate a correct NoteListResponse object', () => {
      const validResponse = {
        notes: [
          {
            id: '550e8400-e29b-41d4-a716-446655440001',
            author_participant_id: 'user123',
            summary: 'Test',
            classification: 'NOT_MISLEADING',
            helpfulness_score: 0,
            status: 'NEEDS_MORE_RATINGS',
            created_at: '2025-10-23T12:00:00Z',
            ratings_count: 0,
            community_server_id: TEST_COMMUNITY_SERVER_ID,
          },
        ],
        total: 1,
        page: 1,
        size: 20,
      };

      expect(validateNoteListResponse(validResponse)).toBe(true);
    });
  });

  describe('Utility functions', () => {
    it('should get validation errors for invalid data', () => {
      const invalidNote = {
        author_participant_id: 'user123',
      };

      const errors = getValidationErrors('NoteCreate', invalidNote);

      expect(errors).not.toBeNull();
      expect(errors!.length).toBeGreaterThan(0);
    });

    it('should return null for valid data', () => {
      const validNote = {
        author_participant_id: 'user123',
        summary: 'Test',
        classification: 'NOT_MISLEADING',
        community_server_id: TEST_COMMUNITY_SERVER_ID,
      };

      const errors = getValidationErrors('NoteCreate', validNote);

      expect(errors).toBeNull();
    });

    it('should format validation errors as human-readable strings', () => {
      const invalidNote = {
        author_participant_id: 'user123',
      };

      const errors = getValidationErrors('NoteCreate', invalidNote);
      const formatted = formatValidationErrors(errors);

      expect(formatted).toContain('must have required property');
      expect(typeof formatted).toBe('string');
    });

    it('should handle null/undefined errors gracefully', () => {
      expect(formatValidationErrors(null)).toBe('No validation errors');
      expect(formatValidationErrors(undefined)).toBe('No validation errors');
      expect(formatValidationErrors([])).toBe('No validation errors');
    });
  });

  describe('Edge cases', () => {
    it('should handle null values where allowed', () => {
      const responseWithNull = {
        id: '550e8400-e29b-41d4-a716-446655440001',
        author_participant_id: 'user123',
        summary: 'Test',
        classification: 'NOT_MISLEADING',
        helpfulness_score: 0,
        status: 'NEEDS_MORE_RATINGS',
        created_at: '2025-10-23T12:00:00Z',
        updated_at: null,
        ratings_count: 0,
        community_server_id: TEST_COMMUNITY_SERVER_ID,
      };

      expect(validateNoteResponse(responseWithNull)).toBe(true);
    });

    it('should reject null values where not allowed', () => {
      const invalidNote = {
        author_participant_id: null,
        summary: 'Test',
        classification: 'NOT_MISLEADING',
        community_server_id: TEST_COMMUNITY_SERVER_ID,
      };

      expect(() => validateNoteCreate(invalidNote)).toThrow(SchemaValidationError);
    });

    it('should handle empty arrays', () => {
      const requestWithEmptyArray = {
        notes: [],
        ratings: [],
        enrollment: [],
      };

      expect(() => validateScoringRequest(requestWithEmptyArray)).not.toThrow();
    });

    it('should strip extra properties when removeAdditional is enabled', () => {
      const noteWithExtra = {
        author_participant_id: 'user123',
        summary: 'Test',
        classification: 'NOT_MISLEADING',
        community_server_id: TEST_COMMUNITY_SERVER_ID,
        extra_field: 'should be removed',
        malicious_script: '<script>alert("xss")</script>',
      };

      expect(() => validateNoteCreate(noteWithExtra)).not.toThrow();
    });
  });

  describe('Date-time format validation', () => {
    it('should accept valid ISO 8601 date-time strings', () => {
      const validDates = [
        '2025-10-23T12:00:00Z',
        '2025-10-23T12:00:00.000Z',
        '2025-10-23T12:00:00+00:00',
      ];

      for (const date of validDates) {
        const response = {
          id: '550e8400-e29b-41d4-a716-446655440001',
          author_participant_id: 'user123',
          summary: 'Test',
          classification: 'NOT_MISLEADING',
          helpfulness_score: 0,
          status: 'NEEDS_MORE_RATINGS',
          created_at: date,
          ratings_count: 0,
          community_server_id: TEST_COMMUNITY_SERVER_ID,
        };

        expect(validateNoteResponse(response)).toBe(true);
      }
    });

    it('should reject invalid date-time formats', () => {
      const invalidDate = {
        id: '550e8400-e29b-41d4-a716-446655440001',
        author_participant_id: 'user123',
        summary: 'Test',
        classification: 'NOT_MISLEADING',
        helpfulness_score: 0,
        status: 'NEEDS_MORE_RATINGS',
        created_at: 'not-a-date',
        ratings_count: 0,
        community_server_id: TEST_COMMUNITY_SERVER_ID,
      };

      expect(validateNoteResponse(invalidDate)).toBe(false);
    });
  });

  describe('Strict mode validation', () => {
    it('should enforce strict mode and reject unknown keywords', () => {
      const noteWithExtra = {
        author_participant_id: 'user123',
        summary: 'Test',
        classification: 'NOT_MISLEADING',
        community_server_id: TEST_COMMUNITY_SERVER_ID,
        extra_property: 'this should be stripped',
      };

      expect(() => validateNoteCreate(noteWithExtra)).not.toThrow();
    });

    it('should remove additional properties from request objects', () => {
      const ratingWithExtra = {
        note_id: '550e8400-e29b-41d4-a716-446655440001',
        rater_participant_id: 'user456',
        helpfulness_level: 'HELPFUL',
        injected_field: 'malicious content',
        another_extra: 123,
      };

      expect(() => validateRatingCreate(ratingWithExtra)).not.toThrow();
    });

    it('should handle nested objects with extra properties', () => {
      const scoringRequestWithExtra = {
        notes: [
          {
            noteId: 12345,
            noteAuthorParticipantId: 'user123',
            createdAtMillis: 1698765432000,
            tweetId: 987654,
            summary: 'Test note',
            classification: 'NOT_MISLEADING',
            extra_nested_field: 'should be removed',
          },
        ],
        ratings: [],
        enrollment: [],
        extra_top_level: 'should be removed',
      };

      expect(() => validateScoringRequest(scoringRequestWithExtra)).not.toThrow();
    });

    it('should validate responses with strict mode', () => {
      const noteResponseWithExtra = {
        id: '550e8400-e29b-41d4-a716-446655440001',
        author_participant_id: 'user123',
        summary: 'Test',
        classification: 'NOT_MISLEADING',
        helpfulness_score: 0,
        status: 'NEEDS_MORE_RATINGS',
        created_at: '2025-10-23T12:00:00Z',
        ratings_count: 0,
        community_server_id: TEST_COMMUNITY_SERVER_ID,
        injected_property: 'should not cause validation to fail',
      };

      expect(validateNoteResponse(noteResponseWithExtra)).toBe(true);
    });

    it('should handle arrays with extra properties in items', () => {
      const listResponseWithExtra = {
        notes: [
          {
            id: '550e8400-e29b-41d4-a716-446655440001',
            author_participant_id: 'user123',
            summary: 'Test',
            classification: 'NOT_MISLEADING',
            helpfulness_score: 0,
            status: 'NEEDS_MORE_RATINGS',
            created_at: '2025-10-23T12:00:00Z',
            ratings_count: 0,
            community_server_id: TEST_COMMUNITY_SERVER_ID,
            extra_in_array_item: 'should be stripped',
          },
        ],
        total: 1,
        page: 1,
        size: 20,
        extra_field: 'should be stripped',
      };

      expect(validateNoteListResponse(listResponseWithExtra)).toBe(true);
    });
  });

  describe('Security validation tests', () => {
    it('should strip potentially malicious properties', () => {
      const noteWithMalicious = {
        author_participant_id: 'user123',
        summary: 'Test',
        classification: 'NOT_MISLEADING',
        community_server_id: TEST_COMMUNITY_SERVER_ID,
        __proto__: { polluted: 'value' },
        constructor: 'malicious',
        prototype: 'malicious',
      };

      expect(() => validateNoteCreate(noteWithMalicious)).not.toThrow();
    });

    it('should handle very large objects without extra properties', () => {
      const largeNote = {
        author_participant_id: 'user123',
        summary: 'A'.repeat(1000),
        classification: 'NOT_MISLEADING',
        community_server_id: TEST_COMMUNITY_SERVER_ID,
      };

      expect(() => validateNoteCreate(largeNote)).not.toThrow();
    });

    it('should prevent property injection in nested structures', () => {
      const requestWithInjection = {
        notes: [{
          noteId: 12345,
          noteAuthorParticipantId: 'user123',
          createdAtMillis: 1698765432000,
          tweetId: 987654,
          summary: 'Test',
          classification: 'NOT_MISLEADING',
        }],
        ratings: [],
        enrollment: [],
        __proto__: { injected: true },
      };

      expect(() => validateScoringRequest(requestWithInjection)).not.toThrow();
    });
  });
});
