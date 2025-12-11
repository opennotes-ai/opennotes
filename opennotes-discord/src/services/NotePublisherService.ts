import {
  Client,
  ChannelType,
  PermissionFlagsBits,
  MessageCreateOptions,
  DiscordAPIError,
  GuildBasedChannel,
  ContainerBuilder,
} from 'discord.js';
import {
  V2_COLORS,
  V2_ICONS,
  createContainer,
  createTextSection,
  createSmallSeparator,
  createDivider,
  createMediaGallery,
  v2MessageFlags,
} from '../utils/v2-components.js';
import { logger } from '../logger.js';
import { apiClient } from '../api-client.js';
import { NoteContextService } from './NoteContextService.js';
import { NotePublisherConfigService } from './NotePublisherConfigService.js';
import { DistributedLock } from '../utils/distributed-lock.js';
import type { ScoreUpdateEvent } from '../events/types.js';
import type { NoteContext } from './NoteContextService.js';

export class NotePublisherService {
  private readonly client: Client;
  private readonly noteContextService: NoteContextService;
  private readonly configService: NotePublisherConfigService;
  private readonly distributedLock: DistributedLock | null;
  private readonly cooldownMs = 5 * 60 * 1000;
  private readonly lockTtlMs = 10 * 1000;
  private readonly permissionCacheTtlMs = 5 * 60 * 1000;
  private readonly permissionCache = new Map<string, { hasPermissions: boolean; expiresAt: number }>();

  constructor(
    client: Client,
    noteContextService: NoteContextService,
    configService: NotePublisherConfigService,
    distributedLock: DistributedLock | null = null
  ) {
    this.client = client;
    this.noteContextService = noteContextService;
    this.configService = configService;
    this.distributedLock = distributedLock;

    if (!this.distributedLock) {
      logger.warn('NotePublisherService initialized without distributed locking - not suitable for multi-instance deployment');
    }
  }

  async handleScoreUpdate(event: ScoreUpdateEvent): Promise<void> {
    const startTime = Date.now();

    logger.info('Processing score update event', {
      noteId: event.note_id,
      score: event.score,
      isForcePublished: event.metadata?.force_published === true,
      hasChannelId: !!event.channel_id,
      hasOriginalMessageId: !!event.original_message_id,
    });

    const lockKey = `note-publisher:note:${event.note_id}`;
    if (this.distributedLock) {
      const lockAcquired = await this.distributedLock.acquire(lockKey, {
        ttlMs: this.lockTtlMs,
        retryDelayMs: 50,
        maxRetries: 3,
      });

      if (!lockAcquired) {
        logger.info('Skipping score update - lock acquisition failed', {
          noteId: event.note_id,
          lockKey,
        });
        return;
      }

      logger.debug('Acquired distributed lock for score update processing', {
        noteId: event.note_id,
        lockKey,
      });
    }

    try {
      // Skip threshold check for force-published notes
      const isForcePublished = event.metadata?.force_published === true;
      if (!isForcePublished && !this.meetsThreshold(event)) {
        logger.info('Skipping score update - does not meet threshold', {
          noteId: event.note_id,
          score: event.score,
          confidence: event.confidence,
        });
        return;
      }

      const context = await this.getNoteContext(event);
      if (!context) {
        logger.info('Skipping score update - no Discord context found', {
          noteId: event.note_id,
          eventData: {
            channelId: event.channel_id,
            originalMessageId: event.original_message_id,
            communityServerId: event.community_server_id,
          },
        });
        return;
      }

      logger.info('Discord context resolved', {
        noteId: event.note_id,
        channelId: context.channelId,
        originalMessageId: context.originalMessageId,
        guildId: context.guildId,
      });

      if (!this.hasPermissionsCached(context.channelId)) {
        const channel = this.client.channels.cache.get(context.channelId);
        const channelType = channel?.type;
        const isThread = channel?.isThread();
        const missingPermission = isThread ? 'SEND_MESSAGES_IN_THREADS' : 'SEND_MESSAGES';

        logger.warn('Missing permissions for note-publisher', {
          noteId: event.note_id,
          channelId: context.channelId,
          channelType,
          isThread,
          missingPermission,
        });
        await this.recordNotePublisher(
          event,
          context,
          '',
          false,
          `Missing permission: ${missingPermission} for channel type ${channelType}`
        );
        return;
      }

      const [isDuplicate, isOnCooldown, config] = await Promise.all([
        this.isDuplicate(context.originalMessageId, context.guildId),
        this.isOnCooldown(context.channelId, context.guildId),
        this.configService.getConfig(context.guildId, context.channelId),
      ]);

      if (isDuplicate) {
        logger.info('Skipping score update - auto-post already exists for this message', {
          noteId: event.note_id,
          originalMessageId: context.originalMessageId,
        });
        return;
      }

      if (isOnCooldown) {
        logger.info('Skipping score update - channel is on cooldown', {
          noteId: event.note_id,
          channelId: context.channelId,
        });
        return;
      }

      if (!config.enabled) {
        logger.info('Skipping score update - auto-posting is disabled', {
          noteId: event.note_id,
          guildId: context.guildId,
          channelId: context.channelId,
        });
        return;
      }

      logger.info('All checks passed - fetching note content and posting', {
        noteId: event.note_id,
        channelId: context.channelId,
        originalMessageId: context.originalMessageId,
      });

      const noteContent = await this.fetchNoteContent(event.note_id);
      if (!noteContent) {
        logger.warn('Failed to fetch note content', {
          noteId: event.note_id,
        });
        return;
      }

      const container = this.formatMessageV2(event, noteContent, context);

      const notePublisherMessageId = await this.postReplyV2(context, container);

      if (notePublisherMessageId) {
        await this.recordNotePublisher(event, context, notePublisherMessageId, true);
        const processingTime = Date.now() - startTime;
        logger.info('Successfully note-publishered note', {
          noteId: event.note_id,
          originalMessageId: context.originalMessageId,
          notePublisherMessageId,
          score: event.score,
          processingTimeMs: processingTime,
        });
      }
    } catch (error) {
      logger.error('Error handling score update', {
        noteId: event.note_id,
        error: error instanceof Error ? error.message : String(error),
        stack: error instanceof Error ? error.stack : undefined,
      });
    } finally {
      if (this.distributedLock) {
        await this.distributedLock.release(lockKey);
        logger.debug('Released distributed lock for score update processing', {
          noteId: event.note_id,
          lockKey,
        });
      }
    }
  }

