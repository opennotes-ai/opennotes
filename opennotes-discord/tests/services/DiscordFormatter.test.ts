import { DiscordFormatter } from '../../src/services/DiscordFormatter.js';
import { ErrorCode, ServiceResult, ListRequestsResult, StatusResult } from '../../src/services/types.js';
import type { TopNotesJSONAPIResponse, ScoringStatusJSONAPIResponse, ScoreConfidence, NoteScoreAttributes, NoteScoreJSONAPIResponse } from '../../src/services/ScoringService.js';
import { Colors, ButtonStyle, MessageFlags, type APIButtonComponentWithCustomId } from 'discord.js';
import type { RequestItem } from '../../src/lib/types.js';
import { TEST_SCORE_ABOVE_THRESHOLD } from '../test-constants.js';

describe('DiscordFormatter', () => {
  describe('score formatting utilities', () => {
    describe('getConfidenceEmoji', () => {
      it.each(['standard', 'provisional', 'no_data'] as const)(
        'should return a non-empty emoji for %s confidence',
        (confidence) => {
          const emoji = DiscordFormatter.getConfidenceEmoji(confidence);
          expect(emoji).toBeTruthy();
          expect(emoji.length).toBeGreaterThan(0);
        }
      );

      it('should return a non-empty emoji for unknown confidence', () => {
        const emoji = DiscordFormatter.getConfidenceEmoji('unknown' as ScoreConfidence);
        expect(emoji).toBeTruthy();
      });
    });

    describe('getConfidenceLabel', () => {
      it.each(['standard', 'provisional', 'no_data'] as const)(
        'should return a non-empty label for %s confidence',
        (confidence) => {
          const label = DiscordFormatter.getConfidenceLabel(confidence);
          expect(label).toBeTruthy();
          expect(label).toMatch(/\w+/);
        }
      );
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
    const createMockScoringStatus = (overrides: Partial<ScoringStatusJSONAPIResponse['data']['attributes']> = {}): ScoringStatusJSONAPIResponse => ({
      data: {
        type: 'scoring_status',
        id: 'status',
        attributes: {
          active_tier: { level: 1, name: 'Bootstrap', scorer_components: [] },
          current_note_count: 100,
          data_confidence: 'provisional',
          tier_thresholds: {},
          next_tier_upgrade: { tier: 'Growing', notes_needed: 500, notes_to_upgrade: 400 },
          performance_metrics: {
            avg_scoring_time_ms: 10,
            scorer_success_rate: 0.99,
            total_scoring_operations: 1000,
            failed_scoring_operations: 10,
          },
          warnings: [],
          configuration: {},
          ...overrides,
        },
      },
      jsonapi: { version: '1.1' },
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
        data_confidence: 'standard',
      }));

      const textContent = getTextContent(result.textDisplay);

      expect(textContent).toContain('250');
      expect(textContent).toContain('standard');
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
          data: {
            type: 'notes',
            id: '123',
            attributes: {
              summary: 'This is a test note content',
              classification: 'NOT_MISLEADING',
              status: 'NEEDS_MORE_RATINGS',
              helpfulness_score: 0,
              author_id: 'user_456',
              community_server_id: 'guild_789',
              channel_id: 'channel_012',
              request_id: null,
              ratings_count: 0,
              force_published: false,
              force_published_at: null,
              ai_generated: false,
              ai_provider: null,
              created_at: new Date().toISOString(),
              updated_at: null,
            },
          },
          jsonapi: { version: '1.1' },
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
      notes: {
        data: Array.from({ length: noteCount }, (_, i) => ({
          type: 'notes' as const,
          id: String(100 + i),
          attributes: {
            summary: `Note content ${i + 1}`,
            classification: 'NOT_MISLEADING' as const,
            status: 'NEEDS_MORE_RATINGS' as const,
            helpfulness_score: 0,
            author_id: `author_${i}`,
            community_server_id: 'server_123',
            channel_id: null,
            request_id: null,
            ratings_count: i + 1,
            force_published: false,
            force_published_at: null,
            created_at: new Date().toISOString(),
            updated_at: null,
          },
        })),
        jsonapi: { version: '1.1' as const },
      },
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
      const scoresMap = new Map<string, NoteScoreAttributes>();
      scoresMap.set('100', {
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
      result.notes.data[0].attributes.summary = 'https://example.com/image.png';
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
    const createMockScoreResponse = (overrides: Partial<NoteScoreAttributes> = {}): NoteScoreJSONAPIResponse => ({
      data: {
        type: 'note_score',
        id: '123',
        attributes: {
          score: 0.75,
          confidence: 'standard',
          algorithm: 'MFCoreScorer',
          rating_count: 10,
          tier: 2,
          tier_name: 'Tier 2 (1k-5k notes)',
          calculated_at: '2025-10-28T12:00:00Z',
          ...overrides,
        },
      },
      jsonapi: { version: '1.1' },
    });

    it('should return container with v2 message flags', () => {
      const formatted = DiscordFormatter.formatNoteScoreV2(createMockScoreResponse());

      expect(formatted.flags & MessageFlags.IsComponentsV2).toBeTruthy();
    });

    it('should return components array with container', () => {
      const formatted = DiscordFormatter.formatNoteScoreV2(createMockScoreResponse());

      expect(formatted.components).toHaveLength(1);
      expect(formatted.components[0]).toHaveProperty('type', 17);
    });

    it('should use green color for high scores', () => {
      const formatted = DiscordFormatter.formatNoteScoreV2(createMockScoreResponse({ score: 0.85 }));

      const container = formatted.container.toJSON();
      expect(container.accent_color).toBe(Colors.Green);
    });

    it('should use yellow color for medium scores', () => {
      const formatted = DiscordFormatter.formatNoteScoreV2(createMockScoreResponse({ score: 0.55 }));

      const container = formatted.container.toJSON();
      expect(container.accent_color).toBe(Colors.Yellow);
    });

    it('should use red color for low scores', () => {
      const formatted = DiscordFormatter.formatNoteScoreV2(createMockScoreResponse({ score: 0.25 }));

      const container = formatted.container.toJSON();
      expect(container.accent_color).toBe(Colors.Red);
    });

    it('should include score, confidence, and algorithm in content', () => {
      const formatted = DiscordFormatter.formatNoteScoreV2(createMockScoreResponse());

      const container = formatted.container.toJSON();
      const textComponents = container.components.filter(c => c.type === 10);
      const allContent = textComponents.map(c => (c as { content?: string }).content).join(' ');

      expect(allContent).toContain('0.750');
      expect(allContent).toContain('Standard');
      expect(allContent).toContain('MFCoreScorer');
    });

    it('should include tier information', () => {
      const formatted = DiscordFormatter.formatNoteScoreV2(createMockScoreResponse());

      const container = formatted.container.toJSON();
      const textComponents = container.components.filter(c => c.type === 10);
      const allContent = textComponents.map(c => (c as { content?: string }).content).join(' ');

      expect(allContent).toContain('Tier 2');
    });

    it('should include rating count', () => {
      const formatted = DiscordFormatter.formatNoteScoreV2(createMockScoreResponse());

      const container = formatted.container.toJSON();
      const textComponents = container.components.filter(c => c.type === 10);
      const allContent = textComponents.map(c => (c as { content?: string }).content).join(' ');

      expect(allContent).toContain('10');
    });
  });

  describe('formatTopNotesForQueueV2', () => {
    const mockTopNotesResponse: TopNotesJSONAPIResponse = {
      data: [
        {
          type: 'note_score',
          id: '123',
          attributes: {
            score: TEST_SCORE_ABOVE_THRESHOLD,
            confidence: 'standard',
            algorithm: 'MFCoreScorer',
            rating_count: 15,
            tier: 2,
            tier_name: 'Tier 2',
            calculated_at: '2025-10-28T12:00:00Z',
          },
        },
        {
          type: 'note_score',
          id: '456',
          attributes: {
            score: 0.72,
            confidence: 'standard',
            algorithm: 'MFCoreScorer',
            rating_count: 12,
            tier: 2,
            tier_name: 'Tier 2',
            calculated_at: '2025-10-28T12:00:00Z',
          },
        },
      ],
      meta: {
        total_count: 50,
        current_tier: 2,
      },
      jsonapi: { version: '1.1' },
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
      const emptyResponse: TopNotesJSONAPIResponse = {
        data: [],
        meta: {
          total_count: 0,
          current_tier: 0,
        },
        jsonapi: { version: '1.1' },
      };
      const formatted = DiscordFormatter.formatTopNotesForQueueV2(emptyResponse, 1, 10);

      const container = formatted.container.toJSON();
      const textComponents = container.components.filter(c => c.type === 10);
      const allContent = textComponents.map(c => (c as { content?: string }).content).join(' ');

      expect(allContent).toContain('No notes found');
    });

    it('should include filters in content when provided', () => {
      const responseWithFilters: TopNotesJSONAPIResponse = {
        ...mockTopNotesResponse,
        meta: {
          ...mockTopNotesResponse.meta,
          filters_applied: {
            min_confidence: 'standard',
            tier: 2,
          },
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

    it('should embed action rows in container for pending requests', async () => {
      const result = createMockListRequestsResult(1);
      result.requests[0].status = 'PENDING';
      const formatted = await DiscordFormatter.formatListRequestsSuccessV2(result);

      const container = formatted.container.toJSON();
      const actionRowComponents = container.components.filter((c: { type: number }) => c.type === 1);
      expect(actionRowComponents.length).toBeGreaterThan(0);
      expect(formatted.actionRows).toHaveLength(0);
    });

    it('should not have action rows for non-pending requests', async () => {
      const result = createMockListRequestsResult(1);
      result.requests[0].status = 'COMPLETED';
      const formatted = await DiscordFormatter.formatListRequestsSuccessV2(result);

      const container = formatted.container.toJSON();
      const actionRowComponents = container.components.filter((c: { type: number }) => c.type === 1);
      expect(actionRowComponents).toHaveLength(0);
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

    it('should embed action rows inside container for pending requests', async () => {
      const result = createMockListRequestsResult(1);
      result.requests[0].status = 'PENDING';
      const formatted = await DiscordFormatter.formatListRequestsSuccessV2(result);

      const container = formatted.container.toJSON();
      const actionRowComponents = container.components.filter((c: { type: number }) => c.type === 1);

      expect(actionRowComponents.length).toBeGreaterThan(0);
    });

    it('should place action row immediately after its associated request entry', async () => {
      const result = createMockListRequestsResult(2);
      result.requests[0].status = 'PENDING';
      result.requests[1].status = 'PENDING';
      const formatted = await DiscordFormatter.formatListRequestsSuccessV2(result);

      const container = formatted.container.toJSON();
      const components = container.components;

      let requestTextIndices: number[] = [];
      let actionRowIndices: number[] = [];

      components.forEach((c: { type: number; content?: string }, idx: number) => {
        if (c.type === 10 && c.content?.includes('discord-123-')) {
          requestTextIndices.push(idx);
        }
        if (c.type === 1) {
          actionRowIndices.push(idx);
        }
      });

      expect(actionRowIndices.length).toBe(2);
      actionRowIndices.forEach((arIdx, i) => {
        const requestIdx = requestTextIndices[i];
        expect(arIdx).toBeGreaterThan(requestIdx);
        const nextRequestIdx = requestTextIndices[i + 1];
        if (nextRequestIdx !== undefined) {
          expect(arIdx).toBeLessThan(nextRequestIdx);
        }
      });
    });

    it('should not return separate actionRows array when rows are embedded', async () => {
      const result = createMockListRequestsResult(1);
      result.requests[0].status = 'PENDING';
      const formatted = await DiscordFormatter.formatListRequestsSuccessV2(result);

      expect(formatted.actionRows).toHaveLength(0);
    });
  });

  describe('formatRateNoteSuccessV2', () => {
    const createMockRateNoteResult = (helpful: boolean): { result: import('../../src/services/types.js').RateNoteResult; noteId: string; helpful: boolean } => ({
      result: {
        rating: {
          data: {
            type: 'ratings',
            id: 'rating-123',
            attributes: {
              note_id: 'note_456',
              rater_id: 'user_789',
              helpfulness_level: helpful ? 'HELPFUL' : 'NOT_HELPFUL',
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
            },
          },
          jsonapi: { version: '1.1' },
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
