import { jest } from '@jest/globals';
import { QueueManager } from '../../src/lib/queue-manager.js';
import { TextChannel } from 'discord.js';
import type { Client, User, ThreadChannel, GuildMember, PermissionsBitField } from 'discord.js';

describe('QueueManager - Rate Limiting', () => {
  let queueManager: QueueManager;
  let mockClient: Client;
  let mockUser: User;
  let mockChannel: TextChannel;

  function createMockChannel(channelId: string, threadId: string): TextChannel {
    const mockBotMember = {
      id: 'bot-123',
    } as GuildMember;

    const mockPermissions = {
      has: jest.fn().mockReturnValue(true),
    } as unknown as Readonly<PermissionsBitField>;

    const mockThreadMembers = new Map<string, unknown>();
    const mockThread = {
      id: threadId,
      archived: false,
      setArchived: jest.fn<any>().mockResolvedValue(undefined),
      members: {
        add: jest.fn<any>().mockImplementation((userId: string) => {
          mockThreadMembers.set(userId, { id: userId });
          return Promise.resolve(undefined);
        }),
        fetch: jest.fn<any>().mockImplementation(() => {
          return Promise.resolve({
            has: (userId: string) => mockThreadMembers.has(userId),
          });
        }),
      },
      delete: jest.fn<any>().mockResolvedValue(undefined),
    } as unknown as ThreadChannel;

    const mockChannelObj = {
      id: channelId,
      isThread: jest.fn().mockReturnValue(false),
      guild: {
        members: {
          fetchMe: jest.fn<any>().mockResolvedValue(mockBotMember),
        },
      },
      permissionsFor: jest.fn().mockReturnValue(mockPermissions),
      threads: {
        create: jest.fn<any>().mockResolvedValue(mockThread),
      },
    };

    Object.setPrototypeOf(mockChannelObj, TextChannel.prototype);
    return mockChannelObj as unknown as TextChannel;
  }

  beforeEach(() => {
    mockClient = {} as Client;
    queueManager = new QueueManager(mockClient);

    mockUser = {
      id: 'user-123',
      username: 'testuser',
    } as User;

    mockChannel = createMockChannel('channel-123', 'thread-123');
  });

  describe('Rate Limit Enforcement', () => {
    it('should allow queue creation within rate limit', async () => {
      await queueManager.getOrCreateOpenNotesThread(mockUser, mockChannel, 'guild-123', [], 0);
      await queueManager.closeQueue(mockUser.id, 'guild-123');

      await queueManager.getOrCreateOpenNotesThread(mockUser, mockChannel, 'guild-123', [], 0);
      await queueManager.closeQueue(mockUser.id, 'guild-123');

      const metrics = queueManager.getMetrics();
      expect(metrics.totalAttempts).toBe(2);
      expect(metrics.rateLimitViolations).toBe(0);
    });

    it('should block excessive queue creation attempts', async () => {
      for (let i = 0; i < 5; i++) {
        await queueManager.getOrCreateOpenNotesThread(mockUser, mockChannel, 'guild-123', [], 0);
        await queueManager.closeQueue(mockUser.id, 'guild-123');
      }

      await expect(
        queueManager.getOrCreateOpenNotesThread(mockUser, mockChannel, 'guild-123', [], 0)
      ).rejects.toThrow(/creating queues too quickly/);

      const metrics = queueManager.getMetrics();
      expect(metrics.rateLimitViolations).toBe(1);
    });

    it('should provide helpful error message with remaining time', async () => {
      for (let i = 0; i < 5; i++) {
        await queueManager.getOrCreateOpenNotesThread(mockUser, mockChannel, 'guild-123', [], 0);
        await queueManager.closeQueue(mockUser.id, 'guild-123');
      }

      let errorThrown = false;
      try {
        await queueManager.getOrCreateOpenNotesThread(mockUser, mockChannel, 'guild-123', [], 0);
      } catch (error) {
        errorThrown = true;
        expect(error).toBeInstanceOf(Error);
        expect((error as Error).message).toMatch(/wait \d+ seconds/);
      }
      expect(errorThrown).toBe(true);
    });

    it('should reset rate limit after window expires', async () => {
      for (let i = 0; i < 5; i++) {
        await queueManager.getOrCreateOpenNotesThread(mockUser, mockChannel, 'guild-123', [], 0);
        await queueManager.closeQueue(mockUser.id, 'guild-123');
      }

      await expect(
        queueManager.getOrCreateOpenNotesThread(mockUser, mockChannel, 'guild-123', [], 0)
      ).rejects.toThrow();

      await new Promise(resolve => setTimeout(resolve, 61000));

      await expect(
        queueManager.getOrCreateOpenNotesThread(mockUser, mockChannel, 'guild-123', [], 0)
      ).resolves.toBeDefined();
    }, 65000);

    it('should track rate limits per user independently', async () => {
      const mockUser2 = { id: 'user-456', username: 'testuser2' } as User;

      for (let i = 0; i < 5; i++) {
        await queueManager.getOrCreateOpenNotesThread(mockUser, mockChannel, 'guild-123', [], 0);
        await queueManager.closeQueue(mockUser.id, 'guild-123');
      }

      await expect(
        queueManager.getOrCreateOpenNotesThread(mockUser, mockChannel, 'guild-123', [], 0)
      ).rejects.toThrow();

      await expect(
        queueManager.getOrCreateOpenNotesThread(mockUser2, mockChannel, 'guild-123', [], 0)
      ).resolves.toBeDefined();
    });
  });

  describe('Metrics', () => {
    it('should track total queue creation attempts', async () => {
      await queueManager.getOrCreateOpenNotesThread(mockUser, mockChannel, 'guild-123', [], 0);
      await queueManager.closeQueue(mockUser.id, 'guild-123');

      await queueManager.getOrCreateOpenNotesThread(mockUser, mockChannel, 'guild-123', [], 0);
      await queueManager.closeQueue(mockUser.id, 'guild-123');

      const metrics = queueManager.getMetrics();
      expect(metrics.totalAttempts).toBe(2);
    });

    it('should track rate limit violations', async () => {
      for (let i = 0; i < 5; i++) {
        await queueManager.getOrCreateOpenNotesThread(mockUser, mockChannel, 'guild-123', [], 0);
        await queueManager.closeQueue(mockUser.id, 'guild-123');
      }

      try {
        await queueManager.getOrCreateOpenNotesThread(mockUser, mockChannel, 'guild-123', [], 0);
      } catch {
        // Expected
      }

      try {
        await queueManager.getOrCreateOpenNotesThread(mockUser, mockChannel, 'guild-123', [], 0);
      } catch {
        // Expected
      }

      const metrics = queueManager.getMetrics();
      expect(metrics.rateLimitViolations).toBe(2);
    });

    it('should track active queues', async () => {
      await queueManager.getOrCreateOpenNotesThread(mockUser, mockChannel, 'guild-123', [], 0);

      const metrics = queueManager.getMetrics();
      expect(metrics.activeQueues).toBe(1);

      await queueManager.closeQueue(mockUser.id, 'guild-123');

      const metricsAfter = queueManager.getMetrics();
      expect(metricsAfter.activeQueues).toBe(0);
    });

    it('should expose max queues per user configuration', () => {
      const metrics = queueManager.getMetrics();
      expect(metrics.maxQueuesPerUser).toBe(3);
    });
  });

  describe('Existing Queue Reuse', () => {
    let freshQueueManager: QueueManager;
    let freshMockChannel: TextChannel;
    let freshMockUser: User;

    beforeEach(() => {
      freshQueueManager = new QueueManager(mockClient);
      freshMockChannel = createMockChannel('channel-reuse', 'thread-reuse');
      freshMockUser = {
        id: 'user-fresh',
        username: 'testuser-fresh',
      } as User;
    });

    it('should not count reusing existing queue against rate limit', async () => {
      await freshQueueManager.getOrCreateOpenNotesThread(freshMockUser, freshMockChannel, 'guild-123', [], 0);

      for (let i = 0; i < 10; i++) {
        await freshQueueManager.getOrCreateOpenNotesThread(freshMockUser, freshMockChannel, 'guild-123', [], 0);
      }

      const metrics = freshQueueManager.getMetrics();
      expect(metrics.totalAttempts).toBe(1);
      expect(metrics.rateLimitViolations).toBe(0);
    });

    it('should re-add user to thread if they left', async () => {
      const thread = await freshQueueManager.getOrCreateOpenNotesThread(
        freshMockUser,
        freshMockChannel,
        'guild-123',
        [],
        0
      );

      const membersAddMock = thread.members.add as jest.Mock;
      expect(membersAddMock).toHaveBeenCalledWith(freshMockUser.id);

      membersAddMock.mockClear();

      const threadMembers = (thread as unknown as { members: { add: jest.Mock; fetch: jest.Mock } }).members;
      const originalFetch = threadMembers.fetch;
      originalFetch.mockImplementationOnce(() =>
        Promise.resolve({
          has: () => false,
        })
      );

      await freshQueueManager.getOrCreateOpenNotesThread(freshMockUser, freshMockChannel, 'guild-123', [], 0);

      expect(membersAddMock).toHaveBeenCalledWith(freshMockUser.id);
    });
  });

  describe('Cross-Guild Isolation', () => {
    it('should not reuse threads across different guilds for same user', async () => {
      const mockChannel2 = createMockChannel('channel-456', 'thread-456');

      const thread1 = await queueManager.getOrCreateOpenNotesThread(
        mockUser,
        mockChannel,
        'guild-123',
        [],
        0
      );

      const thread2 = await queueManager.getOrCreateOpenNotesThread(
        mockUser,
        mockChannel2,
        'guild-456',
        [],
        0
      );

      expect(thread1.id).toBe('thread-123');
      expect(thread2.id).toBe('thread-456');
      expect(thread1.id).not.toBe(thread2.id);

      const metrics = queueManager.getMetrics();
      expect(metrics.activeQueues).toBe(2);
    });

    it('should track separate page state per guild for same user', async () => {
      const mockChannel2 = createMockChannel('channel-456', 'thread-456');

      await queueManager.getOrCreateOpenNotesThread(mockUser, mockChannel, 'guild-123', [], 0);
      await queueManager.getOrCreateOpenNotesThread(mockUser, mockChannel2, 'guild-456', [], 0);

      queueManager.setPage(mockUser.id, 'guild-123', 2);
      queueManager.setPage(mockUser.id, 'guild-456', 3);

      expect(queueManager.getCurrentPage(mockUser.id, 'guild-123')).toBe(2);
      expect(queueManager.getCurrentPage(mockUser.id, 'guild-456')).toBe(3);
    });

    it('should track separate notes per guild for same user', async () => {
      const mockChannel2 = createMockChannel('channel-456', 'thread-456');

      const notesGuild1 = [
        {
          id: 'note-1',
          author_participant_id: 'author-1',
          summary: 'Guild 1 note',
          classification: 'NOT_MISLEADING',
          helpfulness_score: 0.5,
          status: 'NEEDS_MORE_RATINGS' as const,
          created_at: new Date().toISOString(),
          ratings: [],
          ratings_count: 0,
        },
      ];

      const notesGuild2 = [
        {
          id: 'note-2',
          author_participant_id: 'author-2',
          summary: 'Guild 2 note',
          classification: 'NOT_MISLEADING',
          helpfulness_score: 0.8,
          status: 'CURRENTLY_RATED_HELPFUL' as const,
          created_at: new Date().toISOString(),
          ratings: [],
          ratings_count: 0,
        },
      ];

      await queueManager.getOrCreateOpenNotesThread(
        mockUser,
        mockChannel,
        'guild-123',
        notesGuild1,
        1
      );
      await queueManager.getOrCreateOpenNotesThread(
        mockUser,
        mockChannel2,
        'guild-456',
        notesGuild2,
        1
      );

      expect(queueManager.getNotes(mockUser.id, 'guild-123')).toEqual(notesGuild1);
      expect(queueManager.getNotes(mockUser.id, 'guild-456')).toEqual(notesGuild2);
    });

    it('should close queue independently per guild', async () => {
      const mockChannel2 = createMockChannel('channel-456', 'thread-456');

      await queueManager.getOrCreateOpenNotesThread(mockUser, mockChannel, 'guild-123', [], 0);
      await queueManager.getOrCreateOpenNotesThread(mockUser, mockChannel2, 'guild-456', [], 0);

      let metrics = queueManager.getMetrics();
      expect(metrics.activeQueues).toBe(2);

      await queueManager.closeQueue(mockUser.id, 'guild-123');

      metrics = queueManager.getMetrics();
      expect(metrics.activeQueues).toBe(1);

      await queueManager.closeQueue(mockUser.id, 'guild-456');

      metrics = queueManager.getMetrics();
      expect(metrics.activeQueues).toBe(0);
    });
  });
});
