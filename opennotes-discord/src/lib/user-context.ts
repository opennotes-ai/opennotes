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

export function extractUserContext(user: User, guildId?: string | null, member?: GuildMember | null, channelId?: string | null): UserContextData {
  return {
    userId: user.id,
    username: user.username,
    displayName: user.displayName ?? user.globalName ?? undefined,
    avatarUrl: user.displayAvatarURL(),
    guildId: guildId ?? undefined,
    channelId: channelId ?? undefined,
    hasManageServer: member?.permissions.has(PermissionFlagsBits.ManageGuild) ?? undefined,
  };
}
