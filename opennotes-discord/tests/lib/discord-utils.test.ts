import { describe, it, expect, jest, beforeEach } from '@jest/globals';
import { ButtonStyle } from 'discord.js';
import {
  extractPlatformMessageId,
  createForcePublishConfirmationButtons,
  createDisabledForcePublishButtons,
} from '../../src/lib/discord-utils.js';

jest.mock('../../src/logger.js', () => ({
  logger: {
    debug: jest.fn(),
  },
}));

describe('extractPlatformMessageId', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('should return platform_message_id when it is provided', () => {
    const result = extractPlatformMessageId('123456789', 'discord-987654321-1700000000000');
    expect(result).toBe('123456789');
  });

  it('should extract message ID from request_id when platform_message_id is null', () => {
    const result = extractPlatformMessageId(null, 'discord-987654321-1700000000000');
    expect(result).toBe('987654321');
  });

  it('should extract message ID from request_id when platform_message_id is undefined', () => {
    const result = extractPlatformMessageId(undefined, 'discord-987654321-1700000000000');
    expect(result).toBe('987654321');
  });

  it('should extract message ID from request_id when platform_message_id is empty string', () => {
    const result = extractPlatformMessageId('', 'discord-987654321-1700000000000');
    expect(result).toBe('987654321');
  });

  it('should return null when request_id does not start with discord-', () => {
    const result = extractPlatformMessageId(null, 'req-123');
    expect(result).toBeNull();
  });

  it('should return null when request_id format is invalid', () => {
    const result = extractPlatformMessageId(null, 'discord-');
    expect(result).toBeNull();
  });

  it('should handle request_id with only one part after prefix', () => {
    const result = extractPlatformMessageId(null, 'discord-123456789');
    expect(result).toBe('123456789');
  });

  it('should handle complex Discord message IDs (snowflakes)', () => {
    const result = extractPlatformMessageId(null, 'discord-1234567890123456789-1700000000000');
    expect(result).toBe('1234567890123456789');
  });

  it('should prefer platform_message_id over extracting from request_id', () => {
    const result = extractPlatformMessageId('111111', 'discord-222222-1700000000000');
    expect(result).toBe('111111');
  });

  it('should return null for non-discord request_id formats without platform_message_id', () => {
    const result = extractPlatformMessageId(null, 'twitter-12345-1700000000000');
    expect(result).toBeNull();
  });
});

describe('createForcePublishConfirmationButtons', () => {
  it('should create confirmation buttons with correct custom IDs', () => {
    const noteId = '550e8400-e29b-41d4-a716-446655440000';
    const shortId = 'abc12345';
    const result = createForcePublishConfirmationButtons(noteId, shortId);

    expect(result.components).toHaveLength(1);
    const row = result.components[0];
    expect(row.components).toHaveLength(2);

    const confirmJson = row.components[0].toJSON() as any;
    const cancelJson = row.components[1].toJSON() as any;

    expect(confirmJson.custom_id).toBe('fp_confirm:abc12345');
    expect(confirmJson.label).toBe('Confirm');
    expect(confirmJson.style).toBe(ButtonStyle.Danger);

    expect(cancelJson.custom_id).toBe('fp_cancel:abc12345');
    expect(cancelJson.label).toBe('Cancel');
    expect(cancelJson.style).toBe(ButtonStyle.Secondary);
  });

  it('should include note ID in confirmation message', () => {
    const noteId = '550e8400-e29b-41d4-a716-446655440000';
    const shortId = 'abc12345';
    const result = createForcePublishConfirmationButtons(noteId, shortId);

    expect(result.content).toContain(noteId);
    expect(result.content).toContain('Confirm Force Publish');
    expect(result.content).toContain('Admin Published');
  });

  it('should NOT contain text-based confirmation instructions', () => {
    const noteId = '550e8400-e29b-41d4-a716-446655440000';
    const shortId = 'abc12345';
    const result = createForcePublishConfirmationButtons(noteId, shortId);

    expect(result.content).not.toContain('Reply with');
    expect(result.content).not.toContain('"confirm"');
    expect(result.content).toContain('Click **Confirm**');
    expect(result.content).toContain('**Cancel**');
  });

  it('should have custom IDs under 100 characters', () => {
    const noteId = '550e8400-e29b-41d4-a716-446655440000';
    const shortId = 'a1b2c3d4';
    const result = createForcePublishConfirmationButtons(noteId, shortId);

    const row = result.components[0];
    const confirmJson = row.components[0].toJSON() as any;
    const cancelJson = row.components[1].toJSON() as any;

    expect(confirmJson.custom_id.length).toBeLessThan(100);
    expect(cancelJson.custom_id.length).toBeLessThan(100);
  });
});

describe('createDisabledForcePublishButtons', () => {
  it('should create disabled buttons', () => {
    const shortId = 'abc12345';
    const result = createDisabledForcePublishButtons(shortId);

    expect(result).toHaveLength(1);
    const row = result[0];
    expect(row.components).toHaveLength(2);

    const confirmJson = row.components[0].toJSON() as any;
    const cancelJson = row.components[1].toJSON() as any;

    expect(confirmJson.disabled).toBe(true);
    expect(cancelJson.disabled).toBe(true);
  });

  it('should maintain same custom IDs as enabled buttons', () => {
    const shortId = 'abc12345';
    const result = createDisabledForcePublishButtons(shortId);

    const row = result[0];
    const confirmJson = row.components[0].toJSON() as any;
    const cancelJson = row.components[1].toJSON() as any;

    expect(confirmJson.custom_id).toBe('fp_confirm:abc12345');
    expect(cancelJson.custom_id).toBe('fp_cancel:abc12345');
  });
});
