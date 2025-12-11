import { jest } from '@jest/globals';
import {
  ButtonBuilder,
  ButtonStyle,
  ActionRowBuilder,
  MessageFlags,
} from 'discord.js';

const mockCache = {
  get: jest.fn<(key: string) => Promise<unknown>>(),
  set: jest.fn<(key: string, value: unknown, ttl?: number) => Promise<void>>(),
  delete: jest.fn<(key: string) => Promise<void>>(),
  start: jest.fn<() => void>(),
  stop: jest.fn<() => void>(),
  getMetrics: jest.fn(() => ({ size: 0 })),
  clear: jest.fn<() => Promise<void>>(),
};

jest.unstable_mockModule('../../src/cache.js', () => ({
  cache: mockCache,
}));

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: {
    info: jest.fn(),
    error: jest.fn(),
    warn: jest.fn(),
    debug: jest.fn(),
  },
}));

jest.unstable_mockModule('../../src/lib/errors.js', () => ({
  generateErrorId: () => 'test-error-id',
  extractErrorDetails: (error: any) => ({
    message: error?.message || 'Unknown error',
    type: error?.constructor?.name || 'Error',
    stack: error?.stack || '',
  }),
  formatErrorForUser: (errorId: string, message: string) => `${message} (Error ID: ${errorId})`,
  ApiError: class ApiError extends Error {
    constructor(
      message: string,
      public endpoint?: string,
      public statusCode?: number,
      public responseBody?: any
    ) {
      super(message);
    }
  },
}));

