import { GuildMember, PermissionFlagsBits } from 'discord.js';

export function hasManageGuildPermission(member: GuildMember | null): boolean {
  if (!member) {
    return false;
  }

  return member.permissions.has(PermissionFlagsBits.ManageGuild);
}
