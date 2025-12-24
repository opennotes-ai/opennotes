import { Factory } from 'fishery';
import { jest } from '@jest/globals';

export interface MockDiscordUser {
  id: string;
  username: string;
  displayName: string;
  globalName: string | null;
  tag: string;
  bot: boolean;
  displayAvatarURL: ReturnType<typeof jest.fn<(options?: { size?: number }) => string>>;
}

export interface DiscordUserTransientParams {
  avatarUrl?: string;
}

export const discordUserFactory = Factory.define<MockDiscordUser, DiscordUserTransientParams>(
  ({ sequence, transientParams }) => {
    const { avatarUrl = `https://cdn.discordapp.com/avatars/user-${sequence}/avatar.png` } = transientParams;
    const username = `user${sequence}`;

    return {
      id: `user-${sequence}`,
      username,
      displayName: `User ${sequence}`,
      globalName: `User ${sequence}`,
      tag: `${username}#0000`,
      bot: false,
      displayAvatarURL: jest.fn<(options?: { size?: number }) => string>().mockReturnValue(avatarUrl),
    };
  }
);
