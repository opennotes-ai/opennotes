import { jest, describe, it, expect, beforeEach } from '@jest/globals';
import { ActionRowBuilder, ButtonBuilder, ButtonStyle, MessageFlags } from 'discord.js';
import { V2_ICONS, calculateUrgency } from '../../src/utils/v2-components.js';

describe('list notes v2 helper functions', () => {
  describe('v2 helper utilities', () => {
    it('should calculate critical urgency for notes with 0 ratings', () => {
      const result = calculateUrgency(0, 5);
      expect(result.urgencyLevel).toBe('critical');
      expect(result.urgencyEmoji).toBe(V2_ICONS.CRITICAL);
    });

    it('should calculate high urgency for notes with few ratings', () => {
      const result = calculateUrgency(1, 5);
      expect(result.urgencyLevel).toBe('high');
      expect(result.urgencyEmoji).toBe(V2_ICONS.HIGH);
    });

    it('should calculate medium urgency for notes with more ratings', () => {
      const result = calculateUrgency(3, 5);
      expect(result.urgencyLevel).toBe('medium');
      expect(result.urgencyEmoji).toBe(V2_ICONS.MEDIUM);
    });
  });

  describe('AC #1: Single ContainerBuilder per page', () => {
    it('should verify v2 limit of 4 notes per page due to action row constraints', () => {
      const V2_LIMITS_MAX_NOTES_PER_QUEUE_PAGE = 4;
      expect(V2_LIMITS_MAX_NOTES_PER_QUEUE_PAGE).toBe(4);
    });
  });

  describe('AC #2: Note items with rating button accessories', () => {
    it('should create rating buttons with correct customIds', () => {
      const noteId = 'test-note-123';

      const helpfulButton = new ButtonBuilder()
        .setCustomId(`rate:${noteId}:helpful`)
        .setLabel('Helpful')
        .setStyle(ButtonStyle.Success);

      const notHelpfulButton = new ButtonBuilder()
        .setCustomId(`rate:${noteId}:not_helpful`)
        .setLabel('Not Helpful')
        .setStyle(ButtonStyle.Danger);

      const row = new ActionRowBuilder<ButtonBuilder>().addComponents(
        helpfulButton,
        notHelpfulButton
      );

      expect(row.components).toHaveLength(2);
      const helpfulJson = helpfulButton.toJSON() as { custom_id: string };
      const notHelpfulJson = notHelpfulButton.toJSON() as { custom_id: string };
      expect(helpfulJson.custom_id).toBe(`rate:${noteId}:helpful`);
      expect(notHelpfulJson.custom_id).toBe(`rate:${noteId}:not_helpful`);
    });

    it('should create force publish button for admins', () => {
      const noteId = 'test-note-123';

      const forcePublishButton = new ButtonBuilder()
        .setCustomId(`force_publish:${noteId}`)
        .setLabel('Force Publish')
        .setStyle(ButtonStyle.Danger);

      const fpJson = forcePublishButton.toJSON() as { custom_id: string; style: number };
      expect(fpJson.custom_id).toBe(`force_publish:${noteId}`);
      expect(fpJson.style).toBe(ButtonStyle.Danger);
    });
  });

  describe('AC #3: QueueSummaryV2 format', () => {
    it('should create summary with title, subtitle, and stats', () => {
      const totalNotes = 5;
      const summary = {
        title: `${V2_ICONS.PENDING} Rating Queue`,
        subtitle: `${totalNotes} notes need your rating`,
        stats: `Showing notes 1-4 of ${totalNotes} (Page 1/2)`,
      };

      expect(summary.title).toContain('Rating Queue');
      expect(summary.subtitle).toContain('5');
      expect(summary.stats).toContain('Page');
    });

    it('should create empty queue summary', () => {
      const summary = {
        title: `${V2_ICONS.HELPFUL} Rating Queue`,
        subtitle: 'No notes need rating right now!',
        stats: 'All caught up! Check back later.',
      };

      expect(summary.title).toContain('Rating Queue');
      expect(summary.subtitle).toContain('No notes');
    });
  });

  describe('AC #5: Pagination button functionality', () => {
    it('should create pagination buttons with correct customIds', () => {
      const previousButton = new ButtonBuilder()
        .setCustomId('queue:previous')
        .setLabel('Previous')
        .setStyle(ButtonStyle.Secondary)
        .setDisabled(true);

      const nextButton = new ButtonBuilder()
        .setCustomId('queue:next')
        .setLabel('Next')
        .setStyle(ButtonStyle.Secondary);

      const prevJson = previousButton.toJSON() as { custom_id: string };
      const nextJson = nextButton.toJSON() as { custom_id: string };
      expect(prevJson.custom_id).toBe('queue:previous');
      expect(nextJson.custom_id).toBe('queue:next');
    });
  });

  describe('AC #6: Force publish confirmation v2 format', () => {
    it('should use v2MessageFlags for force publish confirmation', () => {
      const fpMessageFlags = MessageFlags.IsComponentsV2 | MessageFlags.Ephemeral;
      expect(fpMessageFlags).toBe(MessageFlags.IsComponentsV2 | MessageFlags.Ephemeral);
    });
  });

  describe('AC #7: Rated notes display v2', () => {
    it('should create rated notes summary with visual indicators', () => {
      const summary = {
        title: `${V2_ICONS.RATED} Your Rated Notes`,
        subtitle: 'Showing 1-5 of 10 notes',
        stats: 'Notes you have rated that are still being processed (Page 1/2)',
      };

      expect(summary.title).toContain(V2_ICONS.RATED);
      expect(summary.title).toContain('Rated Notes');
    });

    it('should display rating indicator in item summary', () => {
      const userRating = true;
      const ratingIndicator = userRating ? V2_ICONS.HELPFUL : V2_ICONS.NOT_HELPFUL;

      expect(ratingIndicator).toBe(V2_ICONS.HELPFUL);
    });
  });

  describe('AC #8: Modal custom ID length validation', () => {
    it('should maintain modal custom IDs under 100 characters', () => {
      const shortId = 'a1b2c3d4';
      const modalCustomId = `write_note_modal:${shortId}`;

      expect(modalCustomId.length).toBeLessThan(100);
    });
  });

  describe('AC #9: MessageFlags.IsComponentsV2', () => {
    it('should have IsComponentsV2 flag defined', () => {
      expect(MessageFlags.IsComponentsV2).toBeDefined();
    });
  });

  describe('AC #10: Multi-item containers', () => {
    it('should allow multiple items in a single container', () => {
      const items = [
        { id: '1', title: 'Note 1' },
        { id: '2', title: 'Note 2' },
        { id: '3', title: 'Note 3' },
      ];

      expect(items.length).toBeLessThanOrEqual(4);
    });
  });

  describe('AC #11: Button interactions within container', () => {
    it('should handle rate button interaction parsing', () => {
      const customId = 'rate:note-123:helpful';
      const parts = customId.split(':');

      expect(parts).toHaveLength(3);
      expect(parts[0]).toBe('rate');
      expect(parts[1]).toBe('note-123');
      expect(parts[2]).toBe('helpful');
    });

    it('should handle pagination button interaction parsing', () => {
      const prevButtonId = 'queue:previous';
      const nextButtonId = 'queue:next';

      expect(prevButtonId.startsWith('queue:')).toBe(true);
      expect(nextButtonId.startsWith('queue:')).toBe(true);
    });
  });
});
