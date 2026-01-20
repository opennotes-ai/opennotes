import { Guild, PermissionFlagsBits } from 'discord.js';
import { logger } from '../logger.js';

export type InstallationMode = 'minimal' | 'full';

export class PermissionModeService {
  detectMode(guild: Guild): InstallationMode {
    const botMember = guild.members.me;

    if (!botMember) {
      logger.warn('Bot member not available, defaulting to minimal mode', {
        guildId: guild.id,
      });
      return 'minimal';
    }

    const hasManageChannels = botMember.permissions.has(PermissionFlagsBits.ManageChannels);
    const hasManageMessages = botMember.permissions.has(PermissionFlagsBits.ManageMessages);

    const mode: InstallationMode = hasManageChannels && hasManageMessages ? 'full' : 'minimal';

    logger.debug('Detected installation mode', {
      guildId: guild.id,
      mode,
      hasManageChannels,
      hasManageMessages,
    });

    return mode;
  }

  hasFullPermissions(guild: Guild): boolean {
    return this.detectMode(guild) === 'full';
  }
}