  private meetsThreshold(event: ScoreUpdateEvent): boolean {
    if (event.confidence !== 'standard') {
      return false;
    }

    const threshold = this.configService.getDefaultThreshold();
    return event.score >= threshold;
  }

  private async getNoteContext(event: ScoreUpdateEvent): Promise<NoteContext | null> {
    logger.debug('Getting note context from event', {
      noteId: event.note_id,
      has_original_message_id: !!event.original_message_id,
      has_channel_id: !!event.channel_id,
      has_community_server_id: !!event.community_server_id,
      original_message_id: event.original_message_id,
      channel_id: event.channel_id,
      community_server_id: event.community_server_id,
    });

    if (event.original_message_id && event.channel_id && event.community_server_id) {
      logger.debug('Using context from event directly', {
        noteId: event.note_id,
        originalMessageId: event.original_message_id,
        channelId: event.channel_id,
        guildId: event.community_server_id,
      });
      return {
        noteId: event.note_id.toString(),
        originalMessageId: event.original_message_id,
        channelId: event.channel_id,
        guildId: event.community_server_id,
        authorId: '',
      };
    }

    logger.debug('Falling back to cache for note context', {
      noteId: event.note_id,
      missing_original_message_id: !event.original_message_id,
      missing_channel_id: !event.channel_id,
      missing_community_server_id: !event.community_server_id,
    });
    return await this.noteContextService.getNoteContext(event.note_id.toString());
  }

  private async isDuplicate(originalMessageId: string, guildId: string): Promise<boolean> {
    try {
      const response = await apiClient.checkNoteDuplicate(originalMessageId, guildId);
      return response.exists === true;
    } catch (error) {
      // 404 means no duplicate exists yet - this is expected for first-time posts
      if (error instanceof Error && error.message.includes('404')) {
        return false;
      }

      logger.error('Error checking for duplicate note-publisher', {
        originalMessageId,
        error: error instanceof Error ? error.message : String(error),
      });
      return true;
    }
  }

  private async isOnCooldown(channelId: string, guildId: string): Promise<boolean> {
    try {
      const response = await apiClient.getLastNotePost(channelId, guildId);
      const lastPostTime = new Date(response.posted_at).getTime();
      const now = Date.now();

      return now - lastPostTime < this.cooldownMs;
    } catch (error) {
      // 404 means no previous post in this channel - no cooldown applies
      if (error instanceof Error && error.message.includes('404')) {
        return false;
      }

      logger.error('Error checking cooldown', {
        channelId,
        error: error instanceof Error ? error.message : String(error),
      });
      return true;
    }
  }

