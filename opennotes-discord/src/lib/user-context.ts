import type { GuildMember, User } from 'discord.js';
import { PermissionFlagsBits } from 'discord.js';

export interface UserContextData {
  userId: string;
  username?: string;
  displayName?: string;
  avatarUrl?: string;
  guildId?: string;
  hasManageServer?: boolean;
}

export function extractUserContext(user: User, guildId?: string | null, member?: GuildMember | null): UserContextData {
  return {
    userId: user.id,
    username: user.username,
    displayName: user.displayName ?? user.globalName ?? undefined,
    avatarUrl: user.displayAvatarURL(),
    guildId: guildId ?? undefined,
    hasManageServer: member?.permissions.has(PermissionFlagsBits.ManageGuild) ?? undefined,
  };
}
