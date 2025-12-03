export enum ConfigKey {
  // Command Visibility
  REQUEST_NOTE_EPHEMERAL = 'request_note_ephemeral',
  WRITE_NOTE_EPHEMERAL = 'write_note_ephemeral',
  RATE_NOTE_EPHEMERAL = 'rate_note_ephemeral',
  LIST_REQUESTS_EPHEMERAL = 'list_requests_ephemeral',
  STATUS_EPHEMERAL = 'status_ephemeral',

  // Feature Toggles
  NOTES_ENABLED = 'notes_enabled',
  RATINGS_ENABLED = 'ratings_enabled',
  REQUESTS_ENABLED = 'requests_enabled',

  // Rate Limiting
  NOTE_RATE_LIMIT = 'note_rate_limit',
  RATING_RATE_LIMIT = 'rating_rate_limit',
  REQUEST_RATE_LIMIT = 'request_rate_limit',

  // Notifications
  NOTIFY_NOTE_HELPFUL = 'notify_note_helpful',
  NOTIFY_REQUEST_FULFILLED = 'notify_request_fulfilled',
}

export type ConfigValue = boolean | number | string;

export interface ConfigDefinition {
  key: ConfigKey;
  type: 'boolean' | 'number' | 'string';
  default: ConfigValue;
  description: string;
  min?: number;
  max?: number;
  validValues?: string[];
}

export const CONFIG_SCHEMA: Record<ConfigKey, ConfigDefinition> = {
  // Command Visibility
  [ConfigKey.REQUEST_NOTE_EPHEMERAL]: {
    key: ConfigKey.REQUEST_NOTE_EPHEMERAL,
    type: 'boolean',
    default: true,
    description: 'Make /request-note responses private (visible only to requester)',
  },
  [ConfigKey.WRITE_NOTE_EPHEMERAL]: {
    key: ConfigKey.WRITE_NOTE_EPHEMERAL,
    type: 'boolean',
    default: false,
    description: 'Make /write-note responses private (visible only to author)',
  },
  [ConfigKey.RATE_NOTE_EPHEMERAL]: {
    key: ConfigKey.RATE_NOTE_EPHEMERAL,
    type: 'boolean',
    default: false,
    description: 'Make /rate-note responses private (visible only to rater)',
  },
  [ConfigKey.LIST_REQUESTS_EPHEMERAL]: {
    key: ConfigKey.LIST_REQUESTS_EPHEMERAL,
    type: 'boolean',
    default: true,
    description: 'Make /list-requests responses private (visible only to requester)',
  },
  [ConfigKey.STATUS_EPHEMERAL]: {
    key: ConfigKey.STATUS_EPHEMERAL,
    type: 'boolean',
    default: true,
    description: 'Make /status responses private (visible only to requester)',
  },

  // Feature Toggles
  [ConfigKey.NOTES_ENABLED]: {
    key: ConfigKey.NOTES_ENABLED,
    type: 'boolean',
    default: true,
    description: 'Enable community note creation in this server',
  },
  [ConfigKey.RATINGS_ENABLED]: {
    key: ConfigKey.RATINGS_ENABLED,
    type: 'boolean',
    default: true,
    description: 'Enable note rating functionality in this server',
  },
  [ConfigKey.REQUESTS_ENABLED]: {
    key: ConfigKey.REQUESTS_ENABLED,
    type: 'boolean',
    default: true,
    description: 'Enable note request functionality in this server',
  },

  // Rate Limiting
  [ConfigKey.NOTE_RATE_LIMIT]: {
    key: ConfigKey.NOTE_RATE_LIMIT,
    type: 'number',
    default: 5,
    min: 1,
    max: 100,
    description: 'Maximum notes per user per hour',
  },
  [ConfigKey.RATING_RATE_LIMIT]: {
    key: ConfigKey.RATING_RATE_LIMIT,
    type: 'number',
    default: 20,
    min: 1,
    max: 200,
    description: 'Maximum ratings per user per hour',
  },
  [ConfigKey.REQUEST_RATE_LIMIT]: {
    key: ConfigKey.REQUEST_RATE_LIMIT,
    type: 'number',
    default: 10,
    min: 1,
    max: 100,
    description: 'Maximum requests per user per hour',
  },

  // Notifications
  [ConfigKey.NOTIFY_NOTE_HELPFUL]: {
    key: ConfigKey.NOTIFY_NOTE_HELPFUL,
    type: 'boolean',
    default: true,
    description: 'Send DM when your note becomes helpful',
  },
  [ConfigKey.NOTIFY_REQUEST_FULFILLED]: {
    key: ConfigKey.NOTIFY_REQUEST_FULFILLED,
    type: 'boolean',
    default: true,
    description: 'Send DM when your request gets a note',
  },
};

export class ConfigValidator {
  static validate(key: ConfigKey, value: unknown): { valid: boolean; error?: string; parsedValue?: ConfigValue } {
    const schema = CONFIG_SCHEMA[key];

    if (!schema) {
      return { valid: false, error: `Unknown configuration key: ${key}` };
    }

    // Type validation
    switch (schema.type) {
      case 'boolean':
        if (typeof value === 'boolean') {
          return { valid: true, parsedValue: value };
        }
        if (value === 'true') {
          return { valid: true, parsedValue: true };
        }
        if (value === 'false') {
          return { valid: true, parsedValue: false };
        }
        return { valid: false, error: `${key} must be a boolean (true/false)` };

      case 'number': {
        const num = typeof value === 'number' ? value : parseFloat(String(value));
        if (isNaN(num)) {
          return { valid: false, error: `${key} must be a number` };
        }
        if (schema.min !== undefined && num < schema.min) {
          return { valid: false, error: `${key} must be at least ${schema.min}` };
        }
        if (schema.max !== undefined && num > schema.max) {
          return { valid: false, error: `${key} must be at most ${schema.max}` };
        }
        return { valid: true, parsedValue: num };
      }

      case 'string': {
        const str = String(value);
        if (schema.validValues && !schema.validValues.includes(str)) {
          return { valid: false, error: `${key} must be one of: ${schema.validValues.join(', ')}` };
        }
        return { valid: true, parsedValue: str };
      }

      default:
        return { valid: false, error: `Invalid schema type for ${key}` };
    }
  }

  static getDefault(key: ConfigKey): ConfigValue {
    return CONFIG_SCHEMA[key]?.default;
  }

  static getAllKeys(): ConfigKey[] {
    return Object.keys(CONFIG_SCHEMA) as ConfigKey[];
  }

  static getDescription(key: ConfigKey): string {
    return CONFIG_SCHEMA[key]?.description || 'No description available';
  }
}
