import { PermissionFlagsBits } from 'discord.js';
import { config } from '../config.js';

const MINIMAL_PERMISSIONS =
  PermissionFlagsBits.SendMessages |
  PermissionFlagsBits.EmbedLinks |
  PermissionFlagsBits.UseApplicationCommands |
  PermissionFlagsBits.ViewChannel |
  PermissionFlagsBits.CreatePublicThreads |
  PermissionFlagsBits.SendMessagesInThreads;

const FULL_PERMISSIONS =
  MINIMAL_PERMISSIONS |
  PermissionFlagsBits.ManageChannels |
  PermissionFlagsBits.ManageMessages;

const OAUTH2_SCOPES = 'bot%20applications.commands';

export function getMinimalInstallUrl(): string {
  return `https://discord.com/api/oauth2/authorize?client_id=${config.clientId}&permissions=${MINIMAL_PERMISSIONS}&scope=${OAUTH2_SCOPES}`;
}

export function getFullInstallUrl(): string {
  return `https://discord.com/api/oauth2/authorize?client_id=${config.clientId}&permissions=${FULL_PERMISSIONS}&scope=${OAUTH2_SCOPES}`;
}

export function getUpgradeUrl(guildId: string): string {
  return `https://discord.com/api/oauth2/authorize?client_id=${config.clientId}&permissions=${FULL_PERMISSIONS}&scope=${OAUTH2_SCOPES}&guild_id=${guildId}&disable_guild_select=true`;
}

export const PERMISSION_VALUES = {
  minimal: MINIMAL_PERMISSIONS,
  full: FULL_PERMISSIONS,
} as const;