  private hasPermissionsCached(channelId: string): boolean {
    const now = Date.now();
    const cached = this.permissionCache.get(channelId);

    if (cached && cached.expiresAt > now) {
      return cached.hasPermissions;
    }

    const hasPerms = this.hasPermissions(channelId);
    this.permissionCache.set(channelId, {
      hasPermissions: hasPerms,
      expiresAt: now + this.permissionCacheTtlMs,
    });

    return hasPerms;
  }

  private hasPermissions(channelId: string): boolean {
    try {
      const channel = this.client.channels.cache.get(channelId);
      if (!channel) {
        logger.debug('Channel not found in cache', { channelId });
        return false;
      }

      // Type guard: only guild-based channels have permissions
      if (!('permissionsFor' in channel)) {
        logger.debug('Channel does not support permissions (DM or non-guild channel)', { channelId });
        return false;
      }

      const guildChannel = channel as GuildBasedChannel;
      const permissions = guildChannel.permissionsFor(this.client.user!);
      if (!permissions) {
        logger.debug('Unable to determine permissions for channel', { channelId });
        return false;
      }

      // Check permissions based on channel type
      if (channel.type === ChannelType.GuildText) {
        // Regular text channels: need SendMessages and CreatePublicThreads
        const hasSendMessages = permissions.has(PermissionFlagsBits.SendMessages);
        const hasCreateThreads = permissions.has(PermissionFlagsBits.CreatePublicThreads);
        const hasPerms = hasSendMessages && hasCreateThreads;
        logger.debug('Checking permissions for text channel', {
          channelId,
          hasSendMessages,
          hasCreateThreads,
          hasPerms,
          required: 'SendMessages, CreatePublicThreads',
        });
        return hasPerms;
      }

      if (channel.isThread()) {
        // Thread channels: need SendMessagesInThreads
        const hasPerms = permissions.has(PermissionFlagsBits.SendMessagesInThreads);
        logger.debug('Checking permissions for thread channel', {
          channelId,
          hasPerms,
          required: 'SendMessagesInThreads',
        });
        return hasPerms;
      }

      // For other channel types (voice, forum, etc.), we can't post messages
      logger.debug('Unsupported channel type for message posting', {
        channelId,
        channelType: channel.type,
      });
      return false;
    } catch (error) {
      logger.error('Error checking permissions', {
        channelId,
        error: error instanceof Error ? error.message : String(error),
      });
      return false;
    }
  }

  private async fetchNoteContent(noteId: number): Promise<{ summary: string; imageUrls?: string[] } | null> {
    try {
      const response = await apiClient.getNote(noteId.toString());
      if (!response.summary) {
        return null;
      }
      return {
        summary: response.summary,
        imageUrls: (response as { image_urls?: string[] }).image_urls,
      };
    } catch (error) {
      logger.error('Failed to fetch note content', {
        noteId,
        error: error instanceof Error ? error.message : String(error),
      });
      return null;
    }
  }

  private getConfidenceBadge(confidence: string): string {
    switch (confidence) {
      case 'standard':
        return '✅';
      case 'provisional':
        return '⚠️';
      case 'no_data':
        return '❓';
      default:
        return '';
    }
  }

  private formatMessageV2(
    event: ScoreUpdateEvent,
    noteContent: { summary: string; imageUrls?: string[] },
    context: NoteContext
  ): ContainerBuilder {
    const scorePercentage = (event.score * 100).toFixed(1);
    const isForcePublished = event.metadata?.force_published === true;

    const container = createContainer(V2_COLORS.HELPFUL);

    const headerEmoji = isForcePublished ? V2_ICONS.RATED : V2_ICONS.HELPFUL;
    const headerText = isForcePublished
      ? `${headerEmoji} **Community Note - Admin Published**`
      : `${headerEmoji} **Community Note - High Quality Detected**`;

    container.addTextDisplayComponents(createTextSection(headerText));
    container.addSeparatorComponents(createSmallSeparator());

    container.addTextDisplayComponents(createTextSection(noteContent.summary));

    if (noteContent.imageUrls && noteContent.imageUrls.length > 0) {
      const gallery = createMediaGallery(noteContent.imageUrls);
      if (gallery) {
        container.addMediaGalleryComponents(gallery);
      }
    }

    container.addSeparatorComponents(createSmallSeparator());

    let metadataText = `**Score:** ${scorePercentage}% ${this.getConfidenceBadge(event.confidence)}\n`;
    metadataText += `**Confidence:** ${event.confidence} (${event.rating_count} ratings)\n`;
    metadataText += `**Algorithm:** ${event.algorithm}`;

    if (context.authorId) {
      metadataText += `\n**Original Author:** <@${context.authorId}>`;
    }

    if (isForcePublished) {
      if (event.metadata?.admin_username) {
        metadataText += `\n**Published By:** ${event.metadata.admin_username}`;
      }
      if (event.metadata?.force_published_at) {
        const publishedDate = new Date(event.metadata.force_published_at);
        metadataText += `\n**Published At:** ${publishedDate.toLocaleString('en-US', {
          dateStyle: 'medium',
          timeStyle: 'short',
          timeZone: 'UTC',
        })} UTC`;
      }
    }

    container.addTextDisplayComponents(createTextSection(metadataText));

    container.addSeparatorComponents(createDivider());

    const footerText = isForcePublished
      ? '*This note was manually published by an admin and may not have met automatic quality thresholds.*'
      : '*This note was automatically posted because it reached the quality threshold.*';

    container.addTextDisplayComponents(createTextSection(footerText));

    return container;
  }

