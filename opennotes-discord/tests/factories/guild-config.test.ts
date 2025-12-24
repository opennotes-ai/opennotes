import { guildConfigFactory, type GuildConfig } from './guild-config.js';
import { ConfigKey, CONFIG_SCHEMA } from '../../src/lib/config-schema.js';

describe('guildConfigFactory', () => {
  describe('basic factory creation', () => {
    it('should create a config object with all keys populated', () => {
      const config = guildConfigFactory.build();

      for (const key of Object.values(ConfigKey)) {
        expect(config[key]).toBeDefined();
      }
    });

    it('should use default values from CONFIG_SCHEMA', () => {
      const config = guildConfigFactory.build();

      expect(config[ConfigKey.REQUEST_NOTE_EPHEMERAL]).toBe(CONFIG_SCHEMA[ConfigKey.REQUEST_NOTE_EPHEMERAL].default);
      expect(config[ConfigKey.NOTE_RATE_LIMIT]).toBe(CONFIG_SCHEMA[ConfigKey.NOTE_RATE_LIMIT].default);
      expect(config[ConfigKey.BOT_CHANNEL_NAME]).toBe(CONFIG_SCHEMA[ConfigKey.BOT_CHANNEL_NAME].default);
    });

    it('should create unique instances', () => {
      const config1 = guildConfigFactory.build();
      const config2 = guildConfigFactory.build();

      expect(config1).not.toBe(config2);
    });
  });

  describe('individual key overrides', () => {
    it('should allow overriding individual keys', () => {
      const config = guildConfigFactory.build({
        [ConfigKey.REQUEST_NOTE_EPHEMERAL]: false,
        [ConfigKey.NOTE_RATE_LIMIT]: 50,
      });

      expect(config[ConfigKey.REQUEST_NOTE_EPHEMERAL]).toBe(false);
      expect(config[ConfigKey.NOTE_RATE_LIMIT]).toBe(50);
    });

    it('should preserve other defaults when overriding', () => {
      const config = guildConfigFactory.build({
        [ConfigKey.NOTES_ENABLED]: false,
      });

      expect(config[ConfigKey.NOTES_ENABLED]).toBe(false);
      expect(config[ConfigKey.RATINGS_ENABLED]).toBe(CONFIG_SCHEMA[ConfigKey.RATINGS_ENABLED].default);
    });
  });

  describe('allEphemeral transient param', () => {
    it('should set all ephemeral settings to true', () => {
      const config = guildConfigFactory.build({}, { transient: { allEphemeral: true } });

      expect(config[ConfigKey.REQUEST_NOTE_EPHEMERAL]).toBe(true);
      expect(config[ConfigKey.WRITE_NOTE_EPHEMERAL]).toBe(true);
      expect(config[ConfigKey.RATE_NOTE_EPHEMERAL]).toBe(true);
      expect(config[ConfigKey.LIST_REQUESTS_EPHEMERAL]).toBe(true);
      expect(config[ConfigKey.STATUS_EPHEMERAL]).toBe(true);
    });

    it('should set all ephemeral settings to false', () => {
      const config = guildConfigFactory.build({}, { transient: { allEphemeral: false } });

      expect(config[ConfigKey.REQUEST_NOTE_EPHEMERAL]).toBe(false);
      expect(config[ConfigKey.WRITE_NOTE_EPHEMERAL]).toBe(false);
      expect(config[ConfigKey.RATE_NOTE_EPHEMERAL]).toBe(false);
      expect(config[ConfigKey.LIST_REQUESTS_EPHEMERAL]).toBe(false);
      expect(config[ConfigKey.STATUS_EPHEMERAL]).toBe(false);
    });
  });

  describe('allFeaturesEnabled transient param', () => {
    it('should enable all features', () => {
      const config = guildConfigFactory.build({}, { transient: { allFeaturesEnabled: true } });

      expect(config[ConfigKey.NOTES_ENABLED]).toBe(true);
      expect(config[ConfigKey.RATINGS_ENABLED]).toBe(true);
      expect(config[ConfigKey.REQUESTS_ENABLED]).toBe(true);
    });

    it('should disable all features', () => {
      const config = guildConfigFactory.build({}, { transient: { allFeaturesEnabled: false } });

      expect(config[ConfigKey.NOTES_ENABLED]).toBe(false);
      expect(config[ConfigKey.RATINGS_ENABLED]).toBe(false);
      expect(config[ConfigKey.REQUESTS_ENABLED]).toBe(false);
    });
  });

  describe('allNotifications transient param', () => {
    it('should enable all notifications', () => {
      const config = guildConfigFactory.build({}, { transient: { allNotifications: true } });

      expect(config[ConfigKey.NOTIFY_NOTE_HELPFUL]).toBe(true);
      expect(config[ConfigKey.NOTIFY_REQUEST_FULFILLED]).toBe(true);
    });

    it('should disable all notifications', () => {
      const config = guildConfigFactory.build({}, { transient: { allNotifications: false } });

      expect(config[ConfigKey.NOTIFY_NOTE_HELPFUL]).toBe(false);
      expect(config[ConfigKey.NOTIFY_REQUEST_FULFILLED]).toBe(false);
    });
  });

  describe('uniformRateLimit transient param', () => {
    it('should set all rate limits to the same value', () => {
      const config = guildConfigFactory.build({}, { transient: { uniformRateLimit: 25 } });

      expect(config[ConfigKey.NOTE_RATE_LIMIT]).toBe(25);
      expect(config[ConfigKey.RATING_RATE_LIMIT]).toBe(25);
      expect(config[ConfigKey.REQUEST_RATE_LIMIT]).toBe(25);
    });
  });

  describe('combined transient params and overrides', () => {
    it('should apply transient params and then overrides', () => {
      const config = guildConfigFactory.build(
        { [ConfigKey.REQUEST_NOTE_EPHEMERAL]: false },
        { transient: { allEphemeral: true } }
      );

      expect(config[ConfigKey.REQUEST_NOTE_EPHEMERAL]).toBe(false);
      expect(config[ConfigKey.WRITE_NOTE_EPHEMERAL]).toBe(true);
    });

    it('should support multiple transient params', () => {
      const config = guildConfigFactory.build(
        {},
        {
          transient: {
            allEphemeral: false,
            allFeaturesEnabled: true,
            uniformRateLimit: 10,
          },
        }
      );

      expect(config[ConfigKey.REQUEST_NOTE_EPHEMERAL]).toBe(false);
      expect(config[ConfigKey.NOTES_ENABLED]).toBe(true);
      expect(config[ConfigKey.NOTE_RATE_LIMIT]).toBe(10);
    });
  });

  describe('buildList', () => {
    it('should create multiple unique config objects', () => {
      const configs = guildConfigFactory.buildList(3);

      expect(configs).toHaveLength(3);
      expect(configs[0]).not.toBe(configs[1]);
      expect(configs[1]).not.toBe(configs[2]);
    });

    it('should support overrides in buildList', () => {
      const configs = guildConfigFactory.buildList(2, {
        [ConfigKey.NOTES_ENABLED]: false,
      });

      expect(configs[0][ConfigKey.NOTES_ENABLED]).toBe(false);
      expect(configs[1][ConfigKey.NOTES_ENABLED]).toBe(false);
    });
  });
});
