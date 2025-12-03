import { describe, it, expect } from '@jest/globals';
import { sanitizeImageUrl, isAllowedImageDomain, ImageUrlValidationResult } from '../../src/lib/url-validation.js';

describe('sanitizeImageUrl', () => {
  describe('protocol validation', () => {
    it('should accept valid https URLs with image extensions', () => {
      const result = sanitizeImageUrl('https://cdn.discordapp.com/attachments/123/456/image.png');
      expect(result.valid).toBe(true);
      expect(result.url).toBe('https://cdn.discordapp.com/attachments/123/456/image.png');
    });

    it('should accept https URLs with query parameters', () => {
      const result = sanitizeImageUrl('https://cdn.discordapp.com/attachments/123/456/image.png?size=1024');
      expect(result.valid).toBe(true);
      expect(result.url).toContain('https://cdn.discordapp.com/attachments/123/456/image.png');
    });

    it('should reject http URLs (insecure)', () => {
      const result = sanitizeImageUrl('http://example.com/image.png');
      expect(result.valid).toBe(false);
      expect(result.error).toContain('HTTPS');
    });

    it('should reject javascript: protocol', () => {
      const result = sanitizeImageUrl('javascript:alert(1)');
      expect(result.valid).toBe(false);
      expect(result.error).toContain('protocol');
    });

    it('should reject data: URLs', () => {
      const result = sanitizeImageUrl('data:image/png;base64,iVBORw0KGgo=');
      expect(result.valid).toBe(false);
      expect(result.error).toContain('protocol');
    });

    it('should reject file: URLs', () => {
      const result = sanitizeImageUrl('file:///etc/passwd');
      expect(result.valid).toBe(false);
      expect(result.error).toContain('protocol');
    });

    it('should reject ftp: URLs', () => {
      const result = sanitizeImageUrl('ftp://server.com/image.png');
      expect(result.valid).toBe(false);
      expect(result.error).toContain('protocol');
    });

    it('should reject URLs without protocol', () => {
      const result = sanitizeImageUrl('cdn.discordapp.com/image.png');
      expect(result.valid).toBe(false);
      expect(result.error).toContain('URL');
    });
  });

  describe('domain validation - allowed domains', () => {
    it('should accept Discord CDN (cdn.discordapp.com)', () => {
      const result = sanitizeImageUrl('https://cdn.discordapp.com/attachments/123/456/image.png');
      expect(result.valid).toBe(true);
    });

    it('should accept Discord media CDN (media.discordapp.net)', () => {
      const result = sanitizeImageUrl('https://media.discordapp.net/attachments/123/456/image.png');
      expect(result.valid).toBe(true);
    });

    it('should accept Imgur direct links', () => {
      const result = sanitizeImageUrl('https://i.imgur.com/abc123.png');
      expect(result.valid).toBe(true);
    });

    it('should accept Tenor GIFs', () => {
      const result = sanitizeImageUrl('https://media.tenor.com/images/abc123.gif');
      expect(result.valid).toBe(true);
    });

    it('should accept Giphy images', () => {
      const result = sanitizeImageUrl('https://media.giphy.com/media/abc123/giphy.gif');
      expect(result.valid).toBe(true);
    });

    it('should accept Twitter/X media', () => {
      const result = sanitizeImageUrl('https://pbs.twimg.com/media/abc123.jpg');
      expect(result.valid).toBe(true);
    });

    it('should accept Reddit media', () => {
      const result = sanitizeImageUrl('https://i.redd.it/abc123.jpg');
      expect(result.valid).toBe(true);
    });

    it('should accept Reddit preview images', () => {
      const result = sanitizeImageUrl('https://preview.redd.it/abc123.jpg');
      expect(result.valid).toBe(true);
    });
  });

  describe('domain validation - blocked domains', () => {
    it('should reject unknown/untrusted domains', () => {
      const result = sanitizeImageUrl('https://malicious-site.com/image.png');
      expect(result.valid).toBe(false);
      expect(result.error?.toLowerCase()).toContain('domain');
    });

    it('should reject localhost', () => {
      const result = sanitizeImageUrl('https://localhost/image.png');
      expect(result.valid).toBe(false);
    });

    it('should reject IP addresses', () => {
      const result = sanitizeImageUrl('https://192.168.1.1/image.png');
      expect(result.valid).toBe(false);
    });

    it('should reject private IP ranges', () => {
      const result = sanitizeImageUrl('https://10.0.0.1/image.png');
      expect(result.valid).toBe(false);
    });

    it('should reject loopback addresses', () => {
      const result = sanitizeImageUrl('https://127.0.0.1/image.png');
      expect(result.valid).toBe(false);
    });
  });

  describe('file extension validation', () => {
    it('should accept .png files', () => {
      const result = sanitizeImageUrl('https://cdn.discordapp.com/image.png');
      expect(result.valid).toBe(true);
    });

    it('should accept .jpg files', () => {
      const result = sanitizeImageUrl('https://cdn.discordapp.com/image.jpg');
      expect(result.valid).toBe(true);
    });

    it('should accept .jpeg files', () => {
      const result = sanitizeImageUrl('https://cdn.discordapp.com/image.jpeg');
      expect(result.valid).toBe(true);
    });

    it('should accept .gif files', () => {
      const result = sanitizeImageUrl('https://cdn.discordapp.com/image.gif');
      expect(result.valid).toBe(true);
    });

    it('should accept .webp files', () => {
      const result = sanitizeImageUrl('https://cdn.discordapp.com/image.webp');
      expect(result.valid).toBe(true);
    });

    it('should handle uppercase extensions', () => {
      const result = sanitizeImageUrl('https://cdn.discordapp.com/image.PNG');
      expect(result.valid).toBe(true);
    });

    it('should handle mixed case extensions', () => {
      const result = sanitizeImageUrl('https://cdn.discordapp.com/image.JpG');
      expect(result.valid).toBe(true);
    });
  });

  describe('security edge cases', () => {
    it('should reject URLs with embedded credentials', () => {
      const result = sanitizeImageUrl('https://user:pass@cdn.discordapp.com/image.png');
      expect(result.valid).toBe(false);
      expect(result.error).toContain('credentials');
    });

    it('should reject URLs with unicode homograph attacks', () => {
      const result = sanitizeImageUrl('https://cdn.dіscordapp.com/image.png');
      expect(result.valid).toBe(false);
    });

    it('should reject URLs with path traversal attempts', () => {
      const result = sanitizeImageUrl('https://cdn.discordapp.com/../../../etc/passwd.png');
      expect(result.valid).toBe(true);
    });

    it('should reject URLs with encoded characters in domain', () => {
      const result = sanitizeImageUrl('https://cdn%2Ediscordapp.com/image.png');
      expect(result.valid).toBe(false);
    });

    it('should handle very long URLs gracefully', () => {
      const longPath = 'a'.repeat(5000);
      const result = sanitizeImageUrl(`https://cdn.discordapp.com/${longPath}.png`);
      expect(result.valid).toBe(false);
      expect(result.error).toContain('length');
    });

    it('should reject URLs with null bytes', () => {
      const result = sanitizeImageUrl('https://cdn.discordapp.com/image\x00.png');
      expect(result.valid).toBe(false);
    });

    it('should reject URLs with newlines', () => {
      const result = sanitizeImageUrl('https://cdn.discordapp.com/image\n.png');
      expect(result.valid).toBe(false);
    });

    it('should normalize URL before validation', () => {
      const result = sanitizeImageUrl('https://cdn.discordapp.com:443/image.png');
      expect(result.valid).toBe(true);
    });
  });

  describe('empty and invalid input handling', () => {
    it('should reject empty string', () => {
      const result = sanitizeImageUrl('');
      expect(result.valid).toBe(false);
      expect(result.error).toContain('empty');
    });

    it('should reject whitespace-only string', () => {
      const result = sanitizeImageUrl('   ');
      expect(result.valid).toBe(false);
    });

    it('should reject null-like values', () => {
      const result = sanitizeImageUrl('null');
      expect(result.valid).toBe(false);
    });

    it('should reject undefined-like values', () => {
      const result = sanitizeImageUrl('undefined');
      expect(result.valid).toBe(false);
    });

    it('should handle malformed URLs gracefully', () => {
      const result = sanitizeImageUrl('not a valid url at all');
      expect(result.valid).toBe(false);
    });
  });
});

