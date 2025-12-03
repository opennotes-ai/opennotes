import { NotesFormatter } from '../../src/lib/notes-formatter.js';
import { NoteWithRatings, RatingThresholds } from '../../src/lib/types.js';
import { MessageInfo } from '../../src/lib/message-fetcher.js';
import { Colors } from 'discord.js';

describe('NotesFormatter', () => {
  const mockThresholds: RatingThresholds = {
    min_ratings_needed: 10,
    min_raters_per_note: 5,
  };

  const mockNote: NoteWithRatings = {
    id: '1',
    author_participant_id: 'author-abc',
    summary: 'This is a test note summary',
    classification: 'MISINFORMATION_OR_ABUSE',
    helpfulness_score: 0.75,
    status: 'NEEDS_MORE_RATINGS',
    created_at: '2025-10-31T12:00:00Z',
    updated_at: '2025-10-31T12:00:00Z',
    ratings_count: 5,
    ratings: [
      {
        id: '1',
        note_id: 'note-123',
        rater_participant_id: 'rater-1',
        helpfulness_level: 'HELPFUL',
        created_at: '2025-10-31T12:00:00Z',
        updated_at: '2025-10-31T12:00:00Z',
      },
      {
        id: '2',
        note_id: 'note-123',
        rater_participant_id: 'rater-2',
        helpfulness_level: 'HELPFUL',
        created_at: '2025-10-31T12:00:00Z',
        updated_at: '2025-10-31T12:00:00Z',
      },
    ],
  };

  describe('calculateProgress', () => {
    it('should return critical urgency for notes with no ratings', () => {
      const noteNoRatings = { ...mockNote, ratings_count: 0, ratings: [] };
      const progress = NotesFormatter.calculateProgress(noteNoRatings, mockThresholds);

      expect(progress.urgencyLevel).toBe('critical');
      expect(progress.urgencyColor).toBe(Colors.Red);
      expect(progress.urgencyEmoji).toBe('🔴');
    });

    it('should return high urgency for notes below half threshold', () => {
      const notePartialRatings = { ...mockNote, ratings_count: 3, ratings: mockNote.ratings };
      const progress = NotesFormatter.calculateProgress(notePartialRatings, mockThresholds);

      expect(progress.urgencyLevel).toBe('high');
      expect(progress.urgencyColor).toBe(Colors.Orange);
      expect(progress.urgencyEmoji).toBe('🟡');
    });

    it('should return medium urgency for notes above half threshold', () => {
      const progress = NotesFormatter.calculateProgress(mockNote, mockThresholds);

      expect(progress.urgencyLevel).toBe('medium');
      expect(progress.urgencyColor).toBe(Colors.Yellow);
      expect(progress.urgencyEmoji).toBe('🟡');
    });

    it('should calculate unique raters correctly', () => {
      const progress = NotesFormatter.calculateProgress(mockNote, mockThresholds);

      expect(progress.raterProgress).toBe('2/5');
    });
  });

  describe('sanitizeMarkdown', () => {
    it('should escape asterisks', () => {
      const noteWithAsterisks = {
        ...mockNote,
        summary: 'Text with *asterisks* for emphasis',
      };
      const embed = NotesFormatter.formatNoteEmbed(noteWithAsterisks, mockThresholds);
      const description = embed.data.description;

      expect(description).toContain('\\*asterisks\\*');
      expect(description).not.toMatch(/(?<!\\)\*asterisks\*(?!\\)/);
    });

    it('should escape underscores', () => {
      const noteWithUnderscores = {
        ...mockNote,
        summary: 'Text with _underscores_ for emphasis',
      };
      const embed = NotesFormatter.formatNoteEmbed(noteWithUnderscores, mockThresholds);
      const description = embed.data.description;

      expect(description).toContain('\\_underscores\\_');
    });

    it('should escape backticks', () => {
      const noteWithBackticks = {
        ...mockNote,
        summary: 'Text with `code` backticks',
      };
      const embed = NotesFormatter.formatNoteEmbed(noteWithBackticks, mockThresholds);
      const description = embed.data.description;

      expect(description).toContain('\\`code\\`');
    });

    it('should escape tildes', () => {
      const noteWithTildes = {
        ...mockNote,
        summary: 'Text with ~strikethrough~',
      };
      const embed = NotesFormatter.formatNoteEmbed(noteWithTildes, mockThresholds);
      const description = embed.data.description;

      expect(description).toContain('\\~strikethrough\\~');
    });

    it('should escape pipes', () => {
      const noteWithPipes = {
        ...mockNote,
        summary: 'Text with || spoiler ||',
      };
      const embed = NotesFormatter.formatNoteEmbed(noteWithPipes, mockThresholds);
      const description = embed.data.description;

      expect(description).toContain('\\|\\|');
    });

    it('should escape angle brackets', () => {
      const noteWithBrackets = {
        ...mockNote,
        summary: 'Text with > quote',
      };
      const embed = NotesFormatter.formatNoteEmbed(noteWithBrackets, mockThresholds);
      const description = embed.data.description;

      expect(description).toContain('\\>');
    });

    it('should escape backslashes', () => {
      const noteWithBackslashes = {
        ...mockNote,
        summary: 'Text with \\ backslash',
      };
      const embed = NotesFormatter.formatNoteEmbed(noteWithBackslashes, mockThresholds);
      const description = embed.data.description;

      expect(description).toContain('\\\\');
    });

    it('should handle multiple special characters', () => {
      const noteWithMultiple = {
        ...mockNote,
        summary: '*bold* _italic_ `code` ~strike~ ||spoiler|| > quote',
      };
      const embed = NotesFormatter.formatNoteEmbed(noteWithMultiple, mockThresholds);
      const description = embed.data.description;

      expect(description).toContain('\\*bold\\*');
      expect(description).toContain('\\_italic\\_');
      expect(description).toContain('\\`code\\`');
      expect(description).toContain('\\~strike\\~');
      expect(description).toContain('\\|\\|spoiler\\|\\|');
      expect(description).toContain('\\>');
    });

    it('should sanitize author participant IDs', () => {
      const noteWithMarkdownAuthor = {
        ...mockNote,
        author_participant_id: 'author_*bold*_italic_',
      };
      const embed = NotesFormatter.formatNoteEmbed(noteWithMarkdownAuthor, mockThresholds);
      const detailsField = embed.data.fields?.find(f => f.name === 'Details');

      expect(detailsField?.value).toContain('author\\_\\*bold\\*\\_italic\\_');
    });

    it('should sanitize original message content from request', () => {
      const noteWithRequest = {
        ...mockNote,
        request: {
          request_id: 'req-123',
          content: 'Message with *markdown* formatting',
          requested_by: 'user-123',
          requested_at: '2025-10-31T12:00:00Z',
        },
      };
      const embed = NotesFormatter.formatNoteEmbed(noteWithRequest, mockThresholds);
      const messageField = embed.data.fields?.find(f => f.name === '💬 Original Message');

      expect(messageField?.value).toContain('\\*markdown\\*');
    });

    it('should sanitize fetched message content and author', () => {
      const mockMessageInfo: MessageInfo = {
        content: 'Fetched message with `code`',
        author: 'User_*Name*',
        url: 'https://discord.com/channels/123/456/789',
      };
      const embed = NotesFormatter.formatNoteEmbed(mockNote, mockThresholds, mockMessageInfo);
      const messageField = embed.data.fields?.find(f => f.name === '💬 Original Message');

      expect(messageField?.value).toContain('\\`code\\`');
      expect(messageField?.value).toContain('User\\_\\*Name\\*');
    });

    it('should prevent XSS via malicious markdown injection', () => {
      const maliciousNote = {
        ...mockNote,
        summary: '**[Click here](javascript:alert("XSS"))**',
      };
      const embed = NotesFormatter.formatNoteEmbed(maliciousNote, mockThresholds);
      const description = embed.data.description;

      expect(description).toContain('\\*\\*');
      expect(description).not.toContain('**[Click here]');
    });

    it('should prevent embed formatting manipulation', () => {
      const manipulativeNote = {
        ...mockNote,
        summary: '```\nFake code block\n```',
      };
      const embed = NotesFormatter.formatNoteEmbed(manipulativeNote, mockThresholds);
      const description = embed.data.description;

      expect(description).toContain('\\`\\`\\`');
      expect(description).not.toContain('```\nFake code block\n```');
    });
  });

  describe('formatQueueEmbed', () => {
    it('should sanitize note summaries in queue', () => {
      const notes = [
        {
          ...mockNote,
          summary: 'Summary with *markdown*',
        },
      ];
      const embed = NotesFormatter.formatQueueEmbed(notes, mockThresholds, 1, 1, 10);
      const noteField = embed.data.fields?.[0];

      expect(noteField?.value).toContain('\\*markdown\\*');
    });

    it('should sanitize message content in queue', () => {
      const notes = [
        {
          ...mockNote,
          request: {
            request_id: 'req-123',
            content: 'Queue message with _formatting_',
            requested_by: 'user-123',
            requested_at: '2025-10-31T12:00:00Z',
          },
        },
      ];
      const embed = NotesFormatter.formatQueueEmbed(notes, mockThresholds, 1, 1, 10);
      const noteField = embed.data.fields?.[0];

      expect(noteField?.value).toContain('\\_formatting\\_');
    });

    it('should sanitize fetched message info in queue', () => {
      const messageInfoMap = new Map<string, MessageInfo | null>();
      messageInfoMap.set('note-123', {
        content: 'Message with ~strikethrough~',
        author: 'Author_*Name*',
        url: 'https://discord.com/channels/123/456/789',
      });

      const noteWithMessageInfo = {
        ...mockNote,
        id: 'note-123',
      };

      const embed = NotesFormatter.formatQueueEmbed([noteWithMessageInfo], mockThresholds, 1, 1, 10, messageInfoMap);
      const noteField = embed.data.fields?.[0];

      expect(noteField?.value).toContain('\\~strikethrough\\~');
      expect(noteField?.value).toContain('Author\\_\\*Name\\*');
    });

    it('should show empty queue message when no notes', () => {
      const embed = NotesFormatter.formatQueueEmbed([], mockThresholds, 1, 0, 10);

      expect(embed.data.description).toContain('No notes need rating');
      expect(embed.data.color).toBe(Colors.Green);
    });
  });

  describe('truncate', () => {
    it('should truncate long text', () => {
      const longNote = {
        ...mockNote,
        summary: 'A'.repeat(300),
      };
      const embed = NotesFormatter.formatNoteEmbed(longNote, mockThresholds);
      const description = embed.data.description;

      expect(description?.length).toBeLessThanOrEqual(203);
      expect(description).toContain('...');
    });

    it('should not truncate short text', () => {
      const shortNote = {
        ...mockNote,
        summary: 'Short summary',
      };
      const embed = NotesFormatter.formatNoteEmbed(shortNote, mockThresholds);
      const description = embed.data.description;

      expect(description).toBe('Short summary');
      expect(description).not.toContain('...');
    });
  });

  describe('formatClassification', () => {
    it('should format classification correctly', () => {
      const embed = NotesFormatter.formatNoteEmbed(mockNote, mockThresholds);
      const detailsField = embed.data.fields?.find(f => f.name === 'Details');

      expect(detailsField?.value).toContain('Misinformation Or Abuse');
    });
  });

  describe('Discord message URL', () => {
    it('should add Discord URL for stored message with guildId and channelId', () => {
      const noteWithStoredMessage = {
        ...mockNote,
        channel_id: 'channel-789',
        request: {
          request_id: 'discord-1234567890-1699012345678',
          content: 'Test message',
          requested_by: 'user-123',
          requested_at: '2025-10-31T12:00:00Z',
        },
      };
      const embed = NotesFormatter.formatNoteEmbed(noteWithStoredMessage, mockThresholds, undefined, 'guild-456');
      const messageField = embed.data.fields?.find(f => f.name === '💬 Original Message');

      expect(messageField?.value).toContain('Test message');
      expect(messageField?.value).toContain('[View Original Message](https://discord.com/channels/guild-456/channel-789/1234567890)');
    });

    it('should not add Discord URL when guildId is missing', () => {
      const noteWithStoredMessage = {
        ...mockNote,
        channel_id: 'channel-789',
        request: {
          request_id: 'req-123',
          content: 'Test message',
          requested_by: 'user-123',
          requested_at: '2025-10-31T12:00:00Z',
        },
      };
      const embed = NotesFormatter.formatNoteEmbed(noteWithStoredMessage, mockThresholds);
      const messageField = embed.data.fields?.find(f => f.name === '💬 Original Message');

      expect(messageField?.value).toContain('Test message');
      expect(messageField?.value).not.toContain('[View Original Message]');
      expect(messageField?.value).not.toContain('https://discord.com');
    });

    it('should not add Discord URL when channelId is missing', () => {
      const noteWithStoredMessage = {
        ...mockNote,
        channel_id: null,
        request: {
          request_id: 'req-123',
          content: 'Test message',
          requested_by: 'user-123',
          requested_at: '2025-10-31T12:00:00Z',
        },
      };
      const embed = NotesFormatter.formatNoteEmbed(noteWithStoredMessage, mockThresholds, undefined, 'guild-456');
      const messageField = embed.data.fields?.find(f => f.name === '💬 Original Message');

      expect(messageField?.value).toContain('Test message');
      expect(messageField?.value).not.toContain('[View Original Message]');
      expect(messageField?.value).not.toContain('https://discord.com');
    });

    it('should not add Discord URL when channelId is undefined', () => {
      const noteWithStoredMessage = {
        ...mockNote,
        request: {
          request_id: 'req-123',
          content: 'Test message',
          requested_by: 'user-123',
          requested_at: '2025-10-31T12:00:00Z',
        },
      };
      const embed = NotesFormatter.formatNoteEmbed(noteWithStoredMessage, mockThresholds, undefined, 'guild-456');
      const messageField = embed.data.fields?.find(f => f.name === '💬 Original Message');

      expect(messageField?.value).toContain('Test message');
      expect(messageField?.value).not.toContain('[View Original Message]');
      expect(messageField?.value).not.toContain('https://discord.com');
    });

    it('should prefer fetched message URL over constructed URL', () => {
      const mockMessageInfo: MessageInfo = {
        content: 'Fetched message',
        author: 'User',
        url: 'https://discord.com/channels/999/888/777',
      };
      const noteWithStoredMessage = {
        ...mockNote,
        channel_id: 'channel-789',
      };
      const embed = NotesFormatter.formatNoteEmbed(noteWithStoredMessage, mockThresholds, mockMessageInfo, 'guild-456');
      const messageField = embed.data.fields?.find(f => f.name === '💬 Original Message');

      expect(messageField?.value).toContain('[View Message](https://discord.com/channels/999/888/777)');
      expect(messageField?.value).not.toContain('guild-456');
    });
  });

  describe('force-published notes', () => {
    it('should show Admin Published indicator for force-published notes in embed', () => {
      const forcePublishedNote = {
        ...mockNote,
        force_published: true,
        force_published_at: '2025-11-08T10:00:00Z',
        force_published_by: 'admin-uuid-123',
      } as any;

      const embed = NotesFormatter.formatNoteEmbed(forcePublishedNote, mockThresholds);

      expect(embed.data.title).toContain('⚠️ Admin Published');
      expect(embed.data.title).toContain(`Note #${mockNote.id}`);
    });

    it('should show normal urgency indicator for non-force-published notes', () => {
      const normalNote = {
        ...mockNote,
        force_published: false,
      } as any;

      const embed = NotesFormatter.formatNoteEmbed(normalNote, mockThresholds);

      expect(embed.data.title).not.toContain('Admin Published');
      expect(embed.data.title).toContain('🟡');
    });

    it('should show Admin Published indicator in queue embed', () => {
      const forcePublishedNote = {
        ...mockNote,
        force_published: true,
      } as any;

      const embed = NotesFormatter.formatQueueEmbed([forcePublishedNote], mockThresholds, 1, 1, 10);

      const fields = embed.data.fields || [];
      expect(fields.length).toBeGreaterThan(0);
      expect(fields[0].name).toBe('⚠️ Admin Published');
    });

    it('should show note number for non-force-published notes in queue', () => {
      const normalNote = {
        ...mockNote,
        force_published: false,
      } as any;

      const embed = NotesFormatter.formatQueueEmbed([normalNote], mockThresholds, 1, 1, 10);

      const fields = embed.data.fields || [];
      expect(fields.length).toBeGreaterThan(0);
      expect(fields[0].name).toContain('Note 1');
      expect(fields[0].name).not.toContain('Admin Published');
    });
  });
});
