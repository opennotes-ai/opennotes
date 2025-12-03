import { ThreadChannel, User, Client, ChannelType, TextChannel, PermissionFlagsBits, DiscordAPIError, GuildTextBasedChannel } from 'discord.js';
import { hasCode } from '../utils/error-handlers.js';
import { NoteWithRatings } from './types.js';
import { logger } from '../logger.js';

interface QueueState {
  thread: ThreadChannel;
  userId: string;
  guildId: string;
  currentPage: number;
  notes: NoteWithRatings[];
  totalNotes: number;
  lastActivity: number;
  cleanupTimer: NodeJS.Timeout;
}

const QUEUE_INACTIVITY_TIMEOUT = 60 * 60 * 1000; // 1 hour - auto-delete thread after this period of no user interaction
const NOTES_PER_PAGE = 10; // Multi-message pattern: each note gets its own message, no action row limits
const MAX_QUEUES_PER_USER = 3;
const RATE_LIMIT_WINDOW_MS = 30 * 1000; // 30 seconds
const MAX_ATTEMPTS_PER_WINDOW = 5;

interface RateLimitEntry {
  attempts: number;
  windowStart: number;
}

export class QueueManager {
  private activeQueues: Map<string, QueueState> = new Map();
  private rateLimits: Map<string, RateLimitEntry> = new Map();
  private queueCreationMetrics: { totalAttempts: number; rateLimitViolations: number } = {
    totalAttempts: 0,
    rateLimitViolations: 0,
  };

  constructor(_client: Client) {
    // Client is available for future use if needed
  }

  private getQueueKey(userId: string, guildId: string): string {
    return `${userId}:${guildId}`;
  }

  async getOrCreateOpenNotesThread(
    user: User,
    channel: GuildTextBasedChannel,
    guildId: string,
    notes: NoteWithRatings[],
    totalNotes: number
  ): Promise<ThreadChannel> {
    const queueKey = this.getQueueKey(user.id, guildId);
    const existingQueue = this.activeQueues.get(queueKey);

    if (existingQueue) {
      logger.info(`Reusing existing queue for user ${user.id} in guild ${guildId}`);
      this.updateActivity(user.id, guildId);

      try {
        if (existingQueue.thread.archived) {
          logger.info(`Unarchiving existing queue for user ${user.id}`);
          await existingQueue.thread.setArchived(false);
        }

        const threadMembers = await existingQueue.thread.members.fetch();
        if (!threadMembers.has(user.id)) {
          logger.info(`Re-adding user ${user.id} to existing thread (user had left)`);
          await existingQueue.thread.members.add(user.id);
        }

        return existingQueue.thread;
      } catch (error) {
        logger.warn(`Failed to restore thread for user ${user.id}, creating new one`, { error });
        this.activeQueues.delete(queueKey);
      }
    }

    this.queueCreationMetrics.totalAttempts++;
    this.checkRateLimit(user.id);

    // If called from a thread, use the parent channel
    const parentChannel = channel.isThread() ? channel.parent : channel;

    if (!parentChannel || !(parentChannel instanceof TextChannel)) {
      throw new Error('Unable to determine parent text channel for thread creation');
    }

    const botMember = await parentChannel.guild.members.fetchMe();
    const botPermissions = parentChannel.permissionsFor(botMember);

    if (!botPermissions) {
      throw new Error('Unable to determine bot permissions in this channel');
    }

    const hasThreadPermission =
      botPermissions.has(PermissionFlagsBits.CreatePrivateThreads) ||
      botPermissions.has(PermissionFlagsBits.ManageThreads);

    if (!hasThreadPermission) {
      throw new Error(
        'Bot lacks permission to create private threads. Please grant "Create Private Threads" or "Manage Threads" permission.'
      );
    }

    logger.info(`Creating new queue for user ${user.id} in channel ${parentChannel.id}`);

    try {
      const thread = await parentChannel.threads.create({
        name: `📋 Open Notes - ${user.username}`,
        type: ChannelType.PrivateThread,
        invitable: false,
        reason: 'User requested Open Notes thread',
      });

      try {
        await thread.members.add(user.id);
      } catch (memberError) {
        logger.error(`Failed to add user ${user.id} to thread, archiving and throwing`, { memberError });
        try {
          await thread.setArchived(true);
        } catch (archiveError) {
          logger.error(`Failed to archive thread after member add failure`, { archiveError });
        }
        throw new Error('Failed to add you to the private thread. Please try again.');
      }

      const cleanupTimer = this.scheduleCleanup(user.id, guildId);

      this.activeQueues.set(queueKey, {
        thread,
        userId: user.id,
        guildId,
        currentPage: 1,
        notes,
        totalNotes,
        lastActivity: Date.now(),
        cleanupTimer,
      });

      logger.info(`Successfully created queue thread ${thread.id} for user ${user.id}`);
      return thread;
    } catch (error) {
      if (error instanceof DiscordAPIError) {
        logger.error(`Discord API error creating thread for user ${user.id}`, {
          code: hasCode(error) ? error.code : undefined,
          message: error.message,
          status: error.status,
        });

        const errorCode = hasCode(error) ? Number(error.code) : null;
        switch (errorCode) {
          case 50001:
            throw new Error('Bot does not have access to this channel.');
          case 50013:
            throw new Error('Bot lacks permission to create threads in this channel.');
          case 160002:
            throw new Error('Maximum number of active threads reached. Please try again later.');
          default:
            throw new Error(`Failed to create private thread: ${error.message}`);
        }
      }

      logger.error(`Unexpected error creating thread for user ${user.id}`, { error });
      throw error;
    }
  }

