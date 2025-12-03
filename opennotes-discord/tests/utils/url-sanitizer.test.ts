import { sanitizeConnectionUrl } from '../../src/utils/url-sanitizer.js';

describe('sanitizeConnectionUrl', () => {
  describe('Redis URLs', () => {
    it('should sanitize Redis URL with username and password', () => {
      const url = 'redis://admin:secretpassword@localhost:6379';
      const sanitized = sanitizeConnectionUrl(url);
      expect(sanitized).toContain('redis://admin:****@localhost:6379');
      expect(sanitized).not.toContain('secretpassword');
    });

    it('should sanitize Redis URL with only password', () => {
      const url = 'redis://:secretpassword@localhost:6379';
      const sanitized = sanitizeConnectionUrl(url);
      expect(sanitized).toContain('redis://:****@localhost:6379');
      expect(sanitized).not.toContain('secretpassword');
    });

    it('should handle Redis URL without credentials', () => {
      const url = 'redis://localhost:6379';
      const sanitized = sanitizeConnectionUrl(url);
      expect(sanitized).toBe('redis://localhost:6379');
    });

    it('should sanitize Redis URL with database number', () => {
      const url = 'redis://admin:secretpassword@localhost:6379/2';
      const sanitized = sanitizeConnectionUrl(url);
      expect(sanitized).toBe('redis://admin:****@localhost:6379/2');
      expect(sanitized).not.toContain('secretpassword');
    });

    it('should sanitize Redis URL with TLS', () => {
      const url = 'rediss://admin:secretpassword@redis.example.com:6380';
      const sanitized = sanitizeConnectionUrl(url);
      expect(sanitized).toContain('rediss://admin:****@redis.example.com:6380');
      expect(sanitized).not.toContain('secretpassword');
    });
  });

  describe('NATS URLs', () => {
    it('should sanitize NATS URL with username and password', () => {
      const url = 'nats://user:password123@nats.example.com:4222';
      const sanitized = sanitizeConnectionUrl(url);
      expect(sanitized).toContain('nats://user:****@nats.example.com:4222');
      expect(sanitized).not.toContain('password123');
    });

    it('should sanitize NATS URL with special characters in password', () => {
      const url = 'nats://user:p@ssw0rd!@nats.example.com:4222';
      const sanitized = sanitizeConnectionUrl(url);
      expect(sanitized).not.toContain('p@ssw0rd!');
      expect(sanitized).toContain('****');
    });

    it('should handle NATS URL without credentials', () => {
      const url = 'nats://localhost:4222';
      const sanitized = sanitizeConnectionUrl(url);
      expect(sanitized).toBe('nats://localhost:4222');
    });

    it('should sanitize NATS URL with TLS', () => {
      const url = 'tls://user:password@nats.example.com:4222';
      const sanitized = sanitizeConnectionUrl(url);
      expect(sanitized).toBe('tls://user:****@nats.example.com:4222');
      expect(sanitized).not.toContain('password');
    });
  });

  describe('HTTP/HTTPS URLs', () => {
    it('should sanitize HTTPS URL with username and password', () => {
      const url = 'https://admin:secret@api.example.com/path';
      const sanitized = sanitizeConnectionUrl(url);
      expect(sanitized).toBe('https://admin:****@api.example.com/path');
      expect(sanitized).not.toContain('secret');
    });

    it('should sanitize HTTP URL with credentials', () => {
      const url = 'http://user:pass@localhost:8080';
      const sanitized = sanitizeConnectionUrl(url);
      expect(sanitized).toContain('http://user:****@localhost:8080');
      expect(sanitized).not.toContain('pass');
    });
  });

  describe('Edge Cases', () => {
    it('should handle URL with @ in username', () => {
      const url = 'redis://user@domain.com:password@localhost:6379';
      const sanitized = sanitizeConnectionUrl(url);
      expect(sanitized).not.toContain('password');
      expect(sanitized).toContain('****');
    });

    it('should handle URL with complex password', () => {
      const url = 'redis://user:c0mpl3x!P@ssw0rd#2024@redis.example.com:6379';
      const sanitized = sanitizeConnectionUrl(url);
      expect(sanitized).not.toContain('c0mpl3x!P@ssw0rd#2024');
      expect(sanitized).toContain('****');
    });

    it('should handle URL with query parameters', () => {
      const url = 'redis://user:password@localhost:6379?db=2&timeout=5000';
      const sanitized = sanitizeConnectionUrl(url);
      expect(sanitized).not.toContain('password');
      expect(sanitized).toContain('****');
      expect(sanitized).toContain('db=2');
      expect(sanitized).toContain('timeout=5000');
    });

    it('should handle invalid URL gracefully with regex fallback', () => {
      const url = 'not-a-valid-url://user:password@host';
      const sanitized = sanitizeConnectionUrl(url);
      expect(sanitized).not.toContain('password');
      expect(sanitized).toContain('****');
    });

    it('should handle URL with no @ symbol', () => {
      const url = 'redis://localhost:6379';
      const sanitized = sanitizeConnectionUrl(url);
      expect(sanitized).toBe('redis://localhost:6379');
    });

    it('should handle empty string', () => {
      const url = '';
      const sanitized = sanitizeConnectionUrl(url);
      expect(sanitized).toBe('');
    });

    it('should handle URL with IPv6 address', () => {
      const url = 'redis://user:password@[::1]:6379';
      const sanitized = sanitizeConnectionUrl(url);
      expect(sanitized).not.toContain('password');
      expect(sanitized).toContain('****');
      expect(sanitized).toContain('[::1]');
    });
  });

  describe('Security Verification', () => {
    const sensitivePasswords = [
      'MySecretP@ssw0rd!',
      '12345',
      'admin123',
      'p@ssw0rd',
      'super-secret-key-2024',
      'aB3$xYz!9#',
    ];

    sensitivePasswords.forEach(password => {
      it(`should not leak password: ${password}`, () => {
        const url = `redis://user:${password}@localhost:6379`;
        const sanitized = sanitizeConnectionUrl(url);
        expect(sanitized).not.toContain(password);
        expect(sanitized).toContain('****');
      });
    });
  });
});
