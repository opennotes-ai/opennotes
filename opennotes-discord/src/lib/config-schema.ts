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

  // Bot Channel
  BOT_CHANNEL_NAME = 'bot_channel_name',
  OPENNOTES_ROLE_NAME = 'opennotes_role_name',

  // Debug
  VIBECHECK_DEBUG_MODE = 'vibecheck_debug_mode',
}

export type ConfigValue = boolean | number | string;

export interface ConfigDefinition {
  key: ConfigKey;
  type: 'boolean' | 'number' | 'string';
  default: ConfigValue;
  shortName: string;
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
    shortName: 'Request Note Privacy',
    description: 'Make /note request responses private (visible only to requester)',
  },
  [ConfigKey.WRITE_NOTE_EPHEMERAL]: {
    key: ConfigKey.WRITE_NOTE_EPHEMERAL,
    type: 'boolean',
    default: false,
    shortName: 'Write Note Privacy',
    description: 'Make /note write responses private (visible only to author)',
  },
  [ConfigKey.RATE_NOTE_EPHEMERAL]: {
    key: ConfigKey.RATE_NOTE_EPHEMERAL,
    type: 'boolean',
    default: false,
    shortName: 'Rate Note Privacy',
    description: 'Make /note rate responses private (visible only to rater)',
  },
  [ConfigKey.LIST_REQUESTS_EPHEMERAL]: {
    key: ConfigKey.LIST_REQUESTS_EPHEMERAL,
    type: 'boolean',
    default: true,
    shortName: 'List Requests Privacy',
    description: 'Make /list requests responses private (visible only to requester)',
  },
  [ConfigKey.STATUS_EPHEMERAL]: {
    key: ConfigKey.STATUS_EPHEMERAL,
    type: 'boolean',
    default: true,
    shortName: 'Status Privacy',
    description: 'Make /status-bot responses private (visible only to requester)',
  },

  // Feature Toggles
  [ConfigKey.NOTES_ENABLED]: {
    key: ConfigKey.NOTES_ENABLED,
    type: 'boolean',
    default: true,
    shortName: 'Notes Enabled',
    description: 'Enable community note creation in this server',
  },
  [ConfigKey.RATINGS_ENABLED]: {
    key: ConfigKey.RATINGS_ENABLED,
    type: 'boolean',
    default: true,
    shortName: 'Ratings Enabled',
    description: 'Enable note rating functionality in this server',
  },
  [ConfigKey.REQUESTS_ENABLED]: {
    key: ConfigKey.REQUESTS_ENABLED,
    type: 'boolean',
    default: true,
    shortName: 'Requests Enabled',
    description: 'Enable note request functionality in this server',
  },

  // Rate Limiting
  [ConfigKey.NOTE_RATE_LIMIT]: {
    key: ConfigKey.NOTE_RATE_LIMIT,
    type: 'number',
    default: 5,
    min: 1,
    max: 100,
    shortName: 'Note Rate Limit',
    description: 'Maximum notes per user per hour',
  },
  [ConfigKey.RATING_RATE_LIMIT]: {
    key: ConfigKey.RATING_RATE_LIMIT,
    type: 'number',
    default: 20,
    min: 1,
    max: 200,
    shortName: 'Rating Rate Limit',
    description: 'Maximum ratings per user per hour',
  },
  [ConfigKey.REQUEST_RATE_LIMIT]: {
    key: ConfigKey.REQUEST_RATE_LIMIT,
    type: 'number',
    default: 10,
    min: 1,
    max: 100,
    shortName: 'Request Rate Limit',
    description: 'Maximum requests per user per hour',
  },

  // Notifications
  [ConfigKey.NOTIFY_NOTE_HELPFUL]: {
    key: ConfigKey.NOTIFY_NOTE_HELPFUL,
    type: 'boolean',
    default: true,
    shortName: 'Helpful Note DM',
    description: 'Send DM when your note becomes helpful',
  },
  [ConfigKey.NOTIFY_REQUEST_FULFILLED]: {
    key: ConfigKey.NOTIFY_REQUEST_FULFILLED,
    type: 'boolean',
    default: true,
    shortName: 'Request Fulfilled DM',
    description: 'Send DM when your request gets a note',
  },

  // Bot Channel
  [ConfigKey.BOT_CHANNEL_NAME]: {
    key: ConfigKey.BOT_CHANNEL_NAME,
    type: 'string',
    default: 'open-notes',
    shortName: 'Bot Channel Name',
    description: 'Name of the dedicated OpenNotes bot channel',
  },
  [ConfigKey.OPENNOTES_ROLE_NAME]: {
    key: ConfigKey.OPENNOTES_ROLE_NAME,
    type: 'string',
    default: 'OpenNotes',
    shortName: 'OpenNotes Role',
    description: 'Name of the role that can send messages in the bot channel',
  },

  // Debug
  [ConfigKey.VIBECHECK_DEBUG_MODE]: {
    key: ConfigKey.VIBECHECK_DEBUG_MODE,
    type: 'boolean',
    default: false,
    shortName: 'Vibecheck Debug',
    description: 'Enable debug mode to echo vibecheck progress and scores to bot channel',
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

  static parseValue(key: ConfigKey, value: unknown): ConfigValue {
    const schema = CONFIG_SCHEMA[key];
    if (!schema) {
      return String(value);
    }

    switch (schema.type) {
      case 'boolean': {
        if (typeof value === 'boolean') {
          return value;
        }
        if (value === 'true' || value === '1' || value === 'yes') {
          return true;
        }
        if (value === 'false' || value === '0' || value === 'no') {
          return false;
        }
        return schema.default as boolean;
      }

      case 'number': {
        if (typeof value === 'number') {
          return value;
        }
        const num = parseFloat(String(value));
        return isNaN(num) ? (schema.default as number) : num;
      }

      case 'string':
      default:
        return String(value);
    }
  }
}
