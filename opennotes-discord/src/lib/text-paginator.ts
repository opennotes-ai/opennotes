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

      const splitIndex = this.findSplitIndex(remaining, maxChars);
      const page = remaining.slice(0, splitIndex);
      pages.push(page);
      remaining = remaining.slice(splitIndex);
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
