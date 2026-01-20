import { describe, it, expect, jest } from '@jest/globals';

jest.unstable_mockModule('../../src/config.js', () => ({
  config: {
    clientId: 'test-client-id-123',
  },
}));

const { getMinimalInstallUrl, getFullInstallUrl, getUpgradeUrl, PERMISSION_VALUES } = await import(
  '../../src/lib/oauth2-urls.js'
);

describe('oauth2-urls', () => {
  describe('getMinimalInstallUrl', () => {
    it('should return URL with minimal permissions', () => {
      const url = getMinimalInstallUrl();

      expect(url).toContain('client_id=test-client-id-123');
      expect(url).toContain(`permissions=${PERMISSION_VALUES.minimal}`);
      expect(url).toContain('scope=bot%20applications.commands');
      expect(url).toMatch(/^https:\/\/discord\.com\/api\/oauth2\/authorize/);
    });
  });

  describe('getFullInstallUrl', () => {
    it('should return URL with full permissions', () => {
      const url = getFullInstallUrl();

      expect(url).toContain('client_id=test-client-id-123');
      expect(url).toContain(`permissions=${PERMISSION_VALUES.full}`);
      expect(url).toContain('scope=bot%20applications.commands');
    });

    it('full permissions should include all minimal permissions', () => {
      expect((PERMISSION_VALUES.full & PERMISSION_VALUES.minimal) === PERMISSION_VALUES.minimal).toBe(true);
    });
  });

  describe('getUpgradeUrl', () => {
    it('should return URL with guild_id and disable_guild_select', () => {
      const url = getUpgradeUrl('guild-456');

      expect(url).toContain('client_id=test-client-id-123');
      expect(url).toContain(`permissions=${PERMISSION_VALUES.full}`);
      expect(url).toContain('guild_id=guild-456');
      expect(url).toContain('disable_guild_select=true');
    });

    it('should throw if guildId is empty', () => {
      expect(() => getUpgradeUrl('')).toThrow('guildId is required and cannot be empty or whitespace');
    });

    it('should throw if guildId is whitespace only', () => {
      expect(() => getUpgradeUrl('   ')).toThrow('guildId is required and cannot be empty or whitespace');
    });
  });

  describe('PERMISSION_VALUES', () => {
    it('should export minimal and full permission values', () => {
      expect(PERMISSION_VALUES.minimal).toBeDefined();
      expect(PERMISSION_VALUES.full).toBeDefined();
      expect(typeof PERMISSION_VALUES.minimal).toBe('bigint');
      expect(typeof PERMISSION_VALUES.full).toBe('bigint');
    });
  });
});