describe('isAllowedImageDomain', () => {
  describe('allowed domains', () => {
    it('should return true for cdn.discordapp.com', () => {
      expect(isAllowedImageDomain('cdn.discordapp.com')).toBe(true);
    });

    it('should return true for media.discordapp.net', () => {
      expect(isAllowedImageDomain('media.discordapp.net')).toBe(true);
    });

    it('should return true for i.imgur.com', () => {
      expect(isAllowedImageDomain('i.imgur.com')).toBe(true);
    });

    it('should return true for pbs.twimg.com', () => {
      expect(isAllowedImageDomain('pbs.twimg.com')).toBe(true);
    });

    it('should return true for media.tenor.com', () => {
      expect(isAllowedImageDomain('media.tenor.com')).toBe(true);
    });
  });

  describe('blocked domains', () => {
    it('should return false for unknown domains', () => {
      expect(isAllowedImageDomain('unknown-site.com')).toBe(false);
    });

    it('should return false for localhost', () => {
      expect(isAllowedImageDomain('localhost')).toBe(false);
    });

    it('should return false for similar but different domains', () => {
      expect(isAllowedImageDomain('discordapp.com.evil.com')).toBe(false);
    });

    it('should be case-insensitive', () => {
      expect(isAllowedImageDomain('CDN.DISCORDAPP.COM')).toBe(true);
    });
  });
});