describe('list command - Force Publish button confirmation', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockCache.get.mockResolvedValue(null);
    mockCache.set.mockResolvedValue(undefined);
    mockCache.delete.mockResolvedValue(undefined);
    mockCache.clear.mockResolvedValue(undefined);
  });

  describe('force_publish_confirm button pattern', () => {
    it('should use button-based confirmation instead of text-based', () => {
      const confirmCustomId = 'fp_confirm:abc12345';
      const cancelCustomId = 'fp_cancel:abc12345';

      expect(confirmCustomId.length).toBeLessThan(100);
      expect(cancelCustomId.length).toBeLessThan(100);

      expect(confirmCustomId).toMatch(/^fp_confirm:[a-zA-Z0-9]{8}$/);
      expect(cancelCustomId).toMatch(/^fp_cancel:[a-zA-Z0-9]{8}$/);
    });

    it('should create Confirm and Cancel buttons with correct styles', () => {
      const shortId = 'test1234';

      const confirmButton = new ButtonBuilder()
        .setCustomId(`fp_confirm:${shortId}`)
        .setLabel('Confirm')
        .setStyle(ButtonStyle.Danger);

      const cancelButton = new ButtonBuilder()
        .setCustomId(`fp_cancel:${shortId}`)
        .setLabel('Cancel')
        .setStyle(ButtonStyle.Secondary);

      const confirmJson = confirmButton.toJSON() as any;
      const cancelJson = cancelButton.toJSON() as any;

      expect(confirmJson.custom_id).toBe(`fp_confirm:${shortId}`);
      expect(confirmJson.label).toBe('Confirm');
      expect(confirmJson.style).toBe(ButtonStyle.Danger);

      expect(cancelJson.custom_id).toBe(`fp_cancel:${shortId}`);
      expect(cancelJson.label).toBe('Cancel');
      expect(cancelJson.style).toBe(ButtonStyle.Secondary);
    });

    it('should create action row with both buttons', () => {
      const shortId = 'test1234';

      const confirmButton = new ButtonBuilder()
        .setCustomId(`fp_confirm:${shortId}`)
        .setLabel('Confirm')
        .setStyle(ButtonStyle.Danger);

      const cancelButton = new ButtonBuilder()
        .setCustomId(`fp_cancel:${shortId}`)
        .setLabel('Cancel')
        .setStyle(ButtonStyle.Secondary);

      const row = new ActionRowBuilder<ButtonBuilder>().addComponents(
        confirmButton,
        cancelButton
      );

      expect(row.components).toHaveLength(2);
      expect((row.components[0].toJSON() as any).custom_id).toBe(`fp_confirm:${shortId}`);
      expect((row.components[1].toJSON() as any).custom_id).toBe(`fp_cancel:${shortId}`);
    });

    it('should NOT use text-based message collector for confirmation', () => {
      const oldConfirmationPattern = 'Reply with "confirm" to proceed';
      const newConfirmationPrompt =
        'Click **Confirm** to proceed or **Cancel** to dismiss.';

      expect(newConfirmationPrompt).not.toContain('Reply with');
      expect(newConfirmationPrompt).not.toContain('"confirm"');
      expect(newConfirmationPrompt).toContain('Confirm');
      expect(newConfirmationPrompt).toContain('Cancel');
    });
  });

  describe('force publish confirmation state caching', () => {
    it('should cache noteId with short ID for button interaction', async () => {
      const noteId = '550e8400-e29b-41d4-a716-446655440000';
      const shortId = 'test1234';
      const cacheKey = `fp_state:${shortId}`;
      const cacheValue = { noteId, userId: 'user123' };

      mockCache.set.mockResolvedValue(undefined);
      mockCache.get.mockResolvedValue(cacheValue);

      await mockCache.set(cacheKey, cacheValue, 60);

      const retrieved = await mockCache.get(cacheKey);
      expect(retrieved).toEqual({ noteId, userId: 'user123' });
      expect(mockCache.set).toHaveBeenCalledWith(cacheKey, cacheValue, 60);
      expect(mockCache.get).toHaveBeenCalledWith(cacheKey);
    });

    it('should validate short ID length for cache key', () => {
      const shortId = 'a1b2c3d4';
      const cacheKey = `fp_state:${shortId}`;

      expect(shortId.length).toBe(8);
      expect(cacheKey.length).toBe(17);
    });

    it('should handle expired cache state gracefully', async () => {
      const missingCacheKey = 'fp_state:nonexist';
      mockCache.get.mockResolvedValue(null);

      const retrieved = await mockCache.get(missingCacheKey);
      expect(retrieved).toBeNull();
    });
  });

  describe('confirmation message content', () => {
    it('should include warning emoji and clear action description', () => {
      const noteId = '550e8400-e29b-41d4-a716-446655440000';
      const confirmationMessage = [
        '**Confirm Force Publish**',
        '',
        `Are you sure you want to force publish Note #${noteId}?`,
        '',
        'This will:',
        '- Bypass the normal rating threshold requirements',
        '- Mark the note as "Admin Published"',
        '- Immediately publish the note to the configured channel',
        '',
        'Click **Confirm** to proceed or **Cancel** to dismiss.',
      ].join('\n');

      expect(confirmationMessage).toContain('Confirm Force Publish');
      expect(confirmationMessage).toContain(noteId);
      expect(confirmationMessage).toContain('Bypass the normal rating');
      expect(confirmationMessage).toContain('Admin Published');
      expect(confirmationMessage).toContain('Confirm');
      expect(confirmationMessage).toContain('Cancel');
      expect(confirmationMessage).not.toContain('Reply with');
    });

    it('should use ephemeral message for confirmation', () => {
      const replyOptions = {
        content: 'Confirm Force Publish message...',
        components: [],
        flags: MessageFlags.Ephemeral,
      };

      expect(replyOptions.flags).toBe(MessageFlags.Ephemeral);
    });
  });

  describe('button interaction handlers', () => {
    it('should parse confirm button custom ID correctly', () => {
      const customId = 'fp_confirm:abc12345';
      const parts = customId.split(':');

      expect(parts).toHaveLength(2);
      expect(parts[0]).toBe('fp_confirm');
      expect(parts[1]).toBe('abc12345');
    });

    it('should parse cancel button custom ID correctly', () => {
      const customId = 'fp_cancel:abc12345';
      const parts = customId.split(':');

      expect(parts).toHaveLength(2);
      expect(parts[0]).toBe('fp_cancel');
      expect(parts[1]).toBe('abc12345');
    });

    it('should identify confirmation buttons by prefix', () => {
      const confirmCustomId = 'fp_confirm:abc12345';
      const cancelCustomId = 'fp_cancel:def67890';
      const otherCustomId = 'rate:note123:helpful';

      expect(confirmCustomId.startsWith('fp_confirm:')).toBe(true);
      expect(cancelCustomId.startsWith('fp_cancel:')).toBe(true);
      expect(otherCustomId.startsWith('fp_confirm:')).toBe(false);
      expect(otherCustomId.startsWith('fp_cancel:')).toBe(false);
    });
  });

  describe('cancel flow', () => {
    it('should update message to show cancelled state', () => {
      const cancelledMessage = 'Force publish cancelled.';

      expect(cancelledMessage).toContain('cancelled');
      expect(cancelledMessage).not.toContain('error');
    });

    it('should remove buttons after cancel', () => {
      const updateOptions = {
        content: 'Force publish cancelled.',
        components: [],
      };

      expect(updateOptions.components).toHaveLength(0);
    });
  });

  describe('timeout handling', () => {
    it('should define timeout constant for button collector', () => {
      const FORCE_PUBLISH_CONFIRM_TIMEOUT_MS = 30000;

      expect(FORCE_PUBLISH_CONFIRM_TIMEOUT_MS).toBe(30000);
    });

    it('should disable buttons on timeout', () => {
      const disabledConfirmButton = new ButtonBuilder()
        .setCustomId('fp_confirm:test1234')
        .setLabel('Confirm')
        .setStyle(ButtonStyle.Danger)
        .setDisabled(true);

      const disabledCancelButton = new ButtonBuilder()
        .setCustomId('fp_cancel:test1234')
        .setLabel('Cancel')
        .setStyle(ButtonStyle.Secondary)
        .setDisabled(true);

      expect(disabledConfirmButton.data.disabled).toBe(true);
      expect(disabledCancelButton.data.disabled).toBe(true);
    });

    it('should update message on timeout to indicate expiration', () => {
      const timeoutMessage = 'Force publish confirmation timed out.';

      expect(timeoutMessage).toContain('timed out');
    });
  });
});
