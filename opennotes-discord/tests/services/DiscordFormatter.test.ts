import { DiscordFormatter } from '../../src/services/DiscordFormatter.js';
import { ErrorCode, ServiceResult, ListRequestsResult } from '../../src/services/types.js';
import type { NoteScoreResponse, TopNotesResponse, ScoreConfidence } from '../../src/services/ScoringService.js';
import { Colors, ButtonStyle, type APIButtonComponentWithCustomId } from 'discord.js';
import type { RequestItem } from '../../src/lib/types.js';
import { TEST_SCORE_ABOVE_THRESHOLD } from '../test-constants.js';

describe('DiscordFormatter', () => {
  describe('formatError', () => {
    it('should format CONFLICT error with helpful message', () => {
      const result: ServiceResult<any> = {
        success: false,
        error: {
          code: ErrorCode.CONFLICT,
          message: "You've already rated this note.",
          details: {
            errorId: 'err_test123456',
            statusCode: 409,
            helpText: 'Use `/view-notes` to see all your ratings.',
          },
        },
      };

      const formatted = DiscordFormatter.formatError(result);

      expect(formatted.content).toContain("You've already rated this note.");
      expect(formatted.content).toContain('💡 Use `/view-notes` to see all your ratings.');
      expect(formatted.content).toContain('Error ID: `err_test123456`');
    });

    it('should format CONFLICT error without help text', () => {
      const result: ServiceResult<any> = {
        success: false,
        error: {
          code: ErrorCode.CONFLICT,
          message: 'This action conflicts with existing data.',
          details: {
            errorId: 'err_abc123',
            statusCode: 409,
          },
        },
      };

      const formatted = DiscordFormatter.formatError(result);

      expect(formatted.content).toContain('This action conflicts with existing data.');
      expect(formatted.content).toContain('Error ID: `err_abc123`');
      expect(formatted.content).not.toContain('💡');
    });

    it('should format CONFLICT error without error ID', () => {
      const result: ServiceResult<any> = {
        success: false,
        error: {
          code: ErrorCode.CONFLICT,
          message: 'Duplicate entry detected.',
          details: {
            helpText: 'Check your existing data.',
          },
        },
      };

      const formatted = DiscordFormatter.formatError(result);

      expect(formatted.content).toContain('Duplicate entry detected.');
      expect(formatted.content).toContain('💡 Check your existing data.');
      expect(formatted.content).not.toContain('Error ID:');
    });

    it('should format VALIDATION_ERROR', () => {
      const result: ServiceResult<any> = {
        success: false,
        error: {
          code: ErrorCode.VALIDATION_ERROR,
          message: 'Note ID is required',
        },
      };

      const formatted = DiscordFormatter.formatError(result);

      expect(formatted.content).toBe('Note ID is required');
    });

    it('should format NOT_FOUND error', () => {
      const result: ServiceResult<any> = {
        success: false,
        error: {
          code: ErrorCode.NOT_FOUND,
          message: 'Note not found',
        },
      };

      const formatted = DiscordFormatter.formatError(result);

      expect(formatted.content).toBe('Note not found');
    });

    it('should format RATE_LIMIT_EXCEEDED error', () => {
      const resetTime = Date.now() + 60000;
      const resetTimeSeconds = Math.floor(resetTime / 1000);

      const result: ServiceResult<any> = {
        success: false,
        error: {
          code: ErrorCode.RATE_LIMIT_EXCEEDED,
          message: 'Rate limit exceeded',
          details: {
            resetAt: resetTime,
          },
        },
      };

      const formatted = DiscordFormatter.formatError(result);

      expect(formatted.content).toContain('Rate limit exceeded');
      expect(formatted.content).toContain(`<t:${resetTimeSeconds}:R>`);
    });

    it('should handle error without error object', () => {
      const result: ServiceResult<any> = {
        success: false,
      };

      const formatted = DiscordFormatter.formatError(result);

      expect(formatted.content).toBe('An unknown error occurred');
    });

    it('should handle unknown error code', () => {
      const result: ServiceResult<any> = {
        success: false,
        error: {
          code: 'UNKNOWN_CODE' as ErrorCode,
          message: 'Something went wrong',
        },
      };

      const formatted = DiscordFormatter.formatError(result);

      expect(formatted.content).toBe('An unexpected error occurred. Please try again later.');
    });
  });

  describe('score formatting utilities', () => {
    describe('getConfidenceEmoji', () => {
      it('should return star emoji for standard confidence', () => {
        expect(DiscordFormatter.getConfidenceEmoji('standard')).toBe('⭐');
      });

      it('should return warning emoji for provisional confidence', () => {
        expect(DiscordFormatter.getConfidenceEmoji('provisional')).toBe('⚠️');
      });

      it('should return question emoji for no_data confidence', () => {
        expect(DiscordFormatter.getConfidenceEmoji('no_data')).toBe('❓');
      });

      it('should return question emoji for unknown confidence', () => {
        expect(DiscordFormatter.getConfidenceEmoji('unknown' as ScoreConfidence)).toBe('❓');
      });
    });

    describe('getConfidenceLabel', () => {
      it('should return correct label for standard confidence', () => {
        expect(DiscordFormatter.getConfidenceLabel('standard')).toBe('Standard (5+ ratings)');
      });

      it('should return correct label for provisional confidence', () => {
        expect(DiscordFormatter.getConfidenceLabel('provisional')).toBe('Provisional (<5 ratings)');
      });

      it('should return correct label for no_data confidence', () => {
        expect(DiscordFormatter.getConfidenceLabel('no_data')).toBe('No data (0 ratings)');
      });
    });

    describe('getScoreColor', () => {
      it('should return green for high scores', () => {
        expect(DiscordFormatter.getScoreColor(0.7)).toBe(Colors.Green);
        expect(DiscordFormatter.getScoreColor(TEST_SCORE_ABOVE_THRESHOLD)).toBe(Colors.Green);
        expect(DiscordFormatter.getScoreColor(1.0)).toBe(Colors.Green);
      });

      it('should return yellow for medium scores', () => {
        expect(DiscordFormatter.getScoreColor(0.4)).toBe(Colors.Yellow);
        expect(DiscordFormatter.getScoreColor(0.55)).toBe(Colors.Yellow);
        expect(DiscordFormatter.getScoreColor(0.69)).toBe(Colors.Yellow);
      });

      it('should return red for low scores', () => {
        expect(DiscordFormatter.getScoreColor(0.0)).toBe(Colors.Red);
        expect(DiscordFormatter.getScoreColor(0.2)).toBe(Colors.Red);
        expect(DiscordFormatter.getScoreColor(0.39)).toBe(Colors.Red);
      });
    });

    describe('formatScore', () => {
      it('should format score to 3 decimal places', () => {
        expect(DiscordFormatter.formatScore(0.75)).toBe('0.750');
        expect(DiscordFormatter.formatScore(0.7)).toBe('0.700');
        expect(DiscordFormatter.formatScore(0.714285)).toBe('0.714');
      });
    });
  });

  describe('formatNoteScore', () => {
    const mockScoreResponse: NoteScoreResponse = {
      note_id: '123',
      score: 0.75,
      confidence: 'standard',
      algorithm: 'MFCoreScorer',
      rating_count: 10,
      tier: 2,
      tier_name: 'Tier 2 (1k-5k notes)',
      calculated_at: '2025-10-28T12:00:00Z',
    };

    it('should format note score with all fields', () => {
      const result = DiscordFormatter.formatNoteScore(mockScoreResponse);

      expect(result.embeds).toHaveLength(1);
      const embed = result.embeds[0];
      expect(embed.data.title).toBe('Note Score: 0.750');
      expect(embed.data.color).toBe(Colors.Green);
      expect(embed.data.fields).toEqual(
        expect.arrayContaining([
          expect.objectContaining({ name: 'Note ID', value: '123' }),
          expect.objectContaining({ name: 'Score', value: '0.750 (0.0-1.0)' }),
          expect.objectContaining({ name: 'Confidence', value: '⭐ Standard (5+ ratings)' }),
          expect.objectContaining({ name: 'Rating Count', value: '10' }),
          expect.objectContaining({ name: 'Algorithm', value: 'MFCoreScorer' }),
          expect.objectContaining({ name: 'Tier', value: 'Tier 2' }),
        ])
      );
    });

    it('should use green color for high scores', () => {
      const highScoreResponse = { ...mockScoreResponse, score: TEST_SCORE_ABOVE_THRESHOLD };
      const result = DiscordFormatter.formatNoteScore(highScoreResponse);

      expect(result.embeds[0].data.color).toBe(Colors.Green);
    });

    it('should use red color for low scores', () => {
      const lowScoreResponse = { ...mockScoreResponse, score: 0.25 };
      const result = DiscordFormatter.formatNoteScore(lowScoreResponse);

      expect(result.embeds[0].data.color).toBe(Colors.Red);
    });

    it('should include tier 0 Bayesian explanation', () => {
      const tier0Response: NoteScoreResponse = {
        ...mockScoreResponse,
        tier: 0,
        algorithm: 'bayesian_average_tier0',
        rating_count: 3,
      };
      const result = DiscordFormatter.formatNoteScore(tier0Response);

      const description = result.embeds[0].data.description;
      expect(description).toContain('Bootstrap Phase (Tier 0)');
      expect(description).toContain('Bayesian Average');
    });
  });

  describe('formatTopNotes', () => {
    const mockTopNotesResponse: TopNotesResponse = {
      notes: [
        {
          note_id: '123',
          score: TEST_SCORE_ABOVE_THRESHOLD,
          confidence: 'standard',
          algorithm: 'MFCoreScorer',
          rating_count: 15,
          tier: 2,
          tier_name: 'Tier 2',
          calculated_at: '2025-10-28T12:00:00Z',
        },
        {
          note_id: '456',
          score: 0.72,
          confidence: 'standard',
          algorithm: 'MFCoreScorer',
          rating_count: 12,
          tier: 2,
          tier_name: 'Tier 2',
          calculated_at: '2025-10-28T12:00:00Z',
        },
      ],
      total_count: 50,
      current_tier: 2,
    };

    it('should format top notes list', () => {
      const result = DiscordFormatter.formatTopNotes(mockTopNotesResponse, 1, 10);

      expect(result.embeds).toHaveLength(1);
      const embed = result.embeds[0];
      expect(embed.data.title).toBe('Top Scored Notes');
      expect(embed.data.fields).toHaveLength(2);
      expect(embed.data.footer?.text).toContain('Page 1 of 5');
      expect(embed.data.footer?.text).toContain('Total: 50 notes');
    });

    it('should include filters in description', () => {
      const responseWithFilters: TopNotesResponse = {
        ...mockTopNotesResponse,
        current_tier: 2,
        filters_applied: {
          min_confidence: 'standard',
          tier: 2,
        },
      };
      const result = DiscordFormatter.formatTopNotes(responseWithFilters, 1, 10);

      const description = result.embeds[0].data.description;
      expect(description).toContain('Min Confidence: standard');
      expect(description).toContain('Tier: 2');
    });

    it('should handle empty notes list', () => {
      const emptyResponse: TopNotesResponse = {
        notes: [],
        total_count: 0,
        current_tier: 0,
      };
      const result = DiscordFormatter.formatTopNotes(emptyResponse, 1, 10);

      expect(result.embeds).toHaveLength(1);
      expect(result.embeds[0].data.description).toBe('No notes found matching the criteria.');
    });
  });

  describe('formatScoreInNoteEmbed', () => {
    it('should format score field for note with score', () => {
      const scoreData: NoteScoreResponse = {
        note_id: '123',
        score: 0.75,
        confidence: 'standard',
        algorithm: 'MFCoreScorer',
        rating_count: 10,
        tier: 2,
        tier_name: 'Tier 2',
        calculated_at: '2025-10-28T12:00:00Z',
      };

      const field = DiscordFormatter.formatScoreInNoteEmbed(scoreData);

      expect(field).toEqual({
        name: 'Score',
        value: '🟢 0.750 ⭐',
        inline: true,
      });
    });

    it('should show not yet scored for null score', () => {
      const field = DiscordFormatter.formatScoreInNoteEmbed(null);

      expect(field).toEqual({
        name: 'Score',
        value: '❓ Not yet scored',
        inline: true,
      });
    });

    it('should use correct color emoji for high scores', () => {
      const highScore: NoteScoreResponse = {
        note_id: '123',
        score: TEST_SCORE_ABOVE_THRESHOLD,
        confidence: 'standard',
        algorithm: 'MFCoreScorer',
        rating_count: 10,
        tier: 2,
        tier_name: 'Tier 2',
        calculated_at: '2025-10-28T12:00:00Z',
      };

      const field = DiscordFormatter.formatScoreInNoteEmbed(highScore);

      expect(field?.value).toContain('🟢');
    });
  });

  describe('formatListRequestsSuccess', () => {
    const createMockRequest = (overrides?: Partial<RequestItem>): RequestItem => ({
      id: '1',
      request_id: 'discord-123456789-1700000000000',
      requested_by: 'user_789',
      requested_at: '2025-10-28T12:00:00Z',
      status: 'PENDING',
      note_id: null,
      created_at: '2025-10-28T12:00:00Z',
      updated_at: null,
      platform_message_id: null,
      community_server_id: 'guild_123',
      content: null,
      ...overrides,
    });

    describe('message ID display (task 465, task 675)', () => {
      it('should display platform_message_id in Message field when available', async () => {
        const mockResult: ListRequestsResult = {
          requests: [
            createMockRequest({
              platform_message_id: '1234567890123456789',
            }),
          ],
          total: 1,
          page: 1,
          size: 10,
        };

        const result = await DiscordFormatter.formatListRequestsSuccess(mockResult);

        expect(result.items).toHaveLength(1);
        const firstItem = result.items[0];
        const embed = firstItem.embed;
        const description = embed.data.description;
        expect(description).toContain('**Message:** 1234567890123456789');
      });

      it('should extract message ID from request_id when platform_message_id is null (task 675)', async () => {
        const mockResult: ListRequestsResult = {
          requests: [
            createMockRequest({
              request_id: 'discord-987654321-1700000000000',
              platform_message_id: null,
            }),
          ],
          total: 1,
          page: 1,
          size: 10,
        };

        const result = await DiscordFormatter.formatListRequestsSuccess(mockResult);

        const firstItem = result.items[0];
        const description = firstItem.embed.data.description;
        expect(description).toContain('**Message:** 987654321');
      });

      it('should display "No message ID" when platform_message_id is null and request_id is not extractable', async () => {
        const mockResult: ListRequestsResult = {
          requests: [
            createMockRequest({
              request_id: 'req-123',
              platform_message_id: null,
            }),
          ],
          total: 1,
          page: 1,
          size: 10,
        };

        const result = await DiscordFormatter.formatListRequestsSuccess(mockResult);

        const firstItem = result.items[0];
        const description = firstItem.embed.data.description;
        expect(description).toContain('**Message:** No message ID');
      });

      it('should not display duplicate message ID field', async () => {
        const mockResult: ListRequestsResult = {
          requests: [
            createMockRequest({
              platform_message_id: '1234567890123456789',
            }),
          ],
          total: 1,
          page: 1,
          size: 10,
        };

        const result = await DiscordFormatter.formatListRequestsSuccess(mockResult);

        const description = result.items[0].embed.data.description || '';
        const messageMatches = (description.match(/\*\*Message:\*\*/g) || []).length;
        expect(messageMatches).toBe(1);
      });
    });

    describe('write note button rendering (task 464)', () => {
      it('should create button for PENDING request with platform_message_id', async () => {
        const mockResult: ListRequestsResult = {
          requests: [
            createMockRequest({
              status: 'PENDING',
              platform_message_id: '1234567890123456789',
              request_id: 'req_abc',
            }),
          ],
          total: 1,
          page: 1,
          size: 10,
        };

        const result = await DiscordFormatter.formatListRequestsSuccess(mockResult);

        expect(result.items[0].buttons).toBeDefined();
        expect(result.items[0].buttons).toHaveLength(1);
        const buttons = result.items[0].buttons[0].components;
        expect(buttons).toHaveLength(3);

        // Check Not Misleading button
        const notMisleadingButton = buttons[0].data as APIButtonComponentWithCustomId;
        expect(notMisleadingButton.custom_id).toMatch(/^write_note:NOT_MISLEADING:[A-Za-z0-9_-]{16}$/);
        expect(notMisleadingButton.label).toBe('Not Misleading');
        expect(notMisleadingButton.style).toBe(ButtonStyle.Success);

        // Check Misinformed button
        const misinformedButton = buttons[1].data as APIButtonComponentWithCustomId;
        expect(misinformedButton.custom_id).toMatch(/^write_note:MISINFORMED_OR_POTENTIALLY_MISLEADING:[A-Za-z0-9_-]{16}$/);
        expect(misinformedButton.label).toBe('Misinformed or Misleading');
        expect(misinformedButton.style).toBe(ButtonStyle.Danger);

        // Check AI Generate button
        const aiButton = buttons[2].data as APIButtonComponentWithCustomId;
        expect(aiButton.custom_id).toMatch(/^ai_write_note:[A-Za-z0-9_-]{16}$/);
        expect(aiButton.label).toBe('✨ AI Generate');
        expect(aiButton.style).toBe(ButtonStyle.Primary);
      });

      it('should not create button when no message ID is available (neither platform_message_id nor extractable from request_id)', async () => {
        const mockResult: ListRequestsResult = {
          requests: [
            createMockRequest({
              request_id: 'req-123',
              status: 'PENDING',
              platform_message_id: null,
            }),
          ],
          total: 1,
          page: 1,
          size: 10,
        };

        const result = await DiscordFormatter.formatListRequestsSuccess(mockResult);

        expect(result.items[0].buttons).toHaveLength(0);
      });

      it('should create button when message ID can be extracted from request_id (task 675)', async () => {
        const mockResult: ListRequestsResult = {
          requests: [
            createMockRequest({
              request_id: 'discord-987654321-1700000000000',
              status: 'PENDING',
              platform_message_id: null,
            }),
          ],
          total: 1,
          page: 1,
          size: 10,
        };

        const result = await DiscordFormatter.formatListRequestsSuccess(mockResult);

        expect(result.items[0].buttons).toHaveLength(1);
      });

      it('should not create button for non-PENDING requests', async () => {
        const mockResult: ListRequestsResult = {
          requests: [
            createMockRequest({
              status: 'COMPLETED',
              platform_message_id: '1234567890123456789',
            }),
            createMockRequest({
              status: 'IN_PROGRESS',
              platform_message_id: '9876543210987654321',
            }),
            createMockRequest({
              status: 'FAILED',
              platform_message_id: '5555555555555555555',
            }),
          ],
          total: 3,
          page: 1,
          size: 10,
        };

        const result = await DiscordFormatter.formatListRequestsSuccess(mockResult);

        // All non-PENDING requests have no buttons
        result.items.forEach(item => {
          expect(item.buttons).toHaveLength(0);
        });
      });

      it('should create buttons with correct indices and request IDs', async () => {
        const mockResult: ListRequestsResult = {
          requests: [
            createMockRequest({
              status: 'PENDING',
              platform_message_id: '111',
              request_id: 'req_1',
            }),
            createMockRequest({
              status: 'PENDING',
              platform_message_id: '222',
              request_id: 'req_2',
            }),
            createMockRequest({
              status: 'PENDING',
              platform_message_id: '333',
              request_id: 'req_3',
            }),
          ],
          total: 3,
          page: 1,
          size: 10,
        };

        const result = await DiscordFormatter.formatListRequestsSuccess(mockResult);

        // Each request gets its own action row with 3 buttons (Not Misleading + Misinformed + AI Generate)
        expect(result.items).toHaveLength(3);

        // Check first request buttons
        const row1Buttons = result.items[0].buttons[0].components;
        expect(row1Buttons).toHaveLength(3);
        expect((row1Buttons[0].data as APIButtonComponentWithCustomId).label).toBe('Not Misleading');
        expect((row1Buttons[0].data as APIButtonComponentWithCustomId).custom_id).toMatch(/^write_note:NOT_MISLEADING:[A-Za-z0-9_-]{16}$/);
        expect((row1Buttons[1].data as APIButtonComponentWithCustomId).label).toBe('Misinformed or Misleading');
        expect((row1Buttons[1].data as APIButtonComponentWithCustomId).custom_id).toMatch(/^write_note:MISINFORMED_OR_POTENTIALLY_MISLEADING:[A-Za-z0-9_-]{16}$/);
        expect((row1Buttons[2].data as APIButtonComponentWithCustomId).label).toBe('✨ AI Generate');
        expect((row1Buttons[2].data as APIButtonComponentWithCustomId).custom_id).toMatch(/^ai_write_note:[A-Za-z0-9_-]{16}$/);

        // Check second request buttons
        const row2Buttons = result.items[1].buttons[0].components;
        expect(row2Buttons).toHaveLength(3);
        expect((row2Buttons[0].data as APIButtonComponentWithCustomId).label).toBe('Not Misleading');
        expect((row2Buttons[0].data as APIButtonComponentWithCustomId).custom_id).toMatch(/^write_note:NOT_MISLEADING:[A-Za-z0-9_-]{16}$/);

        // Check third request buttons
        const row3Buttons = result.items[2].buttons[0].components;
        expect(row3Buttons).toHaveLength(3);
        expect((row3Buttons[0].data as APIButtonComponentWithCustomId).label).toBe('Not Misleading');
        expect((row3Buttons[0].data as APIButtonComponentWithCustomId).custom_id).toMatch(/^write_note:NOT_MISLEADING:[A-Za-z0-9_-]{16}$/);
      });

      it('should group buttons into rows with max 5 per row', async () => {
        const requests: RequestItem[] = [];
        for (let i = 0; i < 5; i++) {
          requests.push(
            createMockRequest({
              status: 'PENDING',
              platform_message_id: `msg_${i}`,
              request_id: `req_${i}`,
            })
          );
        }

        const mockResult: ListRequestsResult = {
          requests,
          total: 5,
          page: 1,
          size: 20,
        };

        const result = await DiscordFormatter.formatListRequestsSuccess(mockResult);

        // Each request item has its own buttons
        expect(result.items).toHaveLength(5);
        expect(result.items[0].buttons[0].components).toHaveLength(3); // Not Misleading + Misinformed + AI
        expect(result.items[1].buttons[0].components).toHaveLength(3);
        expect(result.items[2].buttons[0].components).toHaveLength(3);
        expect(result.items[3].buttons[0].components).toHaveLength(3);
        expect(result.items[4].buttons[0].components).toHaveLength(3);
      });

      it('should skip buttons for requests without platform_message_id in mixed list', async () => {
        const mockResult: ListRequestsResult = {
          requests: [
            createMockRequest({
              status: 'PENDING',
              platform_message_id: '111',
              request_id: 'req_1',
            }),
            createMockRequest({
              status: 'PENDING',
              platform_message_id: null,
              request_id: 'req_2',
            }),
            createMockRequest({
              status: 'PENDING',
              platform_message_id: '333',
              request_id: 'req_3',
            }),
          ],
          total: 3,
          page: 1,
          size: 10,
        };

        const result = await DiscordFormatter.formatListRequestsSuccess(mockResult);

        // Should have 3 items total, but only 2 have buttons
        expect(result.items).toHaveLength(3);
        expect(result.items[0].buttons[0].components).toHaveLength(3);
        expect(result.items[1].buttons).toHaveLength(0); // No buttons for req_2 (no platform_message_id)
        expect(result.items[2].buttons[0].components).toHaveLength(3);

        // First request buttons
        const row1Buttons = result.items[0].buttons[0].components;
        expect((row1Buttons[0].data as APIButtonComponentWithCustomId).label).toBe('Not Misleading');
        expect((row1Buttons[0].data as APIButtonComponentWithCustomId).custom_id).toMatch(/^write_note:NOT_MISLEADING:[A-Za-z0-9_-]{16}$/);
        expect((row1Buttons[1].data as APIButtonComponentWithCustomId).label).toBe('Misinformed or Misleading');
        expect((row1Buttons[1].data as APIButtonComponentWithCustomId).custom_id).toMatch(/^write_note:MISINFORMED_OR_POTENTIALLY_MISLEADING:[A-Za-z0-9_-]{16}$/);
        expect((row1Buttons[2].data as APIButtonComponentWithCustomId).label).toBe('✨ AI Generate');
        expect((row1Buttons[2].data as APIButtonComponentWithCustomId).custom_id).toMatch(/^ai_write_note:[A-Za-z0-9_-]{16}$/);

        // Third request buttons
        const row2Buttons = result.items[2].buttons[0].components;
        expect(row2Buttons).toHaveLength(3);
        expect((row2Buttons[0].data as APIButtonComponentWithCustomId).label).toBe('Not Misleading');
        expect((row2Buttons[0].data as APIButtonComponentWithCustomId).custom_id).toMatch(/^write_note:NOT_MISLEADING:[A-Za-z0-9_-]{16}$/);
        expect((row2Buttons[1].data as APIButtonComponentWithCustomId).label).toBe('Misinformed or Misleading');
        expect((row2Buttons[1].data as APIButtonComponentWithCustomId).custom_id).toMatch(/^write_note:MISINFORMED_OR_POTENTIALLY_MISLEADING:[A-Za-z0-9_-]{16}$/);
        expect((row2Buttons[2].data as APIButtonComponentWithCustomId).label).toBe('✨ AI Generate');
        expect((row2Buttons[2].data as APIButtonComponentWithCustomId).custom_id).toMatch(/^ai_write_note:[A-Za-z0-9_-]{16}$/);
      });
    });

    describe('general formatting', () => {
      it('should handle empty requests list', async () => {
        const mockResult: ListRequestsResult = {
          requests: [],
          total: 0,
          page: 1,
          size: 10,
        };

        const result = await DiscordFormatter.formatListRequestsSuccess(mockResult);

        expect(result.summary.embed.data.description).toBe('No requests found');
        expect(result.items).toHaveLength(0);
      });

      it('should format request with note_id', async () => {
        const mockResult: ListRequestsResult = {
          requests: [
            createMockRequest({
              note_id: 'note_xyz',
            }),
          ],
          total: 1,
          page: 1,
          size: 10,
        };

        const result = await DiscordFormatter.formatListRequestsSuccess(mockResult);

        const fieldValue = result.items[0].embed.data.description;
        expect(fieldValue).toContain('**Note: note_xyz**');
      });

      it('should format request without note_id', async () => {
        const mockResult: ListRequestsResult = {
          requests: [
            createMockRequest({
              note_id: null,
            }),
          ],
          total: 1,
          page: 1,
          size: 10,
        };

        const result = await DiscordFormatter.formatListRequestsSuccess(mockResult);

        const fieldValue = result.items[0].embed.data.description;
        expect(fieldValue).toContain('**No note yet**');
      });
    });

    describe('content preview formatting (task-506)', () => {
      it('should display text content with "Original message content" label', async () => {
        const mockResult: ListRequestsResult = {
          requests: [
            createMockRequest({
              request_id: 'req_text',
              content: 'This is a text message that should be displayed as preview',
            }),
          ],
          total: 1,
          page: 1,
          size: 10,
        };

        const result = await DiscordFormatter.formatListRequestsSuccess(mockResult);

        const description = result.items[0].embed.data.description;
        expect(description).toContain('**Original message content:** This is a text message that should be displayed as preview');
        expect(description).not.toContain('**Preview:**');
      });

      it('should embed image URL and display link with "Original message content" label', async () => {
        const imageUrl = 'https://example.com/image.jpg';
        const mockResult: ListRequestsResult = {
          requests: [
            createMockRequest({
              request_id: 'req_img',
              content: imageUrl,
            }),
          ],
          total: 1,
          page: 1,
          size: 10,
        };

        const result = await DiscordFormatter.formatListRequestsSuccess(mockResult);

        const embed = result.items[0].embed;
        const description = embed.data.description;

        // Should display the link with "Original message content" label
        expect(description).toContain(`**Original message content:** ${imageUrl}`);
        expect(description).not.toContain('**Preview:**');

        // Should also embed the image
        expect(embed.data.image?.url).toBe(imageUrl);
      });

      it('should detect and embed various image extensions', async () => {
        const imageExtensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp'];

        for (const ext of imageExtensions) {
          const imageUrl = `https://example.com/photo${ext}`;
          const mockResult: ListRequestsResult = {
            requests: [
              createMockRequest({
                request_id: `req_${ext}`,
                content: imageUrl,
              }),
            ],
            total: 1,
            page: 1,
            size: 10,
          };

          const result = await DiscordFormatter.formatListRequestsSuccess(mockResult);
          const embed = result.items[0].embed;

          expect(embed.data.image?.url).toBe(imageUrl);
          expect(embed.data.description).toContain(`**Original message content:** ${imageUrl}`);
        }
      });

      it('should handle image URLs with uppercase extensions', async () => {
        const imageUrl = 'https://example.com/photo.JPG';
        const mockResult: ListRequestsResult = {
          requests: [
            createMockRequest({
              request_id: 'req_upper',
              content: imageUrl,
            }),
          ],
          total: 1,
          page: 1,
          size: 10,
        };

        const result = await DiscordFormatter.formatListRequestsSuccess(mockResult);
        const embed = result.items[0].embed;

        expect(embed.data.image?.url).toBe(imageUrl);
        expect(embed.data.description).toContain(`**Original message content:** ${imageUrl}`);
      });

      it('should display non-image URL as text without embedding', async () => {
        const url = 'https://example.com/article.html';
        const mockResult: ListRequestsResult = {
          requests: [
            createMockRequest({
              request_id: 'req_url',
              content: url,
            }),
          ],
          total: 1,
          page: 1,
          size: 10,
        };

        const result = await DiscordFormatter.formatListRequestsSuccess(mockResult);
        const embed = result.items[0].embed;

        // Should display as text
        expect(embed.data.description).toContain(`**Original message content:** ${url}`);

        // Should NOT embed as image
        expect(embed.data.image).toBeUndefined();
      });

      it('should not display content field when content is null', async () => {
        const mockResult: ListRequestsResult = {
          requests: [
            createMockRequest({
              request_id: 'req_no_content',
              content: null as any,
            }),
          ],
          total: 1,
          page: 1,
          size: 10,
        };

        const result = await DiscordFormatter.formatListRequestsSuccess(mockResult);

        const description = result.items[0].embed.data.description;
        expect(description).not.toContain('**Original message content:**');
        expect(description).not.toContain('**Preview:**');
      });

      it('should not display content field when content is empty string', async () => {
        const mockResult: ListRequestsResult = {
          requests: [
            createMockRequest({
              request_id: 'req_empty',
              content: '   ',
            }),
          ],
          total: 1,
          page: 1,
          size: 10,
        };

        const result = await DiscordFormatter.formatListRequestsSuccess(mockResult);

        const description = result.items[0].embed.data.description;
        expect(description).not.toContain('**Original message content:**');
        expect(description).not.toContain('**Preview:**');
      });

      it('should truncate long text content', async () => {
        const longText = 'A'.repeat(200);
        const mockResult: ListRequestsResult = {
          requests: [
            createMockRequest({
              request_id: 'req_long',
              content: longText,
            }),
          ],
          total: 1,
          page: 1,
          size: 10,
        };

        const result = await DiscordFormatter.formatListRequestsSuccess(mockResult);

        const description = result.items[0].embed.data.description;
        expect(description).toContain('**Original message content:**');
        // Should be truncated to 150 chars + "..."
        expect(description).toContain('A'.repeat(150) + '...');
        expect(description).not.toContain('A'.repeat(151));
      });

      it('should handle image URL with query parameters', async () => {
        const imageUrl = 'https://example.com/image.png?size=large&quality=high';
        const mockResult: ListRequestsResult = {
          requests: [
            createMockRequest({
              request_id: 'req_query',
              content: imageUrl,
            }),
          ],
          total: 1,
          page: 1,
          size: 10,
        };

        const result = await DiscordFormatter.formatListRequestsSuccess(mockResult);
        const embed = result.items[0].embed;

        // Should NOT be detected as image (extension check looks at end of string)
        expect(embed.data.image).toBeUndefined();
        expect(embed.data.description).toContain(`**Original message content:** ${imageUrl}`);
      });
    });
  });
});