  updateNotes(userId: string, guildId: string, notes: NoteWithRatings[], totalNotes: number): void {
    const queueKey = this.getQueueKey(userId, guildId);
    const queue = this.activeQueues.get(queueKey);
    if (queue) {
      queue.notes = notes;
      queue.totalNotes = totalNotes;
      this.updateActivity(userId, guildId);
    }
  }

  getCurrentPage(userId: string, guildId: string): number {
    const queueKey = this.getQueueKey(userId, guildId);
    const queue = this.activeQueues.get(queueKey);
    return queue?.currentPage || 1;
  }

  setPage(userId: string, guildId: string, page: number): void {
    const queueKey = this.getQueueKey(userId, guildId);
    const queue = this.activeQueues.get(queueKey);
    if (queue) {
      queue.currentPage = page;
      this.updateActivity(userId, guildId);
    }
  }

  getNotesPerPage(): number {
    return NOTES_PER_PAGE;
  }

  getNotes(userId: string, guildId: string): NoteWithRatings[] {
    const queueKey = this.getQueueKey(userId, guildId);
    const queue = this.activeQueues.get(queueKey);
    return queue?.notes || [];
  }

  async closeQueue(userId: string, guildId: string): Promise<void> {
    const queueKey = this.getQueueKey(userId, guildId);
    const queue = this.activeQueues.get(queueKey);
    if (!queue) {return;}

    logger.info(`Closing queue for user ${userId}`);

    clearTimeout(queue.cleanupTimer);

    try {
      await queue.thread.delete('Queue closed or timed out');
      logger.info(`Successfully deleted thread for user ${userId}`);
    } catch (error: unknown) {
      const errorCode = hasCode(error) ? Number(error.code) : null;

      if (errorCode === 10003) {
        logger.debug(`Thread for user ${userId} already deleted (Unknown Channel)`);
      } else if (errorCode === 50013) {
        logger.warn(`Missing permissions to delete thread for user ${userId}, attempting to archive instead`);
        try {
          if (!queue.thread.archived) {
            await queue.thread.setArchived(true);
            logger.info(`Successfully archived thread for user ${userId} as fallback`);
          }
        } catch (archiveError) {
          logger.error(`Failed to archive thread for user ${userId} after delete failed`, { archiveError });
        }
      } else {
        logger.error(`Failed to delete thread for user ${userId}`, { error, errorCode });
      }
    }

    this.activeQueues.delete(queueKey);
  }

  private updateActivity(userId: string, guildId: string): void {
    const queueKey = this.getQueueKey(userId, guildId);
    const queue = this.activeQueues.get(queueKey);
    if (!queue) {return;}

    queue.lastActivity = Date.now();

    clearTimeout(queue.cleanupTimer);
    queue.cleanupTimer = this.scheduleCleanup(userId, guildId);
  }

  private scheduleCleanup(userId: string, guildId: string): NodeJS.Timeout {
    return setTimeout(() => {
      logger.info(`Queue for user ${userId} in guild ${guildId} timed out due to inactivity`);
      void this.closeQueue(userId, guildId);
    }, QUEUE_INACTIVITY_TIMEOUT);
  }

  // eslint-disable-next-line @typescript-eslint/require-await
  async cleanup(): Promise<void> {
    logger.info('Cleaning up all active queues');
    const queueKeys = Array.from(this.activeQueues.keys());
    for (const queueKey of queueKeys) {
      const [userId, guildId] = queueKey.split(':');
      void this.closeQueue(userId, guildId);
    }
  }

  private checkRateLimit(userId: string): void {
    const now = Date.now();
    const userRateLimit = this.rateLimits.get(userId);

    if (!userRateLimit || now - userRateLimit.windowStart > RATE_LIMIT_WINDOW_MS) {
      this.rateLimits.set(userId, {
        attempts: 1,
        windowStart: now,
      });
      return;
    }

    if (userRateLimit.attempts >= MAX_ATTEMPTS_PER_WINDOW) {
      this.queueCreationMetrics.rateLimitViolations++;
      const remainingTime = Math.ceil((RATE_LIMIT_WINDOW_MS - (now - userRateLimit.windowStart)) / 1000);

      logger.warn('Queue creation rate limit exceeded', {
        userId,
        attempts: userRateLimit.attempts,
        maxAttempts: MAX_ATTEMPTS_PER_WINDOW,
        remainingTime,
      });

      throw new Error(
        `You are creating queues too quickly. Please wait ${remainingTime} seconds before trying again.`
      );
    }

    userRateLimit.attempts++;
  }

  getMetrics(): {
    activeQueues: number;
    maxQueuesPerUser: number;
    totalAttempts: number;
    rateLimitViolations: number;
  } {
    return {
      activeQueues: this.activeQueues.size,
      maxQueuesPerUser: MAX_QUEUES_PER_USER,
      totalAttempts: this.queueCreationMetrics.totalAttempts,
      rateLimitViolations: this.queueCreationMetrics.rateLimitViolations,
    };
  }
}
