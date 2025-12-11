import { jest } from '@jest/globals';
import { Client, TextChannel, PermissionsBitField, Message, PermissionFlagsBits, ChannelType } from 'discord.js';

export interface MockDiscordOptions {
  shouldFailPermissions?: boolean;
  shouldFailSend?: boolean;
  rateLimit?: boolean;
  missingPermission?: 'SEND_MESSAGES' | 'CREATE_PUBLIC_THREADS';
}

export interface SentMessage {
  channelId: string;
  content?: string;
  components?: any[];
  flags?: number;
  timestamp: Date;
}

export class MockDiscordClient {
  private mockClient: jest.Mocked<Client>;
  private mockChannels: Map<string, jest.Mocked<TextChannel>>;
  private sentMessages: SentMessage[];

  constructor(private options: MockDiscordOptions = {}) {
    this.mockChannels = new Map();
    this.sentMessages = [];
    this.mockClient = this.createMockClient();
  }

  private createMockClient(): jest.Mocked<Client> {
    return {
      user: { id: 'bot-123' },
      channels: {
        cache: this.mockChannels,
        fetch: jest.fn((id: string) => {
          const channel = this.mockChannels.get(id);
          if (!channel) {
            throw new Error(`Unknown Channel: ${id}`);
          }
          return Promise.resolve(channel);
        }),
      },
    } as any;
  }

  createMockChannel(
    channelId: string,
    channelOptions: MockDiscordOptions = {}
  ): jest.Mocked<TextChannel> {
    const mergedOptions = { ...this.options, ...channelOptions };

    const mockChannel: jest.Mocked<TextChannel> = {
      id: channelId,
      type: ChannelType.GuildText,
      isThread: jest.fn(() => false),
      isTextBased: jest.fn(() => true),
      isDMBased: jest.fn(() => false),
      permissionsFor: jest.fn((_userOrRole?: any): PermissionsBitField | null => {
        if (mergedOptions.shouldFailPermissions) {
          return null;
        }

        const permissions = PermissionFlagsBits.SendMessages | PermissionFlagsBits.CreatePublicThreads;

        if (mergedOptions.missingPermission === 'SEND_MESSAGES') {
          return new PermissionsBitField(PermissionFlagsBits.CreatePublicThreads);
        }

        if (mergedOptions.missingPermission === 'CREATE_PUBLIC_THREADS') {
          return new PermissionsBitField(PermissionFlagsBits.SendMessages);
        }

        return new PermissionsBitField(permissions);
      }) as any,

      send: jest.fn(async (content: any) => {
        if (mergedOptions.shouldFailSend) {
          throw new Error('Failed to send message');
        }

        if (mergedOptions.rateLimit) {
          const error: any = new Error('You are being rate limited.');
          error.code = 50035;
          error.status = 429;
          throw error;
        }

        const sentMessage: SentMessage = {
          channelId,
          timestamp: new Date(),
        };

        if (typeof content === 'string') {
          sentMessage.content = content;
        } else {
          sentMessage.content = content.content;
          sentMessage.components = content.components;
          sentMessage.flags = content.flags;
        }

        this.sentMessages.push(sentMessage);

        return {
          id: `reply-${Date.now()}`,
          content: sentMessage.content,
          channelId,
        } as Message;
      }),
    } as any;

    this.mockChannels.set(channelId, mockChannel);
    return mockChannel;
  }

  getClient(): jest.Mocked<Client> {
    return this.mockClient;
  }

  getChannel(channelId: string): jest.Mocked<TextChannel> | undefined {
    return this.mockChannels.get(channelId);
  }

  getSentMessages(): SentMessage[] {
    return this.sentMessages;
  }

  getSentMessageCount(channelId?: string): number {
    if (channelId) {
      return this.sentMessages.filter((m) => m.channelId === channelId).length;
    }
    return this.sentMessages.length;
  }

  clearSentMessages(): void {
    this.sentMessages = [];
  }

  simulateDeletedMessage(channelId: string): void {
    const channel = this.mockChannels.get(channelId);
    if (channel) {
      // @ts-expect-error - Complex mock types don't align, but runtime behavior is correct
      channel.send = jest.fn().mockRejectedValue(
        // @ts-expect-error - Error object extension for Discord API codes
        Object.assign(new Error('Unknown Message'), { code: 10008 })
      );
    }
  }

  simulateRateLimit(channelId: string, duration: number = 1000): void {
    const channel = this.mockChannels.get(channelId);
    if (channel) {
      const originalSend = channel.send;

      // @ts-expect-error - Complex mock types don't align, but runtime behavior is correct
      channel.send = jest.fn().mockRejectedValueOnce(
        // @ts-expect-error - Error object extension for Discord rate limit codes
        Object.assign(new Error('You are being rate limited.'), {
          code: 50035,
          status: 429,
          retryAfter: duration / 1000,
        })
      );

      setTimeout(() => {
        channel.send = originalSend;
      }, duration);
    }
  }

  simulatePermissionChange(
    channelId: string,
    missingPermission: 'SEND_MESSAGES' | 'CREATE_PUBLIC_THREADS' | null
  ): void {
    const channel = this.mockChannels.get(channelId);
    if (channel) {
      channel.permissionsFor = jest.fn((): PermissionsBitField | null => {
        if (missingPermission === null) {
          return new PermissionsBitField(PermissionFlagsBits.SendMessages | PermissionFlagsBits.CreatePublicThreads);
        }

        if (missingPermission === 'SEND_MESSAGES') {
          return new PermissionsBitField(PermissionFlagsBits.CreatePublicThreads);
        }

        if (missingPermission === 'CREATE_PUBLIC_THREADS') {
          return new PermissionsBitField(PermissionFlagsBits.SendMessages);
        }

        return new PermissionsBitField(0n);
      }) as any;
    }
  }
}

export const createMockDiscordClient = (options?: MockDiscordOptions): MockDiscordClient => {
  return new MockDiscordClient(options);
};
