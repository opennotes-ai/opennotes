import { describe, it, expect } from '@jest/globals';
import { MessageFlags } from 'discord.js';

describe('V2 Components Utilities', () => {
  describe('V2_COLORS', () => {
    it('should export all required urgency colors as valid hex values', async () => {
      const { V2_COLORS } = await import('../../src/utils/v2-components.js');

      const urgencyColors = ['CRITICAL', 'HIGH', 'MEDIUM', 'COMPLETE'] as const;
      for (const color of urgencyColors) {
        expect(V2_COLORS[color]).toBeGreaterThanOrEqual(0x000000);
        expect(V2_COLORS[color]).toBeLessThanOrEqual(0xffffff);
      }
    });

    it('should export all required note status colors as valid hex values', async () => {
      const { V2_COLORS } = await import('../../src/utils/v2-components.js');

      const statusColors = ['HELPFUL', 'NOT_HELPFUL', 'PENDING', 'RATED'] as const;
      for (const color of statusColors) {
        expect(V2_COLORS[color]).toBeGreaterThanOrEqual(0x000000);
        expect(V2_COLORS[color]).toBeLessThanOrEqual(0xffffff);
      }
    });

    it('should export general colors INFO and PRIMARY as valid hex values', async () => {
      const { V2_COLORS } = await import('../../src/utils/v2-components.js');

      expect(V2_COLORS.INFO).toBeGreaterThanOrEqual(0x000000);
      expect(V2_COLORS.INFO).toBeLessThanOrEqual(0xffffff);
      expect(V2_COLORS.PRIMARY).toBeGreaterThanOrEqual(0x000000);
      expect(V2_COLORS.PRIMARY).toBeLessThanOrEqual(0xffffff);
    });
  });

  describe('V2_ICONS', () => {
    it('should export all urgency icons as non-empty strings', async () => {
      const { V2_ICONS } = await import('../../src/utils/v2-components.js');

      const urgencyIcons = ['CRITICAL', 'HIGH', 'MEDIUM', 'COMPLETE'] as const;
      for (const icon of urgencyIcons) {
        expect(typeof V2_ICONS[icon]).toBe('string');
        expect(V2_ICONS[icon].length).toBeGreaterThan(0);
      }
    });

    it('should export all note status icons as non-empty strings', async () => {
      const { V2_ICONS } = await import('../../src/utils/v2-components.js');

      const statusIcons = ['HELPFUL', 'NOT_HELPFUL', 'PENDING', 'RATED'] as const;
      for (const icon of statusIcons) {
        expect(typeof V2_ICONS[icon]).toBe('string');
        expect(V2_ICONS[icon].length).toBeGreaterThan(0);
      }
    });

    it('should export all confidence icons as non-empty strings', async () => {
      const { V2_ICONS } = await import('../../src/utils/v2-components.js');

      const confidenceIcons = ['STANDARD', 'PROVISIONAL', 'NO_DATA'] as const;
      for (const icon of confidenceIcons) {
        expect(typeof V2_ICONS[icon]).toBe('string');
        expect(V2_ICONS[icon].length).toBeGreaterThan(0);
      }
    });
  });

  describe('V2_LIMITS', () => {
    it('should export MAX_COMPONENTS_PER_CONTAINER as a positive integer', async () => {
      const { V2_LIMITS } = await import('../../src/utils/v2-components.js');

      expect(Number.isInteger(V2_LIMITS.MAX_COMPONENTS_PER_CONTAINER)).toBe(true);
      expect(V2_LIMITS.MAX_COMPONENTS_PER_CONTAINER).toBeGreaterThan(0);
    });

    it('should export MAX_TEXT_DISPLAY_LENGTH as a positive integer', async () => {
      const { V2_LIMITS } = await import('../../src/utils/v2-components.js');

      expect(Number.isInteger(V2_LIMITS.MAX_TEXT_DISPLAY_LENGTH)).toBe(true);
      expect(V2_LIMITS.MAX_TEXT_DISPLAY_LENGTH).toBeGreaterThan(0);
    });

    it('should export MAX_ACTION_ROWS as a positive integer', async () => {
      const { V2_LIMITS } = await import('../../src/utils/v2-components.js');

      expect(Number.isInteger(V2_LIMITS.MAX_ACTION_ROWS)).toBe(true);
      expect(V2_LIMITS.MAX_ACTION_ROWS).toBeGreaterThan(0);
    });

    it('should export MAX_NOTES_PER_QUEUE_PAGE as a positive integer', async () => {
      const { V2_LIMITS } = await import('../../src/utils/v2-components.js');

      expect(Number.isInteger(V2_LIMITS.MAX_NOTES_PER_QUEUE_PAGE)).toBe(true);
      expect(V2_LIMITS.MAX_NOTES_PER_QUEUE_PAGE).toBeGreaterThan(0);
    });
  });

  describe('calculateUrgency', () => {
    it('should return critical urgency when ratingCount is 0', async () => {
      const { calculateUrgency, V2_COLORS, V2_ICONS } = await import(
        '../../src/utils/v2-components.js'
      );

      const result = calculateUrgency(0, 5);

      expect(result.urgencyLevel).toBe('critical');
      expect(result.urgencyColor).toBe(V2_COLORS.CRITICAL);
      expect(result.urgencyEmoji).toBe(V2_ICONS.CRITICAL);
    });

    it('should return high urgency when ratingCount is less than half of minRatingsNeeded', async () => {
      const { calculateUrgency, V2_COLORS, V2_ICONS } = await import(
        '../../src/utils/v2-components.js'
      );

      const result = calculateUrgency(1, 5);

      expect(result.urgencyLevel).toBe('high');
      expect(result.urgencyColor).toBe(V2_COLORS.HIGH);
      expect(result.urgencyEmoji).toBe(V2_ICONS.HIGH);
    });

    it('should return medium urgency when ratingCount is at least half of minRatingsNeeded', async () => {
      const { calculateUrgency, V2_COLORS, V2_ICONS } = await import(
        '../../src/utils/v2-components.js'
      );

      const result = calculateUrgency(3, 5);

      expect(result.urgencyLevel).toBe('medium');
      expect(result.urgencyColor).toBe(V2_COLORS.MEDIUM);
      expect(result.urgencyEmoji).toBe(V2_ICONS.MEDIUM);
    });

    it('should handle edge case where minRatingsNeeded is 0', async () => {
      const { calculateUrgency } = await import('../../src/utils/v2-components.js');

      const result = calculateUrgency(0, 0);

      expect(result.urgencyLevel).toBe('critical');
    });

    it('should handle edge case where ratingCount equals minRatingsNeeded', async () => {
      const { calculateUrgency } = await import('../../src/utils/v2-components.js');

      const result = calculateUrgency(5, 5);

      expect(result.urgencyLevel).toBe('medium');
    });
  });

  describe('formatProgress', () => {
    it('should format progress with rating and rater counts', async () => {
      const { formatProgress } = await import('../../src/utils/v2-components.js');

      const result = formatProgress({
        ratingCount: 3,
        ratingTarget: 5,
        raterCount: 2,
        raterTarget: 3,
      });

      expect(result).toContain('3');
      expect(result).toContain('5');
      expect(result).toContain('2');
      expect(result).toContain('3');
      expect(result).toContain('60%');
    });

    it('should handle zero values', async () => {
      const { formatProgress } = await import('../../src/utils/v2-components.js');

      const result = formatProgress({
        ratingCount: 0,
        ratingTarget: 5,
        raterCount: 0,
        raterTarget: 3,
      });

      expect(result).toContain('0');
      expect(result).toContain('0%');
    });

    it('should handle 100% completion', async () => {
      const { formatProgress } = await import('../../src/utils/v2-components.js');

      const result = formatProgress({
        ratingCount: 5,
        ratingTarget: 5,
        raterCount: 3,
        raterTarget: 3,
      });

      expect(result).toContain('100%');
    });
  });

  describe('formatProgressBar', () => {
    it('should return a string with filled and empty blocks', async () => {
      const { formatProgressBar } = await import('../../src/utils/v2-components.js');

      const result = formatProgressBar(5, 10);

      expect(typeof result).toBe('string');
      expect(result).toContain('`');
    });

    it('should show all filled blocks at 100%', async () => {
      const { formatProgressBar } = await import('../../src/utils/v2-components.js');

      const result = formatProgressBar(10, 10, 10);

      expect(result.indexOf('\u2591')).toBe(-1);
    });

    it('should show all empty blocks at 0%', async () => {
      const { formatProgressBar } = await import('../../src/utils/v2-components.js');

      const result = formatProgressBar(0, 10, 10);

      expect(result.indexOf('\u2588')).toBe(-1);
    });

    it('should respect custom width parameter', async () => {
      const { formatProgressBar } = await import('../../src/utils/v2-components.js');

      const result5 = formatProgressBar(5, 10, 5);
      const result20 = formatProgressBar(5, 10, 20);

      expect(result5.length).toBeLessThan(result20.length);
    });
  });

  describe('formatConfidence', () => {
    it('should return standard confidence for 5 or more ratings', async () => {
      const { formatConfidence, V2_ICONS } = await import('../../src/utils/v2-components.js');

      const result = formatConfidence(5);

      expect(result).toContain(V2_ICONS.STANDARD);
      expect(result.toLowerCase()).toContain('standard');
    });

    it('should return provisional confidence for 1-4 ratings', async () => {
      const { formatConfidence, V2_ICONS } = await import('../../src/utils/v2-components.js');

      const result = formatConfidence(3);

      expect(result).toContain(V2_ICONS.PROVISIONAL);
      expect(result.toLowerCase()).toContain('provisional');
    });

    it('should return no data for 0 ratings', async () => {
      const { formatConfidence, V2_ICONS } = await import('../../src/utils/v2-components.js');

      const result = formatConfidence(0);

      expect(result).toContain(V2_ICONS.NO_DATA);
      expect(result.toLowerCase()).toContain('no data');
    });
  });

  describe('sanitizeMarkdown', () => {
    it('should escape markdown special characters', async () => {
      const { sanitizeMarkdown } = await import('../../src/utils/v2-components.js');

      const input = '*bold* _italic_ `code` ~strikethrough~ |spoiler| > quote \\ backslash';
      const result = sanitizeMarkdown(input);

      expect(result).not.toContain('*bold*');
      expect(result).toContain('\\*');
      expect(result).toContain('\\_');
      expect(result).toContain('\\`');
    });

    it('should handle empty strings', async () => {
      const { sanitizeMarkdown } = await import('../../src/utils/v2-components.js');

      const result = sanitizeMarkdown('');

      expect(result).toBe('');
    });

    it('should not modify strings without special characters', async () => {
      const { sanitizeMarkdown } = await import('../../src/utils/v2-components.js');

      const input = 'Hello world 123';
      const result = sanitizeMarkdown(input);

      expect(result).toBe(input);
    });
  });

  describe('truncate', () => {
    it('should not truncate strings shorter than maxLength', async () => {
      const { truncate } = await import('../../src/utils/v2-components.js');

      const input = 'Short string';
      const result = truncate(input, 100);

      expect(result).toBe(input);
    });

    it('should truncate strings longer than maxLength with ellipsis', async () => {
      const { truncate } = await import('../../src/utils/v2-components.js');

      const input = 'This is a very long string that needs to be truncated';
      const result = truncate(input, 20);

      expect(result.length).toBe(20);
      expect(result.endsWith('...')).toBe(true);
    });

    it('should handle strings exactly at maxLength', async () => {
      const { truncate } = await import('../../src/utils/v2-components.js');

      const input = '12345';
      const result = truncate(input, 5);

      expect(result).toBe(input);
    });
  });

  describe('v2MessageFlags', () => {
    it('should return flags with IsComponentsV2 flag set', async () => {
      const { v2MessageFlags } = await import('../../src/utils/v2-components.js');

      const result = v2MessageFlags();

      expect(result & MessageFlags.IsComponentsV2).toBeTruthy();
    });

    it('should combine IsComponentsV2 with Ephemeral flag when requested', async () => {
      const { v2MessageFlags } = await import('../../src/utils/v2-components.js');

      const result = v2MessageFlags({ ephemeral: true });

      expect(result & MessageFlags.IsComponentsV2).toBeTruthy();
      expect(result & MessageFlags.Ephemeral).toBeTruthy();
    });

    it('should only set IsComponentsV2 when ephemeral is false', async () => {
      const { v2MessageFlags } = await import('../../src/utils/v2-components.js');

      const result = v2MessageFlags({ ephemeral: false });

      expect(result & MessageFlags.IsComponentsV2).toBeTruthy();
      expect(result & MessageFlags.Ephemeral).toBeFalsy();
    });
  });

  describe('NoteProgress type', () => {
    it('should have all required fields in calculateUrgency return type', async () => {
      const { calculateUrgency } = await import('../../src/utils/v2-components.js');

      const result = calculateUrgency(0, 5);

      expect(result).toHaveProperty('urgencyLevel');
      expect(result).toHaveProperty('urgencyColor');
      expect(result).toHaveProperty('urgencyEmoji');
      expect(['critical', 'high', 'medium']).toContain(result.urgencyLevel);
    });
  });

  describe('formatProgressBar edge cases', () => {
    it('should throw an error when width is 0', async () => {
      const { formatProgressBar } = await import('../../src/utils/v2-components.js');

      expect(() => formatProgressBar(5, 10, 0)).toThrow('width must be greater than 0');
    });

    it('should throw an error when width is negative', async () => {
      const { formatProgressBar } = await import('../../src/utils/v2-components.js');

      expect(() => formatProgressBar(5, 10, -5)).toThrow('width must be greater than 0');
    });
  });

  describe('truncate edge cases', () => {
    it('should throw an error when maxLength is less than 3', async () => {
      const { truncate } = await import('../../src/utils/v2-components.js');

      expect(() => truncate('Hello', 2)).toThrow('maxLength must be at least 3');
    });

    it('should handle maxLength of exactly 3', async () => {
      const { truncate } = await import('../../src/utils/v2-components.js');

      const result = truncate('Hello', 3);

      expect(result).toBe('...');
      expect(result.length).toBe(3);
    });

    it('should handle maxLength of 4 correctly', async () => {
      const { truncate } = await import('../../src/utils/v2-components.js');

      const result = truncate('Hello', 4);

      expect(result).toBe('H...');
      expect(result.length).toBe(4);
    });
  });

  describe('createSmallSeparator', () => {
    it('should create a SeparatorBuilder with small spacing', async () => {
      const { createSmallSeparator } = await import('../../src/utils/v2-components.js');
      const { SeparatorSpacingSize } = await import('discord.js');

      const separator = createSmallSeparator();
      const json = separator.toJSON();

      expect(json.spacing).toBe(SeparatorSpacingSize.Small);
      expect(json.divider).toBeFalsy();
    });
  });

  describe('createDivider', () => {
    it('should create a SeparatorBuilder with divider set to true', async () => {
      const { createDivider } = await import('../../src/utils/v2-components.js');

      const separator = createDivider();
      const json = separator.toJSON();

      expect(json.divider).toBe(true);
    });
  });

  describe('createContainer', () => {
    it('should create a ContainerBuilder with accent color', async () => {
      const { createContainer, V2_COLORS } = await import('../../src/utils/v2-components.js');

      const container = createContainer(V2_COLORS.CRITICAL);
      const json = container.toJSON();

      expect(json.accent_color).toBe(V2_COLORS.CRITICAL);
    });

    it('should create a ContainerBuilder with custom accent color', async () => {
      const { createContainer } = await import('../../src/utils/v2-components.js');

      const container = createContainer(0x123456);
      const json = container.toJSON();

      expect(json.accent_color).toBe(0x123456);
    });
  });

  describe('createTextSection', () => {
    it('should create a TextDisplayBuilder with text content', async () => {
      const { createTextSection } = await import('../../src/utils/v2-components.js');
      const { TextDisplayBuilder } = await import('discord.js');

      const textDisplay = createTextSection('Hello World');

      expect(textDisplay).toBeInstanceOf(TextDisplayBuilder);
      const componentJson = textDisplay.toJSON() as { content?: string };
      expect(componentJson.content).toBe('Hello World');
    });

    it('should support markdown content', async () => {
      const { createTextSection } = await import('../../src/utils/v2-components.js');

      const textDisplay = createTextSection('**Bold** and _italic_');

      const componentJson = textDisplay.toJSON() as { content?: string };
      expect(componentJson.content).toBe('**Bold** and _italic_');
    });
  });

  describe('createTextWithButton', () => {
    it('should create a SectionBuilder with text and button accessory', async () => {
      const { createTextWithButton } = await import('../../src/utils/v2-components.js');
      const { ButtonBuilder, ButtonStyle } = await import('discord.js');

      const button = new ButtonBuilder()
        .setCustomId('test-button')
        .setLabel('Click Me')
        .setStyle(ButtonStyle.Primary);

      const section = createTextWithButton('Click the button!', button);
      const json = section.toJSON();

      expect(json.components).toBeDefined();
      expect(json.components[0].content).toBe('Click the button!');
      expect(json.accessory).toBeDefined();
      expect((json.accessory as { custom_id?: string }).custom_id).toBe('test-button');
    });
  });

  describe('createTextWithThumbnail', () => {
    it('should create a SectionBuilder with text and thumbnail accessory', async () => {
      const { createTextWithThumbnail } = await import('../../src/utils/v2-components.js');

      const section = createTextWithThumbnail('Image description', 'https://example.com/image.png');
      const json = section.toJSON();

      expect(json.components).toBeDefined();
      expect(json.components[0].content).toBe('Image description');
      expect(json.accessory).toBeDefined();
      expect((json.accessory as { media?: { url?: string } }).media?.url).toBe('https://example.com/image.png');
    });
  });

  describe('formatStatusIndicator', () => {
    it('should return healthy indicator with checkmark for true status', async () => {
      const { formatStatusIndicator, V2_ICONS } = await import('../../src/utils/v2-components.js');

      const result = formatStatusIndicator(true, 'API');

      expect(result).toContain(V2_ICONS.HELPFUL);
      expect(result).toContain('API');
    });

    it('should return unhealthy indicator with X for false status', async () => {
      const { formatStatusIndicator, V2_ICONS } = await import('../../src/utils/v2-components.js');

      const result = formatStatusIndicator(false, 'Database');

      expect(result).toContain(V2_ICONS.NOT_HELPFUL);
      expect(result).toContain('Database');
    });

    it('should preserve the label text exactly', async () => {
      const { formatStatusIndicator } = await import('../../src/utils/v2-components.js');

      const result = formatStatusIndicator(true, 'Connection: Active');

      expect(result).toContain('Connection: Active');
    });
  });

  describe('isImageUrl', () => {
    it('should return true for PNG URLs', async () => {
      const { isImageUrl } = await import('../../src/utils/v2-components.js');
      expect(isImageUrl('https://example.com/image.png')).toBe(true);
    });

    it('should return true for JPG URLs', async () => {
      const { isImageUrl } = await import('../../src/utils/v2-components.js');
      expect(isImageUrl('https://example.com/image.jpg')).toBe(true);
    });

    it('should return true for JPEG URLs', async () => {
      const { isImageUrl } = await import('../../src/utils/v2-components.js');
      expect(isImageUrl('https://example.com/image.jpeg')).toBe(true);
    });

    it('should return true for GIF URLs', async () => {
      const { isImageUrl } = await import('../../src/utils/v2-components.js');
      expect(isImageUrl('https://example.com/image.gif')).toBe(true);
    });

    it('should return true for WEBP URLs', async () => {
      const { isImageUrl } = await import('../../src/utils/v2-components.js');
      expect(isImageUrl('https://example.com/image.webp')).toBe(true);
    });

    it('should return true for image URLs with query parameters', async () => {
      const { isImageUrl } = await import('../../src/utils/v2-components.js');
      expect(isImageUrl('https://example.com/image.png?size=large')).toBe(true);
    });

    it('should return false for non-image URLs', async () => {
      const { isImageUrl } = await import('../../src/utils/v2-components.js');
      expect(isImageUrl('https://example.com/page.html')).toBe(false);
    });

    it('should return false for non-URL strings', async () => {
      const { isImageUrl } = await import('../../src/utils/v2-components.js');
      expect(isImageUrl('not a url')).toBe(false);
    });
  });

  describe('createMediaGallery', () => {
    it('should return undefined for empty array', async () => {
      const { createMediaGallery } = await import('../../src/utils/v2-components.js');
      expect(createMediaGallery([])).toBeUndefined();
    });

    it('should return undefined for array with no valid image URLs', async () => {
      const { createMediaGallery } = await import('../../src/utils/v2-components.js');
      expect(createMediaGallery(['https://example.com/page.html'])).toBeUndefined();
    });

    it('should create gallery with valid image URLs', async () => {
      const { createMediaGallery } = await import('../../src/utils/v2-components.js');
      const { MediaGalleryBuilder } = await import('discord.js');
      const gallery = createMediaGallery(['https://example.com/image.png']);

      expect(gallery).toBeInstanceOf(MediaGalleryBuilder);
    });

    it('should filter out invalid URLs', async () => {
      const { createMediaGallery } = await import('../../src/utils/v2-components.js');
      const gallery = createMediaGallery([
        'https://example.com/image.png',
        'not a url',
        'https://example.com/image2.jpg'
      ]);

      expect(gallery).toBeDefined();
      const json = gallery!.toJSON();
      expect(json.items).toHaveLength(2);
    });

    it('should limit to max images', async () => {
      const { createMediaGallery } = await import('../../src/utils/v2-components.js');
      const urls = Array.from({ length: 15 }, (_, i) => `https://example.com/image${i}.png`);
      const gallery = createMediaGallery(urls, 5);

      expect(gallery).toBeDefined();
      const json = gallery!.toJSON();
      expect(json.items).toHaveLength(5);
    });
  });
});
