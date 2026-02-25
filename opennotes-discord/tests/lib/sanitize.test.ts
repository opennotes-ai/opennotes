import { sanitizeValue, sanitizeObject } from '../../src/lib/sanitize.js';
import { createHash } from 'node:crypto';

describe('sanitizeValue', () => {
  it('returns non-sensitive values unchanged', () => {
    expect(sanitizeValue('name', 'Alice')).toBe('Alice');
    expect(sanitizeValue('email', 'test@example.com')).toBe('test@example.com');
    expect(sanitizeValue('status', 'active')).toBe('active');
  });

  it('partially reveals tokens (first 2 + last 2)', () => {
    expect(sanitizeValue('token', 'abcdefgh')).toBe('ab****gh');
    expect(sanitizeValue('api_key', 'sk-12345678')).toBe('sk****78');
    expect(sanitizeValue('access_token', 'Bearer.xyz123')).toBe('Be****23');
    expect(sanitizeValue('refresh_token', 'rt-abcdef')).toBe('rt****ef');
    expect(sanitizeValue('secret', 'mysecretvalue')).toBe('my****ue');
    expect(sanitizeValue('authorization', 'Bearer token123')).toBe('Be****23');
    expect(sanitizeValue('apiKey', 'key_abcdef1234')).toBe('ke****34');
  });

  it('fully masks short values (<=4 chars)', () => {
    expect(sanitizeValue('token', 'ab')).toBe('****');
    expect(sanitizeValue('api_key', 'key')).toBe('****');
    expect(sanitizeValue('secret', 'abcd')).toBe('****');
  });

  it('hashes passwords with sha256', () => {
    const value = 'my-secret-password';
    const expectedHash = createHash('sha256').update(value).digest('hex').slice(0, 8);
    expect(sanitizeValue('password', value)).toBe(`[sha256:${expectedHash}]`);
  });

  it('hashes credentials with sha256', () => {
    const value = 'cred-12345';
    const expectedHash = createHash('sha256').update(value).digest('hex').slice(0, 8);
    expect(sanitizeValue('credential', value)).toBe(`[sha256:${expectedHash}]`);
  });

  it('fully masks short passwords', () => {
    expect(sanitizeValue('password', 'abc')).toBe('****');
  });

  it('is case-insensitive for key matching', () => {
    expect(sanitizeValue('TOKEN', 'abcdefgh')).toBe('ab****gh');
    expect(sanitizeValue('Api_Key', 'sk-12345678')).toBe('sk****78');
    expect(sanitizeValue('PASSWORD', 'longpassword')).toMatch(/^\[sha256:[a-f0-9]{8}\]$/);
    expect(sanitizeValue('Authorization', 'Bearer xyz')).toBe('Be****yz');
  });
});

describe('sanitizeObject', () => {
  it('returns null and undefined as-is', () => {
    expect(sanitizeObject(null)).toBeNull();
    expect(sanitizeObject(undefined)).toBeUndefined();
  });

  it('returns primitives as-is', () => {
    expect(sanitizeObject(42)).toBe(42);
    expect(sanitizeObject(true)).toBe(true);
    expect(sanitizeObject('hello')).toBe('hello');
  });

  it('sanitizes sensitive fields in flat objects', () => {
    const input = {
      name: 'test',
      token: 'abcdefgh',
      status: 'active',
    };
    const result = sanitizeObject(input) as Record<string, unknown>;
    expect(result.name).toBe('test');
    expect(result.token).toBe('ab****gh');
    expect(result.status).toBe('active');
  });

  it('sanitizes nested objects deeply', () => {
    const input = {
      user: {
        name: 'Alice',
        credentials: {
          password: 'supersecret123',
          api_key: 'sk-testkey1234',
        },
      },
    };
    const result = sanitizeObject(input) as any;
    expect(result.user.name).toBe('Alice');
    expect(result.user.credentials.password).toMatch(/^\[sha256:[a-f0-9]{8}\]$/);
    expect(result.user.credentials.api_key).toBe('sk****34');
  });

  it('sanitizes arrays of objects', () => {
    const input = [
      { token: 'token123456', name: 'a' },
      { token: 'token789012', name: 'b' },
    ];
    const result = sanitizeObject(input) as any[];
    expect(result[0].token).toBe('to****56');
    expect(result[0].name).toBe('a');
    expect(result[1].token).toBe('to****12');
    expect(result[1].name).toBe('b');
  });

  it('handles mixed nested structures', () => {
    const input = {
      detail: 'Not found',
      errors: [
        { field: 'authorization', value: 'Bearer expired-token-xyz' },
      ],
      meta: {
        secret: 'internal-secret-value',
      },
    };
    const result = sanitizeObject(input) as any;
    expect(result.detail).toBe('Not found');
    expect(result.errors[0].field).toBe('authorization');
    expect(result.errors[0].value).toBe('Bearer expired-token-xyz');
    expect(result.meta.secret).toBe('in****ue');
  });

  it('does not modify the original object', () => {
    const input = { token: 'abcdefgh', name: 'test' };
    sanitizeObject(input);
    expect(input.token).toBe('abcdefgh');
  });

  it('handles objects with non-string sensitive values', () => {
    const input = {
      token: 12345,
      api_key: null,
      secret: undefined,
    };
    const result = sanitizeObject(input) as Record<string, unknown>;
    expect(result.token).toBe(12345);
    expect(result.api_key).toBeNull();
    expect(result.secret).toBeUndefined();
  });
});
