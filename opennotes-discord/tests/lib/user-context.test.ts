import { extractUserContext } from '../../src/lib/user-context.js';
import type { User } from 'discord.js';

describe('extractUserContext', () => {
  it('should extract user context from Discord user', () => {
    const mockUser = {
      id: '123456789',
      username: 'testuser',
      displayName: 'Test User',
      globalName: 'Test Global',
      displayAvatarURL: () => 'https://cdn.discordapp.com/avatars/123456789/avatar.png',
    } as unknown as User;

    const guildId = '987654321';
    const context = extractUserContext(mockUser, guildId);

    expect(context).toEqual({
      userId: '123456789',
      username: 'testuser',
      displayName: 'Test User',
      avatarUrl: 'https://cdn.discordapp.com/avatars/123456789/avatar.png',
      guildId: '987654321',
    });
  });

  it('should use globalName when displayName is not available', () => {
    const mockUser = {
      id: '123456789',
      username: 'testuser',
      displayName: null,
      globalName: 'Test Global',
      displayAvatarURL: () => 'https://cdn.discordapp.com/avatars/123456789/avatar.png',
    } as unknown as User;

    const context = extractUserContext(mockUser, null);

    expect(context).toEqual({
      userId: '123456789',
      username: 'testuser',
      displayName: 'Test Global',
      avatarUrl: 'https://cdn.discordapp.com/avatars/123456789/avatar.png',
      guildId: undefined,
    });
  });

  it('should handle missing optional fields', () => {
    const mockUser = {
      id: '123456789',
      username: 'testuser',
      displayName: null,
      globalName: null,
      displayAvatarURL: () => 'https://cdn.discordapp.com/avatars/123456789/avatar.png',
    } as unknown as User;

    const context = extractUserContext(mockUser);

    expect(context).toEqual({
      userId: '123456789',
      username: 'testuser',
      displayName: undefined,
      avatarUrl: 'https://cdn.discordapp.com/avatars/123456789/avatar.png',
      guildId: undefined,
    });
  });
});
