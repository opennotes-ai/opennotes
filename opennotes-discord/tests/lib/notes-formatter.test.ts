import { NotesFormatter } from '../../src/lib/notes-formatter.js';
import { RatingThresholds } from '../../src/lib/types.js';
import {
  noteWithRatingsFactory,
  ratingResponseFactory,
  requestInfoFactory,
} from '../factories/index.js';

describe('NotesFormatter', () => {
  const mockThresholds: RatingThresholds = {
    min_ratings_needed: 10,
    min_raters_per_note: 5,
  };

  const mockNote = noteWithRatingsFactory.build(
    {
      id: '1',
      author_id: '00000000-0000-0001-aaaa-abc',
      summary: 'This is a test note summary',
      classification: 'MISINFORMATION_OR_ABUSE',
      helpfulness_score: 0.75,
      status: 'NEEDS_MORE_RATINGS',
      created_at: '2025-10-31T12:00:00Z',
      updated_at: '2025-10-31T12:00:00Z',
      ratings_count: 5,
      ratings: [
        ratingResponseFactory.build({
          id: '1',
          note_id: 'note-123',
          rater_id: '00000000-0000-0002-bbbb-1',
          helpfulness_level: 'HELPFUL',
          created_at: '2025-10-31T12:00:00Z',
          updated_at: '2025-10-31T12:00:00Z',
        }),
        ratingResponseFactory.build({
          id: '2',
          note_id: 'note-123',
          rater_id: '00000000-0000-0002-bbbb-2',
          helpfulness_level: 'HELPFUL',
          created_at: '2025-10-31T12:00:00Z',
          updated_at: '2025-10-31T12:00:00Z',
        }),
      ],
    }
  );

  describe('formatStatus', () => {
    it('should format NEEDS_MORE_RATINGS status', () => {
      const status = NotesFormatter.formatStatus('NEEDS_MORE_RATINGS');
      expect(status).toContain('Awaiting More Ratings');
    });

    it('should format CURRENTLY_RATED_HELPFUL status', () => {
      const status = NotesFormatter.formatStatus('CURRENTLY_RATED_HELPFUL');
      expect(status).toContain('Published');
    });

    it('should format CURRENTLY_RATED_NOT_HELPFUL status', () => {
      const status = NotesFormatter.formatStatus('CURRENTLY_RATED_NOT_HELPFUL');
      expect(status).toContain('Not Helpful');
    });
  });

  describe('formatNoteEmbedV2', () => {
    it('should return a ContainerBuilder with urgency-based accent color', () => {
      const container = NotesFormatter.formatNoteEmbedV2(mockNote, mockThresholds);
      const json = container.toJSON();

      expect(json.accent_color).toBeDefined();
      expect(typeof json.accent_color).toBe('number');
    });

    it('should use critical urgency color for notes with no ratings', () => {
      const noteNoRatings = noteWithRatingsFactory.build({
        ...mockNote,
        ratings_count: 0,
        ratings: [],
      });
      const container = NotesFormatter.formatNoteEmbedV2(noteNoRatings, mockThresholds);
      const json = container.toJSON();

      expect(json.accent_color).toBe(0xed4245);
    });

    it('should use high urgency color for notes below half threshold', () => {
      const notePartialRatings = noteWithRatingsFactory.build({
        ...mockNote,
        ratings_count: 3,
      });
      const container = NotesFormatter.formatNoteEmbedV2(notePartialRatings, mockThresholds);
      const json = container.toJSON();

      expect(json.accent_color).toBe(0xffa500);
    });

    it('should use medium urgency color for notes at or above half threshold', () => {
      const container = NotesFormatter.formatNoteEmbedV2(mockNote, mockThresholds);
      const json = container.toJSON();

      expect(json.accent_color).toBe(0xfee75c);
    });

    it('should include note summary in container components', () => {
      const container = NotesFormatter.formatNoteEmbedV2(mockNote, mockThresholds);
      const json = container.toJSON();

      expect(json.components).toBeDefined();
      expect(json.components.length).toBeGreaterThan(0);

      const jsonString = JSON.stringify(json);
      expect(jsonString).toContain(mockNote.summary.replace(/([*_`~|>\\])/g, '\\$1'));
    });

    it('should include author info section', () => {
      const container = NotesFormatter.formatNoteEmbedV2(mockNote, mockThresholds);
      const json = container.toJSON();
      const jsonString = JSON.stringify(json);

      expect(jsonString).toContain('author-abc');
    });

    it('should include visual progress bar', () => {
      const container = NotesFormatter.formatNoteEmbedV2(mockNote, mockThresholds);
      const json = container.toJSON();
      const jsonString = JSON.stringify(json);

      expect(jsonString).toMatch(/\u2588|\u2591/);
    });

    it('should sanitize markdown in note summary', () => {
      const noteWithMarkdown = noteWithRatingsFactory.build({
        ...mockNote,
        summary: 'Text with *bold* and _italic_',
      });
      const container = NotesFormatter.formatNoteEmbedV2(noteWithMarkdown, mockThresholds);
      const jsonString = JSON.stringify(container.toJSON());

      expect(jsonString).toContain('\\\\*bold\\\\*');
      expect(jsonString).toContain('\\\\_italic\\\\_');
    });

    it('should include original message content from request when available', () => {
      const noteWithRequest = noteWithRatingsFactory.build({
        ...mockNote,
        request: requestInfoFactory.build({
          request_id: 'req-123',
          content: 'Original message content',
          requested_by: 'user-123',
          requested_at: '2025-10-31T12:00:00Z',
        }),
      });
      const container = NotesFormatter.formatNoteEmbedV2(noteWithRequest, mockThresholds);
      const jsonString = JSON.stringify(container.toJSON());

      expect(jsonString).toContain('Original message content');
    });

    it('should show Admin Published indicator for force-published notes', () => {
      const forcePublishedNote = noteWithRatingsFactory.build(
        { ...mockNote },
        { transient: { forcePublished: true } }
      );
      const container = NotesFormatter.formatNoteEmbedV2(forcePublishedNote, mockThresholds);
      const jsonString = JSON.stringify(container.toJSON());

      expect(jsonString).toContain('Admin Published');
    });

    it('should include classification type', () => {
      const container = NotesFormatter.formatNoteEmbedV2(mockNote, mockThresholds);
      const jsonString = JSON.stringify(container.toJSON());

      expect(jsonString).toContain('Misinformation Or Abuse');
    });

    it('should include Discord message URL when guildId and channelId are provided', () => {
      const noteWithChannel = noteWithRatingsFactory.build({
        ...mockNote,
        channel_id: 'channel-789',
        request: requestInfoFactory.build({
          request_id: 'discord-1234567890-1699012345678',
          content: 'Test message',
          requested_by: 'user-123',
          requested_at: '2025-10-31T12:00:00Z',
        }),
      });
      const container = NotesFormatter.formatNoteEmbedV2(
        noteWithChannel,
        mockThresholds,
        undefined,
        'guild-456'
      );
      const jsonString = JSON.stringify(container.toJSON());

      expect(jsonString).toContain('https://discord.com/channels/guild-456/channel-789/1234567890');
    });
  });

  describe('formatQueueEmbedV2', () => {
    it('should return a ContainerBuilder for non-empty queue', () => {
      const container = NotesFormatter.formatQueueEmbedV2([mockNote], mockThresholds, 1, 1, 10);
      const json = container.toJSON();

      expect(json.accent_color).toBeDefined();
      expect(json.components).toBeDefined();
    });

    it('should show empty queue message when no notes', () => {
      const container = NotesFormatter.formatQueueEmbedV2([], mockThresholds, 1, 0, 10);
      const jsonString = JSON.stringify(container.toJSON());

      expect(jsonString).toContain('No notes need rating');
    });

    it('should use green color for empty queue', () => {
      const container = NotesFormatter.formatQueueEmbedV2([], mockThresholds, 1, 0, 10);
      const json = container.toJSON();

      expect(json.accent_color).toBe(0x57f287);
    });

    it('should use blue/primary color for non-empty queue', () => {
      const container = NotesFormatter.formatQueueEmbedV2([mockNote], mockThresholds, 1, 1, 10);
      const json = container.toJSON();

      expect(json.accent_color).toBe(0x5865f2);
    });

    it('should show page information in the container', () => {
      const container = NotesFormatter.formatQueueEmbedV2(
        [mockNote, mockNote],
        mockThresholds,
        2,
        15,
        10
      );
      const jsonString = JSON.stringify(container.toJSON());

      expect(jsonString).toContain('Page 2');
    });

    it('should show note count information', () => {
      const container = NotesFormatter.formatQueueEmbedV2([mockNote], mockThresholds, 1, 5, 10);
      const jsonString = JSON.stringify(container.toJSON());

      expect(jsonString).toContain('1');
      expect(jsonString).toContain('5');
    });

    it('should include note summaries in queue items', () => {
      const container = NotesFormatter.formatQueueEmbedV2([mockNote], mockThresholds, 1, 1, 10);
      const jsonString = JSON.stringify(container.toJSON());

      expect(jsonString).toContain(mockNote.summary.replace(/([*_`~|>\\])/g, '\\$1'));
    });

    it('should show Admin Published indicator for force-published notes in queue', () => {
      const forcePublishedNote = noteWithRatingsFactory.build(
        { ...mockNote },
        { transient: { forcePublished: true } }
      );

      const container = NotesFormatter.formatQueueEmbedV2([forcePublishedNote], mockThresholds, 1, 1, 10);
      const jsonString = JSON.stringify(container.toJSON());

      expect(jsonString).toContain('Admin Published');
    });

    it('should include progress bar for each note', () => {
      const container = NotesFormatter.formatQueueEmbedV2([mockNote], mockThresholds, 1, 1, 10);
      const jsonString = JSON.stringify(container.toJSON());

      expect(jsonString).toMatch(/\u2588|\u2591/);
    });

    it('should sanitize message content from request in queue', () => {
      const noteWithMarkdownRequest = noteWithRatingsFactory.build({
        ...mockNote,
        request: requestInfoFactory.build({
          request_id: 'req-123',
          content: 'Message with _formatting_',
          requested_by: 'user-123',
          requested_at: '2025-10-31T12:00:00Z',
        }),
      });
      const container = NotesFormatter.formatQueueEmbedV2([noteWithMarkdownRequest], mockThresholds, 1, 1, 10);
      const jsonString = JSON.stringify(container.toJSON());

      expect(jsonString).toContain('\\\\_formatting\\\\_');
    });
  });

  describe('formatRatedNoteEmbedV2', () => {
    it('should return a ContainerBuilder with rated color', () => {
      const container = NotesFormatter.formatRatedNoteEmbedV2(mockNote, true, mockThresholds);
      const json = container.toJSON();

      expect(json.accent_color).toBe(0x9b59b6);
    });

    it('should show thumbs up indicator for helpful rating', () => {
      const container = NotesFormatter.formatRatedNoteEmbedV2(mockNote, true, mockThresholds);
      const jsonString = JSON.stringify(container.toJSON());

      expect(jsonString).toMatch(/\u{1F44D}|Helpful/u);
    });

    it('should show thumbs down indicator for not helpful rating', () => {
      const container = NotesFormatter.formatRatedNoteEmbedV2(mockNote, false, mockThresholds);
      const jsonString = JSON.stringify(container.toJSON());

      expect(jsonString).toMatch(/\u{1F44E}|Not Helpful/u);
    });

    it('should include current status of the note', () => {
      const container = NotesFormatter.formatRatedNoteEmbedV2(mockNote, true, mockThresholds);
      const jsonString = JSON.stringify(container.toJSON());

      expect(jsonString).toContain('Awaiting More Ratings');
    });

    it('should include rating progress information', () => {
      const container = NotesFormatter.formatRatedNoteEmbedV2(mockNote, true, mockThresholds);
      const jsonString = JSON.stringify(container.toJSON());

      expect(jsonString).toContain('5');
      expect(jsonString).toContain('10');
    });

    it('should include visual progress bar', () => {
      const container = NotesFormatter.formatRatedNoteEmbedV2(mockNote, true, mockThresholds);
      const jsonString = JSON.stringify(container.toJSON());

      expect(jsonString).toMatch(/\u2588|\u2591/);
    });

    it('should include note details section', () => {
      const container = NotesFormatter.formatRatedNoteEmbedV2(mockNote, true, mockThresholds);
      const jsonString = JSON.stringify(container.toJSON());

      expect(jsonString).toContain('author-abc');
      expect(jsonString).toContain('Misinformation Or Abuse');
    });

    it('should include request ID when available', () => {
      const noteWithRequest = noteWithRatingsFactory.build({
        ...mockNote,
        request: requestInfoFactory.build({
          request_id: 'req-123',
          content: 'Test message',
          requested_by: 'user-123',
          requested_at: '2025-10-31T12:00:00Z',
        }),
      });
      const container = NotesFormatter.formatRatedNoteEmbedV2(noteWithRequest, true, mockThresholds);
      const jsonString = JSON.stringify(container.toJSON());

      expect(jsonString).toContain('req-123');
    });

    it('should sanitize note summary', () => {
      const noteWithMarkdown = noteWithRatingsFactory.build({
        ...mockNote,
        summary: 'Summary with *bold* text',
      });
      const container = NotesFormatter.formatRatedNoteEmbedV2(noteWithMarkdown, true, mockThresholds);
      const jsonString = JSON.stringify(container.toJSON());

      expect(jsonString).toContain('\\\\*bold\\\\*');
    });
  });
});
