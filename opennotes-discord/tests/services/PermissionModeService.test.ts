import { describe, it, expect, beforeEach, jest } from '@jest/globals';
import { PermissionFlagsBits } from 'discord.js';
import {
  discordGuildFactory,
  discordMemberFactory,
  discordUserFactory,
  loggerFactory,
} from '../factories/index.js';

const mockLogger = loggerFactory.build();

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
}));

const { PermissionModeService } = await import('../../src/services/PermissionModeService.js');

describe('PermissionModeService', () => {
  let service: InstanceType<typeof PermissionModeService>;

  beforeEach(() => {
    service = new PermissionModeService();
    jest.clearAllMocks();
  });

  describe('detectMode', () => {
    it('should return "full" when bot has both ManageChannels and ManageMessages', () => {
      const botMember = discordMemberFactory.build(
        {},
        {
          transient: {
            permissionOverrides: {
              [PermissionFlagsBits.ManageChannels.toString()]: true,
              [PermissionFlagsBits.ManageMessages.toString()]: true,
            },
          },
          associations: {
            user: discordUserFactory.build({ id: 'bot-user', bot: true }),
          },
        }
      );

      const guild = discordGuildFactory.build(
        { id: 'guild-123' },
        { transient: { botMember } }
      );

      const mode = service.detectMode(guild as any);

      expect(mode).toBe('full');
      expect(mockLogger.debug).toHaveBeenCalledWith(
        'Detected installation mode',
        expect.objectContaining({
          guildId: 'guild-123',
          mode: 'full',
          hasManageChannels: true,
          hasManageMessages: true,
        })
      );
    });

    it('should return "minimal" when bot lacks ManageChannels', () => {
      const botMember = discordMemberFactory.build(
        {},
        {
          transient: {
            permissionOverrides: {
              [PermissionFlagsBits.ManageMessages.toString()]: true,
            },
          },
          associations: {
            user: discordUserFactory.build({ id: 'bot-user', bot: true }),
          },
        }
      );

      const guild = discordGuildFactory.build(
        { id: 'guild-456' },
        { transient: { botMember } }
      );

      const mode = service.detectMode(guild as any);

      expect(mode).toBe('minimal');
      expect(mockLogger.debug).toHaveBeenCalledWith(
        'Detected installation mode',
        expect.objectContaining({
          guildId: 'guild-456',
          mode: 'minimal',
          hasManageChannels: false,
          hasManageMessages: true,
        })
      );
    });

    it('should return "minimal" when bot lacks ManageMessages', () => {
      const botMember = discordMemberFactory.build(
        {},
        {
          transient: {
            permissionOverrides: {
              [PermissionFlagsBits.ManageChannels.toString()]: true,
            },
          },
          associations: {
            user: discordUserFactory.build({ id: 'bot-user', bot: true }),
          },
        }
      );

      const guild = discordGuildFactory.build(
        { id: 'guild-789' },
        { transient: { botMember } }
      );

      const mode = service.detectMode(guild as any);

      expect(mode).toBe('minimal');
    });

    it('should return "minimal" when bot member is not available', () => {
      const guild = discordGuildFactory.build(
        { id: 'guild-no-bot' },
        { transient: { noBotMember: true } }
      );

      const mode = service.detectMode(guild as any);

      expect(mode).toBe('minimal');
      expect(mockLogger.warn).toHaveBeenCalledWith(
        'Bot member not available, defaulting to minimal mode',
        expect.objectContaining({ guildId: 'guild-no-bot' })
      );
    });

    it('should return "minimal" when bot has no special permissions', () => {
      const botMember = discordMemberFactory.build(
        {},
        {
          associations: {
            user: discordUserFactory.build({ id: 'bot-user', bot: true }),
          },
        }
      );

      const guild = discordGuildFactory.build(
        { id: 'guild-basic' },
        { transient: { botMember } }
      );

      const mode = service.detectMode(guild as any);

      expect(mode).toBe('minimal');
    });
  });

  describe('hasFullPermissions', () => {
    it('should return true when mode is full', () => {
      const botMember = discordMemberFactory.build(
        {},
        {
          transient: {
            permissionOverrides: {
              [PermissionFlagsBits.ManageChannels.toString()]: true,
              [PermissionFlagsBits.ManageMessages.toString()]: true,
            },
          },
          associations: {
            user: discordUserFactory.build({ id: 'bot-user', bot: true }),
          },
        }
      );

      const guild = discordGuildFactory.build(
        { id: 'guild-full' },
        { transient: { botMember } }
      );

      expect(service.hasFullPermissions(guild as any)).toBe(true);
    });

    it('should return false when mode is minimal', () => {
      const guild = discordGuildFactory.build({ id: 'guild-minimal' });

      expect(service.hasFullPermissions(guild as any)).toBe(false);
    });
  });
});