  private async postReplyV2(context: NoteContext, container: ContainerBuilder): Promise<string | null> {
    try {
      const channel = await this.client.channels.fetch(context.channelId);

      if (!channel) {
        logger.warn('Channel not found', {
          channelId: context.channelId,
        });
        return null;
      }

      if (!channel.isTextBased() || channel.isDMBased()) {
        logger.warn('Channel does not support text messages or is a DM channel', {
          channelId: context.channelId,
          channelType: channel.type,
        });
        return null;
      }

      const options: MessageCreateOptions = {
        components: [container.toJSON()],
        flags: v2MessageFlags(),
        reply: {
          messageReference: context.originalMessageId,
          failIfNotExists: false,
        },
      };

      const sentMessage = await channel.send(options);
      return sentMessage.id;
    } catch (error) {
      if (error instanceof DiscordAPIError) {
        if (error.code === 10008) {
          logger.debug('Original message not found, skipping note-publisher', {
            originalMessageId: context.originalMessageId,
          });
          return null;
        }

        if (error.code === 50013) {
          logger.warn('Missing permissions for note-publisher', {
            channelId: context.channelId,
            error: error.message,
          });
          return null;
        }

        if (error.status === 429) {
          await this.handleRateLimit(error);
          return null;
        }
      }

      logger.error('Failed to post reply', {
        channelId: context.channelId,
        originalMessageId: context.originalMessageId,
        error: error instanceof Error ? error.message : String(error),
      });
      throw error;
    }
  }

  private async handleRateLimit(error: DiscordAPIError): Promise<void> {
    const retryAfter = error.message.match(/retry after (\d+)/)?.[1];
    const delayMs = retryAfter ? parseInt(retryAfter, 10) * 1000 : 5000;

    logger.warn('Rate limited by Discord API, waiting before retry', {
      retryAfter: delayMs,
    });

    await new Promise((resolve) => setTimeout(resolve, delayMs));
  }

  private async recordNotePublisher(
    event: ScoreUpdateEvent,
    context: NoteContext,
    notePublisherMessageId: string,
    success: boolean,
    errorMessage?: string,
    messageContent?: string
  ): Promise<void> {
    try {
      // Fetch the original message to get its content for embedding storage
      let content = messageContent;
      if (!content && success) {
        try {
          const channel = await this.client.channels.fetch(context.channelId);
          if (channel && 'messages' in channel) {
            const message = await channel.messages.fetch(context.originalMessageId);
            content = message.content;
          }
        } catch (fetchError) {
          logger.warn('Could not fetch original message content for embedding', {
            originalMessageId: context.originalMessageId,
            channelId: context.channelId,
            error: fetchError instanceof Error ? fetchError.message : String(fetchError),
          });
        }
      }

      await apiClient.recordNotePublisher({
        noteId: String(event.note_id),
        originalMessageId: context.originalMessageId,
        channelId: context.channelId,
        guildId: context.guildId,
        scoreAtPost: event.score,
        confidenceAtPost: event.confidence,
        success,
        errorMessage: errorMessage || null,
        // Optional embedding fields - server will generate embeddings if content available
        messageEmbedding: null, // Server generates this from the original message
        embeddingProvider: null,
        embeddingModel: null,
      });

      logger.info('Recorded note-publisher attempt', {
        noteId: event.note_id,
        success,
        notePublisherMessageId: notePublisherMessageId || undefined,
        hasContent: !!content,
      });
    } catch (error) {
      logger.error('Failed to record note-publisher attempt', {
        noteId: event.note_id,
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }

  public clearPermissionCache(): void {
    this.permissionCache.clear();
  }
}
