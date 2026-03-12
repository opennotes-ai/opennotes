import {
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
} from 'discord.js';

export interface PaginatedContent {
  pages: string[];
  totalPages: number;
}

export interface TextPaginatorOptions {
  maxCharsPerPage?: number;
  addPageIndicator?: boolean;
}

export interface PaginationButtonConfig {
  currentPage: number;
  totalPages: number;
  customIdPrefix: string;
  stateId: string;
}

export interface ParsedButtonId {
  prefix: string;
  page: number;
  stateId: string;
}

interface FenceState {
  openerLine: string;
  closingLine: string;
  marker: '`' | '~';
  markerLength: number;
  quotePrefix: string;
}

interface ParsedFenceLine {
  rawLine: string;
  quotePrefix: string;
  marker: '`' | '~';
  markerRun: string;
  rest: string;
}

const DEFAULT_MAX_CHARS = 1900;

export class TextPaginator {
  static paginate(content: string, options?: TextPaginatorOptions): PaginatedContent {
    const maxChars = options?.maxCharsPerPage ?? DEFAULT_MAX_CHARS;
    const addIndicator = options?.addPageIndicator ?? false;

    if (!content || content.length <= maxChars) {
      return {
        pages: [content],
        totalPages: 1,
      };
    }

    const pages: string[] = [];
    let remaining = content;

    while (remaining.length > 0) {
      if (remaining.length <= maxChars) {
        pages.push(remaining);
        break;
      }

      const { page, remainingContent } = this.splitPage(remaining, maxChars);
      pages.push(page);
      remaining = remainingContent;
    }

    if (addIndicator) {
      const totalPages = pages.length;
      return {
        pages: pages.map((page, i) => `${page}\n\n*(${i + 1}/${totalPages})*`),
        totalPages,
      };
    }

    return {
      pages,
      totalPages: pages.length,
    };
  }

  private static splitPage(content: string, maxChars: number): { page: string; remainingContent: string } {
    let splitIndex = this.findSplitIndex(content, maxChars);
    let page = content.slice(0, splitIndex);
    let remainingContent = content.slice(splitIndex);
    let openFence = this.findUnclosedFence(page);

    while (openFence) {
      const closedPage = this.closeFence(page, openFence);
      if (closedPage.length <= maxChars) {
        const reopenedContent = this.reopenFence(remainingContent, openFence);
        if (reopenedContent.length < content.length) {
          return {
            page: closedPage,
            remainingContent: reopenedContent,
          };
        }

        const progressSplitIndex = this.findProgressSplitIndex(content, maxChars, splitIndex);
        if (progressSplitIndex <= splitIndex) {
          break;
        }

        splitIndex = progressSplitIndex;
        page = content.slice(0, splitIndex);
        remainingContent = content.slice(splitIndex);
        openFence = this.findUnclosedFence(page);
        continue;
      }

      const adjustedMaxChars = Math.max(1, maxChars - this.getFenceClosureOverhead(page, openFence));
      const adjustedSplitIndex = this.findSplitIndex(content, adjustedMaxChars);

      if (adjustedSplitIndex >= splitIndex) {
        return {
          page,
          remainingContent,
        };
      }

      splitIndex = adjustedSplitIndex;
      page = content.slice(0, splitIndex);
      remainingContent = content.slice(splitIndex);
      openFence = this.findUnclosedFence(page);
    }

    return {
      page,
      remainingContent,
    };
  }

  private static findSplitIndex(content: string, maxChars: number): number {
    const searchStart = Math.max(0, maxChars - 200);
    const searchEnd = maxChars;
    const searchRange = content.slice(searchStart, searchEnd);
    const lastNewline = searchRange.lastIndexOf('\n');

    if (lastNewline !== -1) {
      return searchStart + lastNewline + 1;
    }

    return maxChars;
  }

  private static findProgressSplitIndex(content: string, maxChars: number, minimumIndex: number): number {
    const maxCandidate = Math.min(content.length, maxChars);

    for (let candidate = maxCandidate; candidate > minimumIndex; candidate -= 1) {
      const candidatePage = content.slice(0, candidate);
      const candidateFence = this.findUnclosedFence(candidatePage);
      if (!candidateFence) {
        return candidate;
      }

      const candidateClosedPage = this.closeFence(candidatePage, candidateFence);
      if (candidateClosedPage.length > maxChars) {
        continue;
      }

      const candidateRemaining = this.reopenFence(content.slice(candidate), candidateFence);
      if (candidateRemaining.length < content.length) {
        return candidate;
      }
    }

    return minimumIndex;
  }

