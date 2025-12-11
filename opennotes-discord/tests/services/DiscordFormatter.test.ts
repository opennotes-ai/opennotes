import { DiscordFormatter } from '../../src/services/DiscordFormatter.js';
import { ErrorCode, ServiceResult, ListRequestsResult, StatusResult } from '../../src/services/types.js';
import type { NoteScoreResponse, TopNotesResponse, ScoreConfidence, ScoringStatusResponse } from '../../src/services/ScoringService.js';
import { Colors, ButtonStyle, MessageFlags, type APIButtonComponentWithCustomId } from 'discord.js';
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

  describe('formatStatusSuccessV2', () => {
    const createMockStatusResult = (overrides: Partial<StatusResult> = {}): StatusResult => ({
      bot: {
        uptime: 3600,
        cacheSize: 10,
        guilds: 5,
        ...overrides.bot,
      },
      server: {
        status: 'healthy',
        version: '1.0.0',
        latency: 50,
        ...overrides.server,
      },
    });

    it('should return container with v2 message flags', () => {
      const result = DiscordFormatter.formatStatusSuccessV2(createMockStatusResult());

      expect(result.flags & MessageFlags.IsComponentsV2).toBeTruthy();
      expect(result.flags & MessageFlags.Ephemeral).toBeTruthy();
    });

    it('should return components array with container', () => {
      const result = DiscordFormatter.formatStatusSuccessV2(createMockStatusResult());

      expect(result.components).toHaveLength(1);
      expect(result.components[0]).toHaveProperty('type', 17);
    });

    it('should include bot info in container', () => {
      const result = DiscordFormatter.formatStatusSuccessV2(createMockStatusResult({
        bot: { uptime: 7200, cacheSize: 25, guilds: 10 },
      }));

      const container = result.container.toJSON();
      const textComponents = container.components.filter(c => c.type === 10);
      const allContent = textComponents.map(c => (c as { content?: string }).content).join(' ');

      expect(allContent).toContain('2h');
      expect(allContent).toContain('25 entries');
      expect(allContent).toContain('10');
    });

    it('should include server info with status indicator', () => {
      const result = DiscordFormatter.formatStatusSuccessV2(createMockStatusResult({
        server: { status: 'healthy', version: '2.0.0', latency: 100 },
      }));

      const container = result.container.toJSON();
      const textComponents = container.components.filter(c => c.type === 10);
      const allContent = textComponents.map(c => (c as { content?: string }).content).join(' ');

      expect(allContent).toContain('2.0.0');
      expect(allContent).toContain('100ms');
    });

    it('should format uptime correctly for different durations', () => {
      const testCases = [
        { uptime: 0, expected: '0h 0m 0s' },
        { uptime: 3661, expected: '1h 1m 1s' },
        { uptime: 86400, expected: '24h 0m 0s' },
      ];

      for (const { uptime, expected } of testCases) {
        const result = DiscordFormatter.formatStatusSuccessV2(createMockStatusResult({
          bot: { uptime, cacheSize: 0, guilds: 0 },
        }));

        const container = result.container.toJSON();
        const textComponents = container.components.filter(c => c.type === 10);
        const allContent = textComponents.map(c => (c as { content?: string }).content).join(' ');

        expect(allContent).toContain(expected);
      }
    });

    it('should omit guilds when undefined', () => {
      const result = DiscordFormatter.formatStatusSuccessV2(createMockStatusResult({
        bot: { uptime: 3600, cacheSize: 10, guilds: undefined },
      }));

      const container = result.container.toJSON();
      const textComponents = container.components.filter(c => c.type === 10);
      const allContent = textComponents.map(c => (c as { content?: string }).content).join(' ');

      expect(allContent).toContain('Cache Size');
      expect(allContent).not.toContain('Guilds');
    });
  });

  describe('formatScoringStatusV2', () => {
    const createMockScoringStatus = (overrides: Partial<ScoringStatusResponse> = {}): ScoringStatusResponse => ({
      active_tier: { level: 1, name: 'Bootstrap', scorer_components: [] },
      current_note_count: 100,
      data_confidence: 'medium',
      tier_thresholds: {},
      next_tier_upgrade: { tier: 'Growing', notes_needed: 500, notes_to_upgrade: 400 },
      performance_metrics: {
        avg_scoring_time_ms: 10,
        scorer_success_rate: 0.99,
        total_scoring_operations: 1000,
        failed_scoring_operations: 10,
      },
      ...overrides,
    });

    const getTextContent = (textDisplay: ReturnType<typeof DiscordFormatter.formatScoringStatusV2>['textDisplay']): string => {
      return (textDisplay as unknown as { data: { content: string } }).data.content;
    };

    it('should return textDisplay and separator', () => {
      const result = DiscordFormatter.formatScoringStatusV2(createMockScoringStatus());

      expect(result.textDisplay).toBeDefined();
      expect(result.separator).toBeDefined();
    });

    it('should include tier information', () => {
      const result = DiscordFormatter.formatScoringStatusV2(createMockScoringStatus({
        active_tier: { level: 3, name: 'Advanced', scorer_components: [] },
      }));

      const textContent = getTextContent(result.textDisplay);

      expect(textContent).toContain('Current Tier:** 3');
      expect(textContent).toContain('Advanced');
    });

    it('should include note count and confidence', () => {
      const result = DiscordFormatter.formatScoringStatusV2(createMockScoringStatus({
        current_note_count: 250,
        data_confidence: 'high',
      }));

      const textContent = getTextContent(result.textDisplay);

      expect(textContent).toContain('250');
      expect(textContent).toContain('high');
    });

    it('should show progress to next tier when available', () => {
      const result = DiscordFormatter.formatScoringStatusV2(createMockScoringStatus({
        active_tier: { level: 2, name: 'Growing', scorer_components: [] },
        current_note_count: 300,
        next_tier_upgrade: { tier: 'Advanced', notes_needed: 500, notes_to_upgrade: 200 },
      }));

      const textContent = getTextContent(result.textDisplay);

      expect(textContent).toContain('Progress to Tier 3');
      expect(textContent).toContain('300/500');
      expect(textContent).toContain('200 more needed');
    });

    it('should show maximum tier reached when at tier 5', () => {
      const result = DiscordFormatter.formatScoringStatusV2(createMockScoringStatus({
        active_tier: { level: 5, name: 'Maximum', scorer_components: [] },
        next_tier_upgrade: undefined,
      }));

      const textContent = getTextContent(result.textDisplay);

      expect(textContent).toContain('Maximum tier reached');
      expect(textContent).not.toContain('Progress to Tier');
    });
  });

  describe('formatWriteNoteSuccessV2', () => {
    const createMockWriteNoteResult = (): { result: import('../../src/services/types.js').WriteNoteResult; messageId: string; guildId: string; channelId: string } => ({
      result: {
        note: {
          id: '123',
          messageId: 'msg_123',
          content: 'This is a test note content',
          authorId: 'user_456',
          helpfulCount: 0,
          notHelpfulCount: 0,
          createdAt: Date.now(),
        },
      },
      messageId: 'msg_123',
      guildId: 'guild_789',
      channelId: 'channel_012',
    });

    it('should return container with v2 message flags', () => {
      const { result, messageId, guildId, channelId } = createMockWriteNoteResult();
      const formatted = DiscordFormatter.formatWriteNoteSuccessV2(result, messageId, guildId, channelId);

      expect(formatted.flags & MessageFlags.IsComponentsV2).toBeTruthy();
    });

    it('should be non-ephemeral for public success response', () => {
      const { result, messageId, guildId, channelId } = createMockWriteNoteResult();
      const formatted = DiscordFormatter.formatWriteNoteSuccessV2(result, messageId, guildId, channelId);

      expect(formatted.flags & MessageFlags.Ephemeral).toBeFalsy();
    });

    it('should return components array with container', () => {
      const { result, messageId, guildId, channelId } = createMockWriteNoteResult();
      const formatted = DiscordFormatter.formatWriteNoteSuccessV2(result, messageId, guildId, channelId);

      expect(formatted.components).toHaveLength(1);
      expect(formatted.components[0]).toHaveProperty('type', 17);
    });

    it('should include note content in container', () => {
      const { result, messageId, guildId, channelId } = createMockWriteNoteResult();
      const formatted = DiscordFormatter.formatWriteNoteSuccessV2(result, messageId, guildId, channelId);

      const container = formatted.container.toJSON();
      const textComponents = container.components.filter(c => c.type === 10);
      const allContent = textComponents.map(c => (c as { content?: string }).content).join(' ');

      expect(allContent).toContain('This is a test note content');
    });

    it('should include author and note ID metadata', () => {
      const { result, messageId, guildId, channelId } = createMockWriteNoteResult();
      const formatted = DiscordFormatter.formatWriteNoteSuccessV2(result, messageId, guildId, channelId);

      const container = formatted.container.toJSON();
      const textComponents = container.components.filter(c => c.type === 10);
      const allContent = textComponents.map(c => (c as { content?: string }).content).join(' ');

      expect(allContent).toContain('user_456');
      expect(allContent).toContain('123');
    });

    it('should include message link when guildId and channelId provided', () => {
      const { result, messageId, guildId, channelId } = createMockWriteNoteResult();
      const formatted = DiscordFormatter.formatWriteNoteSuccessV2(result, messageId, guildId, channelId);

      const container = formatted.container.toJSON();
      const textComponents = container.components.filter(c => c.type === 10);
      const allContent = textComponents.map(c => (c as { content?: string }).content).join(' ');

      expect(allContent).toContain(`https://discord.com/channels/${guildId}/${channelId}/${messageId}`);
    });

    it('should use success color for container', () => {
      const { result, messageId, guildId, channelId } = createMockWriteNoteResult();
      const formatted = DiscordFormatter.formatWriteNoteSuccessV2(result, messageId, guildId, channelId);

      const container = formatted.container.toJSON();
      expect(container.accent_color).toBe(0x57f287);
    });
  });

  describe('formatViewNotesSuccessV2', () => {
    const createMockViewNotesResult = (noteCount: number = 2): import('../../src/services/types.js').ViewNotesResult => ({
      notes: Array.from({ length: noteCount }, (_, i) => ({
        id: String(100 + i),
        messageId: `msg_${100 + i}`,
        content: `Note content ${i + 1}`,
        authorId: `author_${i}`,
        helpfulCount: i + 1,
        notHelpfulCount: i,
        createdAt: Date.now(),
      })),
    });

    it('should return container with v2 message flags', () => {
      const result = createMockViewNotesResult();
      const formatted = DiscordFormatter.formatViewNotesSuccessV2(result);

      expect(formatted.flags & MessageFlags.IsComponentsV2).toBeTruthy();
    });

    it('should return components array with container', () => {
      const result = createMockViewNotesResult();
      const formatted = DiscordFormatter.formatViewNotesSuccessV2(result);

      expect(formatted.components).toHaveLength(1);
      expect(formatted.components[0]).toHaveProperty('type', 17);
    });

    it('should include text display for each note', () => {
      const result = createMockViewNotesResult(3);
      const formatted = DiscordFormatter.formatViewNotesSuccessV2(result);

      const container = formatted.container.toJSON();
      const textComponents = container.components.filter((c: { type: number }) => c.type === 10);

      expect(textComponents.length).toBeGreaterThanOrEqual(4);
    });

    it('should include note content and ratings', () => {
      const result = createMockViewNotesResult(1);
      const formatted = DiscordFormatter.formatViewNotesSuccessV2(result);

      const container = formatted.container.toJSON();
      const textComponents = container.components.filter(c => c.type === 10);
      const allContent = textComponents.map(c => (c as { content?: string }).content).join(' ');

      expect(allContent).toContain('Note content 1');
    });

    it('should handle empty notes list', () => {
      const result = createMockViewNotesResult(0);
      const formatted = DiscordFormatter.formatViewNotesSuccessV2(result);

      const container = formatted.container.toJSON();
      const textComponents = container.components.filter(c => c.type === 10);
      const allContent = textComponents.map(c => (c as { content?: string }).content).join(' ');

      expect(allContent).toContain('No notes found');
    });

    it('should include score data when provided', () => {
      const result = createMockViewNotesResult(1);
      const scoresMap = new Map<string, NoteScoreResponse>();
      scoresMap.set('100', {
        note_id: '100',
        score: 0.85,
        confidence: 'standard',
        algorithm: 'MFCoreScorer',
        rating_count: 10,
        tier: 2,
        tier_name: 'Tier 2',
        calculated_at: '2025-10-28T12:00:00Z',
      });

      const formatted = DiscordFormatter.formatViewNotesSuccessV2(result, scoresMap);

      const container = formatted.container.toJSON();
      const textComponents = container.components.filter(c => c.type === 10);
      const allContent = textComponents.map(c => (c as { content?: string }).content).join(' ');

      expect(allContent).toContain('0.850');
    });

    it('should include media gallery for image URLs', () => {
      const result = createMockViewNotesResult(1);
      result.notes[0].content = 'https://example.com/image.png';
      const formatted = DiscordFormatter.formatViewNotesSuccessV2(result);

      const container = formatted.container.toJSON();
      const mediaGalleryComponents = container.components.filter((c: { type: number }) => c.type === 12);

      expect(mediaGalleryComponents.length).toBeGreaterThanOrEqual(1);
    });
  });

  describe('formatErrorV2', () => {
    it('should return container with v2 message flags', () => {
      const result: ServiceResult<any> = {
        success: false,
        error: {
          code: ErrorCode.VALIDATION_ERROR,
          message: 'Validation failed',
        },
      };

      const formatted = DiscordFormatter.formatErrorV2(result);

      expect(formatted.flags & MessageFlags.IsComponentsV2).toBeTruthy();
      expect(formatted.flags & MessageFlags.Ephemeral).toBeTruthy();
    });

    it('should return components array with container', () => {
      const result: ServiceResult<any> = {
        success: false,
        error: {
          code: ErrorCode.NOT_FOUND,
          message: 'Resource not found',
        },
      };

      const formatted = DiscordFormatter.formatErrorV2(result);

      expect(formatted.components).toHaveLength(1);
      expect(formatted.components[0]).toHaveProperty('type', 17);
    });

    it('should use error color for container', () => {
      const result: ServiceResult<any> = {
        success: false,
        error: {
          code: ErrorCode.API_ERROR,
          message: 'Server error',
        },
      };

      const formatted = DiscordFormatter.formatErrorV2(result);

      const container = formatted.container.toJSON();
      expect(container.accent_color).toBe(0xed4245);
    });

    it('should include error message in content', () => {
      const result: ServiceResult<any> = {
        success: false,
        error: {
          code: ErrorCode.CONFLICT,
          message: 'Duplicate entry',
          details: {
            helpText: 'Try a different value',
            errorId: 'err_123',
          },
        },
      };

      const formatted = DiscordFormatter.formatErrorV2(result);

      const container = formatted.container.toJSON();
      const textComponents = container.components.filter(c => c.type === 10);
      const allContent = textComponents.map(c => (c as { content?: string }).content).join(' ');

      expect(allContent).toContain('Duplicate entry');
      expect(allContent).toContain('Try a different value');
      expect(allContent).toContain('err_123');
    });

    it('should handle rate limit error with reset time', () => {
      const resetTime = Date.now() + 60000;
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

      const formatted = DiscordFormatter.formatErrorV2(result);

      const container = formatted.container.toJSON();
      const textComponents = container.components.filter(c => c.type === 10);
      const allContent = textComponents.map(c => (c as { content?: string }).content).join(' ');

      expect(allContent).toContain('Rate limit');
    });

    it('should handle error without error object', () => {
      const result: ServiceResult<any> = {
        success: false,
      };

      const formatted = DiscordFormatter.formatErrorV2(result);

      const container = formatted.container.toJSON();
      const textComponents = container.components.filter(c => c.type === 10);
      const allContent = textComponents.map(c => (c as { content?: string }).content).join(' ');

      expect(allContent).toContain('unknown error');
    });
  });

  describe('formatNoteScoreV2', () => {
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

    it('should return container with v2 message flags', () => {
      const formatted = DiscordFormatter.formatNoteScoreV2(mockScoreResponse);

      expect(formatted.flags & MessageFlags.IsComponentsV2).toBeTruthy();
    });

    it('should return components array with container', () => {
      const formatted = DiscordFormatter.formatNoteScoreV2(mockScoreResponse);

      expect(formatted.components).toHaveLength(1);
      expect(formatted.components[0]).toHaveProperty('type', 17);
    });

    it('should use green color for high scores', () => {
      const highScoreResponse = { ...mockScoreResponse, score: 0.85 };
      const formatted = DiscordFormatter.formatNoteScoreV2(highScoreResponse);

      const container = formatted.container.toJSON();
      expect(container.accent_color).toBe(Colors.Green);
    });

    it('should use yellow color for medium scores', () => {
      const mediumScoreResponse = { ...mockScoreResponse, score: 0.55 };
      const formatted = DiscordFormatter.formatNoteScoreV2(mediumScoreResponse);

      const container = formatted.container.toJSON();
      expect(container.accent_color).toBe(Colors.Yellow);
    });

    it('should use red color for low scores', () => {
      const lowScoreResponse = { ...mockScoreResponse, score: 0.25 };
      const formatted = DiscordFormatter.formatNoteScoreV2(lowScoreResponse);

      const container = formatted.container.toJSON();
      expect(container.accent_color).toBe(Colors.Red);
    });

    it('should include score, confidence, and algorithm in content', () => {
      const formatted = DiscordFormatter.formatNoteScoreV2(mockScoreResponse);

      const container = formatted.container.toJSON();
      const textComponents = container.components.filter(c => c.type === 10);
      const allContent = textComponents.map(c => (c as { content?: string }).content).join(' ');

      expect(allContent).toContain('0.750');
      expect(allContent).toContain('Standard');
      expect(allContent).toContain('MFCoreScorer');
    });

    it('should include tier information', () => {
      const formatted = DiscordFormatter.formatNoteScoreV2(mockScoreResponse);

      const container = formatted.container.toJSON();
      const textComponents = container.components.filter(c => c.type === 10);
      const allContent = textComponents.map(c => (c as { content?: string }).content).join(' ');

      expect(allContent).toContain('Tier 2');
    });

    it('should include rating count', () => {
      const formatted = DiscordFormatter.formatNoteScoreV2(mockScoreResponse);

      const container = formatted.container.toJSON();
      const textComponents = container.components.filter(c => c.type === 10);
      const allContent = textComponents.map(c => (c as { content?: string }).content).join(' ');

      expect(allContent).toContain('10');
    });
  });

  describe('formatTopNotesForQueueV2', () => {
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

    it('should return container with v2 message flags', () => {
      const formatted = DiscordFormatter.formatTopNotesForQueueV2(mockTopNotesResponse, 1, 10);

      expect(formatted.flags & MessageFlags.IsComponentsV2).toBeTruthy();
    });

    it('should return components array with container', () => {
      const formatted = DiscordFormatter.formatTopNotesForQueueV2(mockTopNotesResponse, 1, 10);

      expect(formatted.components).toHaveLength(1);
      expect(formatted.components[0]).toHaveProperty('type', 17);
    });

    it('should include ranking indicators for each note', () => {
      const formatted = DiscordFormatter.formatTopNotesForQueueV2(mockTopNotesResponse, 1, 10);

      const container = formatted.container.toJSON();
      const textComponents = container.components.filter(c => c.type === 10);
      const allContent = textComponents.map(c => (c as { content?: string }).content).join(' ');

      expect(allContent).toMatch(/1\./);
      expect(allContent).toMatch(/2\./);
    });

    it('should include score color indicators', () => {
      const formatted = DiscordFormatter.formatTopNotesForQueueV2(mockTopNotesResponse, 1, 10);

      const container = formatted.container.toJSON();
      const textComponents = container.components.filter(c => c.type === 10);
      const allContent = textComponents.map(c => (c as { content?: string }).content).join(' ');

      expect(allContent).toContain('\u{1F7E2}');
    });

    it('should include pagination info in footer', () => {
      const formatted = DiscordFormatter.formatTopNotesForQueueV2(mockTopNotesResponse, 1, 10);

      const container = formatted.container.toJSON();
      const textComponents = container.components.filter(c => c.type === 10);
      const allContent = textComponents.map(c => (c as { content?: string }).content).join(' ');

      expect(allContent).toContain('Page 1');
      expect(allContent).toContain('50');
    });

    it('should handle empty notes list', () => {
      const emptyResponse: TopNotesResponse = {
        notes: [],
        total_count: 0,
        current_tier: 0,
      };
      const formatted = DiscordFormatter.formatTopNotesForQueueV2(emptyResponse, 1, 10);

      const container = formatted.container.toJSON();
      const textComponents = container.components.filter(c => c.type === 10);
      const allContent = textComponents.map(c => (c as { content?: string }).content).join(' ');

      expect(allContent).toContain('No notes found');
    });

    it('should include filters in content when provided', () => {
      const responseWithFilters: TopNotesResponse = {
        ...mockTopNotesResponse,
        filters_applied: {
          min_confidence: 'standard',
          tier: 2,
        },
      };
      const formatted = DiscordFormatter.formatTopNotesForQueueV2(responseWithFilters, 1, 10);

      const container = formatted.container.toJSON();
      const textComponents = container.components.filter(c => c.type === 10);
      const allContent = textComponents.map(c => (c as { content?: string }).content).join(' ');

      expect(allContent).toContain('standard');
      expect(allContent).toContain('2');
    });
  });

  describe('formatListRequestsSuccessV2', () => {
    const createMockListRequestsResult = (requestCount: number = 2): import('../../src/services/types.js').ListRequestsResult => ({
      requests: Array.from({ length: requestCount }, (_, i) => ({
        id: String(100 + i),
        request_id: `discord-123-${i}`,
        requested_by: `user_${i}`,
        requested_at: '2025-10-28T12:00:00Z',
        created_at: '2025-10-28T12:00:00Z',
        status: i === 0 ? 'PENDING' as const : 'COMPLETED' as const,
        note_id: i === 0 ? null : `note_${i}`,
        platform_message_id: `msg_${i}`,
        content: `Test content ${i}`,
        community_server_id: 'guild_123',
      })),
      page: 1,
      size: 10,
      total: requestCount,
    });

    it('should return container with v2 message flags', async () => {
      const result = createMockListRequestsResult();
      const formatted = await DiscordFormatter.formatListRequestsSuccessV2(result);

      expect(formatted.flags & MessageFlags.IsComponentsV2).toBeTruthy();
    });

    it('should return components array with container', async () => {
      const result = createMockListRequestsResult();
      const formatted = await DiscordFormatter.formatListRequestsSuccessV2(result);

      expect(formatted.components).toHaveLength(1);
      expect(formatted.components[0]).toHaveProperty('type', 17);
    });

    it('should include request info in container', async () => {
      const result = createMockListRequestsResult();
      const formatted = await DiscordFormatter.formatListRequestsSuccessV2(result);

      const container = formatted.container.toJSON();
      const textComponents = container.components.filter((c) => c.type === 10);
      const allContent = textComponents.map((c) => (c as { content?: string }).content).join(' ');

      expect(allContent).toContain('discord-123-0');
      expect(allContent).toContain('user_0');
    });

    it('should handle empty requests list', async () => {
      const result = createMockListRequestsResult(0);
      const formatted = await DiscordFormatter.formatListRequestsSuccessV2(result);

      const container = formatted.container.toJSON();
      const textComponents = container.components.filter((c) => c.type === 10);
      const allContent = textComponents.map((c) => (c as { content?: string }).content).join(' ');

      expect(allContent).toContain('No requests found');
    });

    it('should return action rows for pending requests', async () => {
      const result = createMockListRequestsResult(1);
      result.requests[0].status = 'PENDING';
      const formatted = await DiscordFormatter.formatListRequestsSuccessV2(result);

      expect(formatted.actionRows.length).toBeGreaterThan(0);
    });

    it('should not return action rows for non-pending requests', async () => {
      const result = createMockListRequestsResult(1);
      result.requests[0].status = 'COMPLETED';
      const formatted = await DiscordFormatter.formatListRequestsSuccessV2(result);

      expect(formatted.actionRows).toHaveLength(0);
    });

    it('should include content preview when available', async () => {
      const result = createMockListRequestsResult(1);
      result.requests[0].content = 'This is a test message content';
      const formatted = await DiscordFormatter.formatListRequestsSuccessV2(result);

      const container = formatted.container.toJSON();
      const textComponents = container.components.filter((c) => c.type === 10);
      const allContent = textComponents.map((c) => (c as { content?: string }).content).join(' ');

      expect(allContent).toContain('This is a test message content');
    });

    it('should include media gallery for image URLs', async () => {
      const result = createMockListRequestsResult(1);
      result.requests[0].content = 'https://example.com/image.jpg';
      const formatted = await DiscordFormatter.formatListRequestsSuccessV2(result);

      const container = formatted.container.toJSON();
      const mediaGalleryComponents = container.components.filter((c: { type: number }) => c.type === 12);

      expect(mediaGalleryComponents.length).toBeGreaterThanOrEqual(1);
    });
  });

  describe('formatRateNoteSuccessV2', () => {
    const createMockRateNoteResult = (helpful: boolean): { result: import('../../src/services/types.js').RateNoteResult; noteId: string; helpful: boolean } => ({
      result: {
        rating: {
          noteId: 'note_456',
          userId: 'user_789',
          helpful,
          createdAt: Date.now(),
        },
      },
      noteId: 'note_456',
      helpful,
    });

    it('should return container with v2 message flags', () => {
      const { result, noteId, helpful } = createMockRateNoteResult(true);
      const formatted = DiscordFormatter.formatRateNoteSuccessV2(result, noteId, helpful);

      expect(formatted.flags & MessageFlags.IsComponentsV2).toBeTruthy();
    });

    it('should return components array with container', () => {
      const { result, noteId, helpful } = createMockRateNoteResult(true);
      const formatted = DiscordFormatter.formatRateNoteSuccessV2(result, noteId, helpful);

      expect(formatted.components).toHaveLength(1);
      expect(formatted.components[0]).toHaveProperty('type', 17);
    });

    it('should use success color for helpful rating', () => {
      const { result, noteId, helpful } = createMockRateNoteResult(true);
      const formatted = DiscordFormatter.formatRateNoteSuccessV2(result, noteId, helpful);

      const container = formatted.container.toJSON();
      expect(container.accent_color).toBe(0x57f287);
    });

    it('should use critical color for not helpful rating', () => {
      const { result, noteId, helpful } = createMockRateNoteResult(false);
      const formatted = DiscordFormatter.formatRateNoteSuccessV2(result, noteId, helpful);

      const container = formatted.container.toJSON();
      expect(container.accent_color).toBe(0xed4245);
    });

    it('should include rating confirmation text', () => {
      const { result, noteId, helpful } = createMockRateNoteResult(true);
      const formatted = DiscordFormatter.formatRateNoteSuccessV2(result, noteId, helpful);

      const container = formatted.container.toJSON();
      const textComponents = container.components.filter(c => c.type === 10);
      const allContent = textComponents.map(c => (c as { content?: string }).content).join(' ');

      expect(allContent).toContain('Helpful');
      expect(allContent).toContain('note_456');
      expect(allContent).toContain('user_789');
    });

    it('should show Not Helpful text for negative rating', () => {
      const { result, noteId, helpful } = createMockRateNoteResult(false);
      const formatted = DiscordFormatter.formatRateNoteSuccessV2(result, noteId, helpful);

      const container = formatted.container.toJSON();
      const textComponents = container.components.filter(c => c.type === 10);
      const allContent = textComponents.map(c => (c as { content?: string }).content).join(' ');

      expect(allContent).toContain('Not Helpful');
    });
  });

  describe('formatRequestNoteSuccessV2', () => {
    it('should return container with v2 message flags', () => {
      const formatted = DiscordFormatter.formatRequestNoteSuccessV2(
        'msg_123',
        'user_456',
        undefined,
        'guild_789',
        'channel_012'
      );

      expect(formatted.flags & MessageFlags.IsComponentsV2).toBeTruthy();
    });

    it('should return components array with container', () => {
      const formatted = DiscordFormatter.formatRequestNoteSuccessV2(
        'msg_123',
        'user_456',
        undefined,
        'guild_789',
        'channel_012'
      );

      expect(formatted.components).toHaveLength(1);
      expect(formatted.components[0]).toHaveProperty('type', 17);
    });

    it('should use success color for container', () => {
      const formatted = DiscordFormatter.formatRequestNoteSuccessV2(
        'msg_123',
        'user_456',
        undefined,
        'guild_789',
        'channel_012'
      );

      const container = formatted.container.toJSON();
      expect(container.accent_color).toBe(0x57f287);
    });

    it('should include message link when guildId and channelId provided', () => {
      const formatted = DiscordFormatter.formatRequestNoteSuccessV2(
        'msg_123',
        'user_456',
        undefined,
        'guild_789',
        'channel_012'
      );

      const container = formatted.container.toJSON();
      const textComponents = container.components.filter(c => c.type === 10);
      const allContent = textComponents.map(c => (c as { content?: string }).content).join(' ');

      expect(allContent).toContain('https://discord.com/channels/guild_789/channel_012/msg_123');
    });

    it('should include requester information', () => {
      const formatted = DiscordFormatter.formatRequestNoteSuccessV2(
        'msg_123',
        'user_456',
        undefined,
        'guild_789',
        'channel_012'
      );

      const container = formatted.container.toJSON();
      const textComponents = container.components.filter(c => c.type === 10);
      const allContent = textComponents.map(c => (c as { content?: string }).content).join(' ');

      expect(allContent).toContain('user_456');
    });

    it('should include reason when provided', () => {
      const formatted = DiscordFormatter.formatRequestNoteSuccessV2(
        'msg_123',
        'user_456',
        'This message needs verification',
        'guild_789',
        'channel_012'
      );

      const container = formatted.container.toJSON();
      const textComponents = container.components.filter(c => c.type === 10);
      const allContent = textComponents.map(c => (c as { content?: string }).content).join(' ');

      expect(allContent).toContain('This message needs verification');
    });

    it('should not include reason section when not provided', () => {
      const formatted = DiscordFormatter.formatRequestNoteSuccessV2(
        'msg_123',
        'user_456',
        undefined,
        'guild_789',
        'channel_012'
      );

      const container = formatted.container.toJSON();
      const textComponents = container.components.filter(c => c.type === 10);
      const allContent = textComponents.map(c => (c as { content?: string }).content).join(' ');

      expect(allContent).not.toContain('Reason');
    });

    it('should include action row with buttons', () => {
      const formatted = DiscordFormatter.formatRequestNoteSuccessV2(
        'msg_123',
        'user_456',
        undefined,
        'guild_789',
        'channel_012'
      );

      expect(formatted.actionRow).toBeDefined();
      const actionRowJson = formatted.actionRow.toJSON();
      expect(actionRowJson.type).toBe(1);
      expect(actionRowJson.components).toHaveLength(2);

      const containerJson = formatted.container.toJSON();
      const actionRowsInContainer = containerJson.components.filter(c => c.type === 1);
      expect(actionRowsInContainer).toHaveLength(1);
    });

    it('should include "See other requests" button with Secondary style', () => {
      const formatted = DiscordFormatter.formatRequestNoteSuccessV2(
        'msg_123',
        'user_456',
        undefined,
        'guild_789',
        'channel_012'
      );

      const actionRowJson = formatted.actionRow.toJSON();
      const seeRequestsButton = actionRowJson.components.find(
        (c) => 'custom_id' in c && c.custom_id === 'request_reply:list_requests'
      ) as { custom_id: string; label: string; style: number } | undefined;

      expect(seeRequestsButton).toBeDefined();
      expect(seeRequestsButton!.label).toBe('See other requests');
      expect(seeRequestsButton!.style).toBe(2);
    });

    it('should include "Rate some notes" button with Primary style', () => {
      const formatted = DiscordFormatter.formatRequestNoteSuccessV2(
        'msg_123',
        'user_456',
        undefined,
        'guild_789',
        'channel_012'
      );

      const actionRowJson = formatted.actionRow.toJSON();
      const rateNotesButton = actionRowJson.components.find(
        (c) => 'custom_id' in c && c.custom_id === 'request_reply:list_notes'
      ) as { custom_id: string; label: string; style: number } | undefined;

      expect(rateNotesButton).toBeDefined();
      expect(rateNotesButton!.label).toBe('Rate some notes');
      expect(rateNotesButton!.style).toBe(1);
    });
  });
});
