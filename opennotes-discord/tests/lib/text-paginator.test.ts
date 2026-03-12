import { describe, it, expect } from '@jest/globals';
import { TextPaginator } from '../../src/lib/text-paginator.js';

describe('TextPaginator', () => {
  const paginatorInternals = TextPaginator as unknown as {
    findUnclosedFence(content: string): unknown;
    splitPage(content: string, maxChars: number): { page: string; remainingContent: string };
  };

  describe('paginate', () => {
    it('returns single page for content under limit', () => {
      const content = 'Short content that fits easily.';
      const result = TextPaginator.paginate(content);

      expect(result.pages).toHaveLength(1);
      expect(result.pages[0]).toBe(content);
      expect(result.totalPages).toBe(1);
    });

    it('returns single page for empty content', () => {
      const result = TextPaginator.paginate('');

      expect(result.pages).toHaveLength(1);
      expect(result.pages[0]).toBe('');
      expect(result.totalPages).toBe(1);
    });

    it('splits content at line boundaries when exceeding limit', () => {
      const lines = Array.from({ length: 50 }, (_, i) => `Line ${i + 1}: This is some content that takes up space.`);
      const content = lines.join('\n');

      const result = TextPaginator.paginate(content, { maxCharsPerPage: 500 });

      expect(result.totalPages).toBeGreaterThan(1);
      result.pages.forEach((page, index) => {
        expect(page.length).toBeLessThanOrEqual(500);
        if (index < result.pages.length - 1) {
          expect(page.endsWith('\n') || !page.includes('\n')).toBe(true);
        }
      });
    });

    it('handles content with no line breaks by splitting at maxCharsPerPage', () => {
      const content = 'A'.repeat(500);
      const result = TextPaginator.paginate(content, { maxCharsPerPage: 100 });

      expect(result.totalPages).toBe(5);
      result.pages.forEach(page => {
        expect(page.length).toBeLessThanOrEqual(100);
      });
    });

    it('uses default maxCharsPerPage of 1900', () => {
      const content = 'A'.repeat(4000);
      const result = TextPaginator.paginate(content);

      expect(result.totalPages).toBe(3);
      expect(result.pages[0].length).toBe(1900);
      expect(result.pages[1].length).toBe(1900);
      expect(result.pages[2].length).toBe(200);
    });

    it('handles unicode/emoji content correctly', () => {
      const emojis = '🎉🚀💡🔥⭐';
      const content = emojis.repeat(100);
      const result = TextPaginator.paginate(content, { maxCharsPerPage: 50 });

      expect(result.totalPages).toBeGreaterThan(1);
      const totalChars = result.pages.join('').length;
      expect(totalChars).toBe(content.length);
    });

    it('preserves complete lines when possible', () => {
      const content = 'Line 1\nLine 2\nLine 3\nLine 4\nLine 5';
      const result = TextPaginator.paginate(content, { maxCharsPerPage: 20 });

      result.pages.forEach(page => {
        const trimmed = page.trim();
        if (trimmed.length > 0) {
          expect(trimmed.startsWith('Line')).toBe(true);
        }
      });
    });

    it('adds page indicator when requested', () => {
      const content = 'A'.repeat(200);
      const result = TextPaginator.paginate(content, {
        maxCharsPerPage: 100,
        addPageIndicator: true
      });

      expect(result.pages[0]).toContain('(1/');
      expect(result.pages[1]).toContain('(2/');
    });

    it('preserves fenced markdown integrity across paginated pages', () => {
      const fencedBody = Array.from(
        { length: 40 },
        (_, index) => `const line${index} = ${index};`
      ).join('\n');
      const content = ['Request details:', '', '```ts', fencedBody, '```', '', 'Done.'].join('\n');

      const result = TextPaginator.paginate(content, { maxCharsPerPage: 180 });

      expect(result.totalPages).toBeGreaterThan(1);
      result.pages.forEach(page => {
        expect((page.match(/```/g)?.length ?? 0) % 2).toBe(0);
      });
      expect(result.pages.join('\n')).toContain('const line39 = 39;');
      expect(result.pages.at(-1)).toContain('Done.');
    });

    it('keeps quoted fenced blocks balanced across paginated pages', () => {
      const quotedFenceBody = Array.from(
        { length: 10 },
        (_, index) => `> const quotedLine${index} = ${index};`
      ).join('\n');
      const content = [
        '> Request details:',
        '>',
        '> ```ts',
        quotedFenceBody,
        '> ```',
        '>',
        '> Follow-up context after the quoted block.',
      ].join('\n');

      const result = TextPaginator.paginate(content, { maxCharsPerPage: 120 });

      expect(result.totalPages).toBeGreaterThan(1);
      result.pages.forEach(page => {
        expect((page.match(/```/g)?.length ?? 0) % 2).toBe(0);
      });
      expect(result.pages.join('\n')).toContain('> const quotedLine9 = 9;');
      expect(result.pages.at(-1)).toContain('> Follow-up context after the quoted block.');
    });

    it('does not emit an empty reopened fence page when a split lands before the original closer', () => {
      const content = [
        '```ts',
        'alpha',
        'beta',
        '```',
        'tail',
      ].join('\n');

      const result = TextPaginator.paginate(content, { maxCharsPerPage: 20 });

      expect(result.totalPages).toBeGreaterThan(1);
      expect(result.pages[1]).not.toContain('```ts\n```\n');
      expect(result.pages.join('\n')).toContain('tail');
    });
  });

  describe('fence parsing', () => {
    it('treats quoted fence openers as still-open fences before their closer', () => {
      const content = [
        '> ```ts',
        '> const value = 1;',
        '> const value = 2;',
      ].join('\n');

      expect(paginatorInternals.findUnclosedFence(content)).not.toBeNull();
    });

    it('does not treat four-space-indented fence-like text as a fence closer', () => {
      const content = [
        '````md',
        'alpha',
        '    ````',
        'omega',
      ].join('\n');

      expect(paginatorInternals.findUnclosedFence(content)).not.toBeNull();
    });

    it('accepts closing fences that use a longer run than the opener', () => {
      const content = [
        '````md',
        'alpha',
        'beta',
        '`````',
      ].join('\n');

      expect(paginatorInternals.findUnclosedFence(content)).toBeNull();
    });

    it('forces forward progress when the first fenced content line exceeds the page limit', () => {
      const content = [
        '```ts',
        'const value = "this fenced line is intentionally much longer than the page limit";',
        '```',
        'tail',
      ].join('\n');

      const result = paginatorInternals.splitPage(content, 22);

      expect(result.remainingContent.length).toBeLessThan(content.length);
      expect(result.page).not.toBe('```ts\n```');
      expect(result.page.length).toBeGreaterThan('```ts\n```'.length);
    });
  });

  describe('getPage', () => {
    it('returns correct page by index (1-based)', () => {
      const content = 'A'.repeat(300);
      const paginated = TextPaginator.paginate(content, { maxCharsPerPage: 100 });

      expect(TextPaginator.getPage(paginated, 1)).toBe(paginated.pages[0]);
      expect(TextPaginator.getPage(paginated, 2)).toBe(paginated.pages[1]);
      expect(TextPaginator.getPage(paginated, 3)).toBe(paginated.pages[2]);
    });

    it('returns first page for page < 1', () => {
      const content = 'A'.repeat(300);
      const paginated = TextPaginator.paginate(content, { maxCharsPerPage: 100 });

      expect(TextPaginator.getPage(paginated, 0)).toBe(paginated.pages[0]);
      expect(TextPaginator.getPage(paginated, -1)).toBe(paginated.pages[0]);
    });

    it('returns last page for page > totalPages', () => {
      const content = 'A'.repeat(300);
      const paginated = TextPaginator.paginate(content, { maxCharsPerPage: 100 });

      expect(TextPaginator.getPage(paginated, 10)).toBe(paginated.pages[2]);
    });
  });

  describe('buildPaginationButtons', () => {
    it('creates action row with previous, indicator, and next buttons', () => {
      const row = TextPaginator.buildPaginationButtons({
        currentPage: 2,
        totalPages: 5,
        customIdPrefix: 'test_page',
        stateId: 'abc123',
      });

      const buttons = row.components;
      expect(buttons).toHaveLength(3);
    });

    it('disables previous button on first page', () => {
      const row = TextPaginator.buildPaginationButtons({
        currentPage: 1,
        totalPages: 5,
        customIdPrefix: 'test_page',
        stateId: 'abc123',
      });

      const prevButton = row.components[0];
      expect(prevButton.data.disabled).toBe(true);
    });

    it('disables next button on last page', () => {
      const row = TextPaginator.buildPaginationButtons({
        currentPage: 5,
        totalPages: 5,
        customIdPrefix: 'test_page',
        stateId: 'abc123',
      });

      const nextButton = row.components[2];
      expect(nextButton.data.disabled).toBe(true);
    });

    it('enables both buttons on middle pages', () => {
      const row = TextPaginator.buildPaginationButtons({
        currentPage: 3,
        totalPages: 5,
        customIdPrefix: 'test_page',
        stateId: 'abc123',
      });

      const prevButton = row.components[0];
      const nextButton = row.components[2];
      expect(prevButton.data.disabled).toBe(false);
      expect(nextButton.data.disabled).toBe(false);
    });

    it('uses correct custom IDs for navigation', () => {
      const row = TextPaginator.buildPaginationButtons({
        currentPage: 2,
        totalPages: 5,
        customIdPrefix: 'vibecheck_page',
        stateId: 'xyz789',
      });

      const rowJson = row.toJSON();
      expect(rowJson.components[0]).toMatchObject({ custom_id: 'vibecheck_page:1:xyz789' });
      expect(rowJson.components[2]).toMatchObject({ custom_id: 'vibecheck_page:3:xyz789' });
    });

    it('shows page indicator in center button', () => {
      const row = TextPaginator.buildPaginationButtons({
        currentPage: 3,
        totalPages: 7,
        customIdPrefix: 'test',
        stateId: 'abc',
      });

      const rowJson = row.toJSON();
      expect(rowJson.components[1]).toMatchObject({ label: '3/7', disabled: true });
    });
  });

  describe('parseButtonCustomId', () => {
    it('extracts page number and stateId from custom ID', () => {
      const result = TextPaginator.parseButtonCustomId('vibecheck_page:3:abc123');

      expect(result).toEqual({
        prefix: 'vibecheck_page',
        page: 3,
        stateId: 'abc123',
      });
    });

    it('returns null for invalid format', () => {
      expect(TextPaginator.parseButtonCustomId('invalid')).toBeNull();
      expect(TextPaginator.parseButtonCustomId('prefix:notanumber:state')).toBeNull();
      expect(TextPaginator.parseButtonCustomId('')).toBeNull();
    });
  });
});
