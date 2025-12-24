import { Factory } from 'fishery';
import { jest } from '@jest/globals';
import { PermissionFlagsBits } from 'discord.js';
import { discordUserFactory, type MockDiscordUser } from './discord-user.js';

export interface MockDiscordMember {
  id: string;
  user: MockDiscordUser;
  displayName: string;
  permissions: {
    has: ReturnType<typeof jest.fn<(permission: bigint | string) => boolean>>;
  };
  roles: {
    cache: Map<string, { id: string; name: string }>;
    highest: { id: string; name: string };
  };
}

export interface DiscordMemberTransientParams {
  hasManageGuild?: boolean;
  hasAdministrator?: boolean;
  permissionOverrides?: Record<string, boolean>;
}

export const discordMemberFactory = Factory.define<MockDiscordMember, DiscordMemberTransientParams>(
  ({ sequence, transientParams, associations }) => {
    const {
      hasManageGuild = false,
      hasAdministrator = false,
      permissionOverrides = {},
    } = transientParams;

    const user = associations.user ?? discordUserFactory.build();
    const rolesCache = new Map<string, { id: string; name: string }>();
    rolesCache.set(`role-${sequence}`, { id: `role-${sequence}`, name: `Role ${sequence}` });

    const permissionsHas = jest.fn<(permission: bigint | string) => boolean>((permission) => {
      if (hasAdministrator && permission === PermissionFlagsBits.Administrator) {
        return true;
      }
      if (hasManageGuild && permission === PermissionFlagsBits.ManageGuild) {
        return true;
      }

      const permKey = typeof permission === 'bigint' ? permission.toString() : permission;
      if (permKey in permissionOverrides) {
        return permissionOverrides[permKey];
      }

      if (hasAdministrator) {
        return true;
      }

      return false;
    });

    return {
      id: user.id,
      user,
      displayName: user.displayName,
      permissions: {
        has: permissionsHas,
      },
      roles: {
        cache: rolesCache,
        highest: { id: `role-${sequence}`, name: `Role ${sequence}` },
      },
    };
  }
);

export const adminMemberFactory = discordMemberFactory.transient({
  hasManageGuild: true,
});
