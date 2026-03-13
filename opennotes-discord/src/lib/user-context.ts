import type { GuildMember, User } from 'discord.js';
import { PermissionFlagsBits } from 'discord.js';

export interface UserContextData {
  userId: string;
  username?: string;
  displayName?: string;
  avatarUrl?: string;
  guildId?: string;
  channelId?: string;
  hasManageServer?: boolean;
}

function extractManageServerPermission(member?: GuildMember | null): boolean | undefined {
  const permissions = member?.permissions as
    | { has?: (permission: bigint) => boolean; bitfield?: bigint | string | number }
    | string
    | null
    | undefined;

  if (permissions === null || permissions === undefined) {
    return undefined;
  }

  if (typeof permissions === 'object' && typeof permissions.has === 'function') {
    return permissions.has(PermissionFlagsBits.ManageGuild);
  }

  const rawPermissions = typeof permissions === 'string'
    ? permissions
    : permissions.bitfield;

  if (rawPermissions === null || rawPermissions === undefined) {
    return undefined;
  }

  try {
    return (BigInt(rawPermissions) & PermissionFlagsBits.ManageGuild) === PermissionFlagsBits.ManageGuild;
  } catch {
    return undefined;
  }
}

export function extractUserContext(user: User, guildId?: string | null, member?: GuildMember | null, channelId?: string | null): UserContextData {
  return {
    userId: user.id,
    username: user.username,
    displayName: ('displayName' in user ? user.displayName : undefined) ?? user.globalName ?? undefined,
    avatarUrl: typeof user.displayAvatarURL === 'function' ? user.displayAvatarURL() : undefined,
    guildId: guildId ?? undefined,
    channelId: channelId ?? undefined,
    hasManageServer: extractManageServerPermission(member),
  };
}