  private static findUnclosedFence(content: string): FenceState | null {
    const lines = content.split('\n');
    let openFence: FenceState | null = null;

    for (const line of lines) {
      if (!openFence) {
        const fence = this.parseFenceOpener(line);
        if (fence) {
          openFence = fence;
        }
        continue;
      }

      if (this.isFenceCloser(line, openFence)) {
        openFence = null;
      }
    }

    return openFence;
  }

  private static parseFenceLine(line: string): ParsedFenceLine | null {
    const rawLine = line.trimEnd();
    const match = rawLine.match(/^(?<quotePrefix>(?:>\s*)*)(?: {0,3})(?<marker>`{3,}|~{3,})(?<rest>.*)$/);
    if (!match?.groups) {
      return null;
    }

    const markerRun = match.groups.marker;
    return {
      rawLine,
      quotePrefix: match.groups.quotePrefix ?? '',
      marker: markerRun[0] as '`' | '~',
      markerRun,
      rest: match.groups.rest ?? '',
    };
  }

  private static parseFenceOpener(line: string): FenceState | null {
    const parsed = this.parseFenceLine(line);
    if (!parsed) {
      return null;
    }

    return {
      openerLine: parsed.rawLine,
      closingLine: `${parsed.quotePrefix}${parsed.markerRun}`,
      marker: parsed.marker,
      markerLength: parsed.markerRun.length,
      quotePrefix: parsed.quotePrefix,
    };
  }

  private static isFenceCloser(line: string, openFence: FenceState): boolean {
    const parsed = this.parseFenceLine(line);
    if (!parsed) {
      return false;
    }

    return parsed.quotePrefix === openFence.quotePrefix
      && parsed.marker === openFence.marker
      && parsed.markerRun.length >= openFence.markerLength
      && parsed.rest.trim() === '';
  }

  private static getFenceClosureOverhead(page: string, openFence: FenceState): number {
    return this.closeFence('', openFence).length + (page.endsWith('\n') ? 0 : 1);
  }

  private static closeFence(page: string, openFence: FenceState): string {
    const closingFence = this.getClosingFence(openFence);

    if (!page) {
      return closingFence;
    }

    return page.endsWith('\n') ? `${page}${closingFence}` : `${page}\n${closingFence}`;
  }

  private static reopenFence(content: string, openFence: FenceState): string {
    if (!content) {
      return content;
    }

    if (this.startsWithFenceCloser(content, openFence)) {
      return content;
    }

    return `${openFence.openerLine}\n${content}`;
  }

  private static startsWithFenceCloser(content: string, openFence: FenceState): boolean {
    const [firstLine = ''] = content.split('\n', 1);
    return this.isFenceCloser(firstLine, openFence);
  }

  private static getClosingFence(openFence: FenceState): string {
    return openFence.closingLine;
  }

  static getPage(paginated: PaginatedContent, page: number): string {
    const safeIndex = Math.max(0, Math.min(page - 1, paginated.totalPages - 1));
    return paginated.pages[safeIndex];
  }

  static buildPaginationButtons(config: PaginationButtonConfig): ActionRowBuilder<ButtonBuilder> {
    const { currentPage, totalPages, customIdPrefix, stateId } = config;

    const prevButton = new ButtonBuilder()
      .setCustomId(`${customIdPrefix}:${currentPage - 1}:${stateId}`)
      .setLabel('◀')
      .setStyle(ButtonStyle.Secondary)
      .setDisabled(currentPage <= 1);

    const pageIndicator = new ButtonBuilder()
      .setCustomId('page:indicator')
      .setLabel(`${currentPage}/${totalPages}`)
      .setStyle(ButtonStyle.Secondary)
      .setDisabled(true);

    const nextButton = new ButtonBuilder()
      .setCustomId(`${customIdPrefix}:${currentPage + 1}:${stateId}`)
      .setLabel('▶')
      .setStyle(ButtonStyle.Secondary)
      .setDisabled(currentPage >= totalPages);

    return new ActionRowBuilder<ButtonBuilder>().addComponents(
      prevButton,
      pageIndicator,
      nextButton
    );
  }

  static parseButtonCustomId(customId: string): ParsedButtonId | null {
    if (!customId) {
      return null;
    }

    const parts = customId.split(':');
    if (parts.length !== 3) {
      return null;
    }

    const [prefix, pageStr, stateId] = parts;
    const page = parseInt(pageStr, 10);

    if (isNaN(page)) {
      return null;
    }

    return { prefix, page, stateId };
  }
}
