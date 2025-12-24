import { Factory } from 'fishery';
import { ConfigKey, CONFIG_SCHEMA, type ConfigValue } from '../../src/lib/config-schema.js';

export type GuildConfig = Record<ConfigKey, ConfigValue>;

export interface GuildConfigTransientParams {
  allEphemeral?: boolean;
  allFeaturesEnabled?: boolean;
  allNotifications?: boolean;
  uniformRateLimit?: number;
}

function getDefaults(): GuildConfig {
  const defaults = {} as GuildConfig;
  for (const key of Object.values(ConfigKey)) {
    defaults[key] = CONFIG_SCHEMA[key].default;
  }
  return defaults;
}

export const guildConfigFactory = Factory.define<GuildConfig, GuildConfigTransientParams>(
  ({ transientParams }) => {
    const { allEphemeral, allFeaturesEnabled, allNotifications, uniformRateLimit } = transientParams;

    const config = getDefaults();

    if (allEphemeral !== undefined) {
      config[ConfigKey.REQUEST_NOTE_EPHEMERAL] = allEphemeral;
      config[ConfigKey.WRITE_NOTE_EPHEMERAL] = allEphemeral;
      config[ConfigKey.RATE_NOTE_EPHEMERAL] = allEphemeral;
      config[ConfigKey.LIST_REQUESTS_EPHEMERAL] = allEphemeral;
      config[ConfigKey.STATUS_EPHEMERAL] = allEphemeral;
    }

    if (allFeaturesEnabled !== undefined) {
      config[ConfigKey.NOTES_ENABLED] = allFeaturesEnabled;
      config[ConfigKey.RATINGS_ENABLED] = allFeaturesEnabled;
      config[ConfigKey.REQUESTS_ENABLED] = allFeaturesEnabled;
    }

    if (allNotifications !== undefined) {
      config[ConfigKey.NOTIFY_NOTE_HELPFUL] = allNotifications;
      config[ConfigKey.NOTIFY_REQUEST_FULFILLED] = allNotifications;
    }

    if (uniformRateLimit !== undefined) {
      config[ConfigKey.NOTE_RATE_LIMIT] = uniformRateLimit;
      config[ConfigKey.RATING_RATE_LIMIT] = uniformRateLimit;
      config[ConfigKey.REQUEST_RATE_LIMIT] = uniformRateLimit;
    }

    return config;
  }
);
