import { describe, it, expect } from '@jest/globals';
import { safeJSONParse, safeJSONStringify, isValidJSON, SafeJSONError } from '../../src/utils/safe-json.js';

describe('Safe JSON Utilities', () => {
  describe('safeJSONParse', () => {
    it('should parse valid JSON', () => {
      const json = '{"name": "test", "value": 123}';
      const result = safeJSONParse(json);
      expect(result).toEqual({ name: 'test', value: 123 });
    });

    it('should parse arrays', () => {
      const json = '[1, 2, 3, 4, 5]';
      const result = safeJSONParse<number[]>(json);
      expect(result).toEqual([1, 2, 3, 4, 5]);
    });

    it('should block __proto__ in JSON', () => {
      const maliciousJSON = '{"__proto__": {"polluted": true}, "safe": "value"}';
      const result = safeJSONParse(maliciousJSON) as Record<string, unknown>;

      expect(result).toEqual({ safe: 'value' });
      expect(Object.hasOwn(result, '__proto__')).toBe(false);
      expect(Object.prototype).not.toHaveProperty('polluted');
    });

    it('should block constructor in JSON', () => {
      const maliciousJSON = '{"constructor": {"polluted": true}, "safe": "value"}';
      const result = safeJSONParse(maliciousJSON) as Record<string, unknown>;

      expect(result).toEqual({ safe: 'value' });
      expect(Object.hasOwn(result, 'constructor')).toBe(false);
    });

    it('should block prototype in JSON', () => {
      const maliciousJSON = '{"prototype": {"polluted": true}, "safe": "value"}';
      const result = safeJSONParse(maliciousJSON);

      expect(result).toEqual({ safe: 'value' });
      expect(result).not.toHaveProperty('prototype');
    });

    it('should block nested dangerous keys', () => {
      const maliciousJSON = '{"level1": {"level2": {"__proto__": {"polluted": true}, "safe": "value"}}}';
      const result = safeJSONParse(maliciousJSON);

      expect(result).toEqual({ level1: { level2: { safe: 'value' } } });
      expect(Object.prototype).not.toHaveProperty('polluted');
    });

    it('should block dangerous keys in arrays', () => {
      const maliciousJSON = '[{"__proto__": {"polluted": true}}, {"safe": "value"}]';
      const result = safeJSONParse(maliciousJSON);

      expect(result).toEqual([{}, { safe: 'value' }]);
      expect(Object.prototype).not.toHaveProperty('polluted');
    });

    it('should validate data when validation function is provided', () => {
      const json = '{"type": "note", "content": "test"}';
      const result = safeJSONParse(json, {
        validate: (data) => {
          return typeof data === 'object' && data !== null && 'type' in data;
        },
      });

      expect(result).toEqual({ type: 'note', content: 'test' });
    });

    it('should throw SafeJSONError when validation fails', () => {
      const json = '{"missing": "type"}';

      expect(() => {
        safeJSONParse(json, {
          validate: (data) => {
            return typeof data === 'object' && data !== null && 'type' in data;
          },
        });
      }).toThrow(SafeJSONError);
    });

    it('should throw SafeJSONError for invalid JSON', () => {
      const invalidJSON = '{invalid json}';

      expect(() => {
        safeJSONParse(invalidJSON);
      }).toThrow(SafeJSONError);
    });

    it('should allow disabling sanitization', () => {
      const json = '{"__proto__": {"test": true}}';
      const result = safeJSONParse(json, { sanitize: false }) as Record<string, unknown>;

      expect(Object.hasOwn(result, '__proto__')).toBe(false);
    });

    it('should handle complex nested structures', () => {
      const json = JSON.stringify({
        user: {
          name: 'Alice',
          settings: {
            theme: 'dark',
            notifications: ['email', 'sms'],
          },
        },
        metadata: {
          created: '2025-01-01',
          tags: ['important', 'urgent'],
        },
      });

      const result = safeJSONParse(json);

      expect(result).toEqual({
        user: {
          name: 'Alice',
          settings: {
            theme: 'dark',
            notifications: ['email', 'sms'],
          },
        },
        metadata: {
          created: '2025-01-01',
          tags: ['important', 'urgent'],
        },
      });
    });
  });

  describe('safeJSONStringify', () => {
    it('should stringify objects', () => {
      const obj = { name: 'test', value: 123 };
      const result = safeJSONStringify(obj);
      expect(result).toBe('{"name":"test","value":123}');
    });

    it('should stringify arrays', () => {
      const arr = [1, 2, 3, 4, 5];
      const result = safeJSONStringify(arr);
      expect(result).toBe('[1,2,3,4,5]');
    });

    it('should handle nested structures', () => {
      const obj = { outer: { inner: { value: 'test' } } };
      const result = safeJSONStringify(obj);
      expect(result).toBe('{"outer":{"inner":{"value":"test"}}}');
    });

    it('should throw SafeJSONError for circular references', () => {
      const circular: Record<string, unknown> = { name: 'circular' };
      circular.self = circular;

      expect(() => {
        safeJSONStringify(circular);
      }).toThrow(SafeJSONError);
    });
  });

  describe('isValidJSON', () => {
    it('should return true for valid JSON', () => {
      expect(isValidJSON('{"valid": true}')).toBe(true);
      expect(isValidJSON('[1, 2, 3]')).toBe(true);
      expect(isValidJSON('"string"')).toBe(true);
      expect(isValidJSON('123')).toBe(true);
      expect(isValidJSON('true')).toBe(true);
      expect(isValidJSON('null')).toBe(true);
    });

    it('should return false for invalid JSON', () => {
      expect(isValidJSON('{invalid}')).toBe(false);
      expect(isValidJSON('undefined')).toBe(false);
      expect(isValidJSON('')).toBe(false);
      expect(isValidJSON('{"unclosed":')).toBe(false);
    });
  });

  describe('Prototype Pollution Prevention', () => {
    it('should prevent Object.prototype pollution via __proto__', () => {
      const beforePollution = Object.prototype.hasOwnProperty('polluted');
      expect(beforePollution).toBe(false);

      const maliciousJSON = '{"__proto__": {"polluted": "yes"}}';
      safeJSONParse(maliciousJSON);

      const afterParsing = Object.prototype.hasOwnProperty('polluted');
      expect(afterParsing).toBe(false);
    });

    it('should prevent constructor pollution', () => {
      const maliciousJSON = '{"constructor": {"prototype": {"polluted": "yes"}}}';
      const result = safeJSONParse(maliciousJSON) as Record<string, unknown>;

      expect(Object.hasOwn(result, 'constructor')).toBe(false);
      expect(Object.prototype).not.toHaveProperty('polluted');
    });

    it('should handle multiple pollution attempts in same JSON', () => {
      const maliciousJSON = `{
        "__proto__": {"polluted1": true},
        "safe": "value",
        "nested": {
          "__proto__": {"polluted2": true},
          "constructor": {"polluted3": true}
        }
      }`;

      const result = safeJSONParse(maliciousJSON);

      expect(result).toEqual({
        safe: 'value',
        nested: {},
      });
      expect(Object.prototype).not.toHaveProperty('polluted1');
      expect(Object.prototype).not.toHaveProperty('polluted2');
      expect(Object.prototype).not.toHaveProperty('polluted3');
    });
  });

  describe('SafeJSONError', () => {
    it('should include error details', () => {
      try {
        safeJSONParse('{invalid}');
      } catch (error) {
        expect(error).toBeInstanceOf(SafeJSONError);
        expect(error).toHaveProperty('name', 'SafeJSONError');
        expect(error).toHaveProperty('message');
      }
    });

    it('should include cause when available', () => {
      const invalidJSON = '{invalid}';
      try {
        safeJSONParse(invalidJSON);
      } catch (error) {
        if (error instanceof SafeJSONError) {
          expect(error.cause).toBeDefined();
        }
      }
    });
  });
});
