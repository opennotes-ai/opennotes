import {
  Client,
  GatewayIntentBits,
  Collection,
  Events,
  Interaction,
  REST,
  Routes,
  ActivityType,
  MessageFlags,
  SlashCommandBuilder,
  ContextMenuCommandBuilder,
  ChatInputCommandInteraction,
  MessageContextMenuCommandInteraction,
  Message,
  Guild,
  ChannelType,
  DMChannel,
  NonThreadGuildBasedChannel,
} from 'discord.js';
import { config } from './config.js';
import { logger } from './logger.js';
import { cache } from './cache.js';

// Consolidated command imports
import * as configCommand from './commands/config.js';
import * as noteCommand from './commands/note.js';
import * as listCommand from './commands/list.js';

// Standalone command imports
import * as aboutOpenNotesCommand from './commands/about-opennotes.js';
import * as statusBotCommand from './commands/status-bot.js';
import * as vibecheckCommand from './commands/vibecheck.js';
import * as clearCommand from './commands/clear.js';

// Context menu command imports
import * as noteRequestContextCommand from './commands/note-request-context.js';

import { NatsSubscriber } from './events/NatsSubscriber.js';
import { initializeNatsPublisher, closeNatsPublisher } from './events/NatsPublisher.js';
import {
  isVibecheckPromptInteraction,
  handleVibecheckPromptInteraction,
} from './handlers/vibecheck-prompt-handler.js';
import { NotePublisherService } from './services/NotePublisherService.js';
import { NoteContextService } from './services/NoteContextService.js';
import { NotePublisherConfigService } from './services/NotePublisherConfigService.js';
import { MessageMonitorService } from './services/MessageMonitorService.js';
import { GuildSetupService } from './services/GuildSetupService.js';
import { GuildOnboardingService } from './services/GuildOnboardingService.js';
import { BotChannelService } from './services/BotChannelService.js';
import { GuildConfigService } from './services/GuildConfigService.js';
import { PermissionModeService } from './services/PermissionModeService.js';
import { ConfigKey } from './lib/config-schema.js';
import { VibecheckProgressService } from './services/VibecheckProgressService.js';
import { apiClient } from './api-client.js';
import { closeRedisClient } from './redis-client.js';
import express, { Express } from 'express';

interface Command {
  data: SlashCommandBuilder | ContextMenuCommandBuilder;
  execute: (interaction: ChatInputCommandInteraction | MessageContextMenuCommandInteraction) => Promise<void>;
}

export class Bot {
  private client: Client;
  commands: Collection<string, Command>;
  private isReady: boolean;
  private natsSubscriber?: NatsSubscriber;
  private notePublisherService?: NotePublisherService;
  private messageMonitorService?: MessageMonitorService;
  private guildSetupService?: GuildSetupService;
  private guildOnboardingService?: GuildOnboardingService;
  private botChannelService?: BotChannelService;
  private guildConfigService?: GuildConfigService;
  private permissionModeService?: PermissionModeService;
  private vibecheckProgressService?: VibecheckProgressService;
  private healthCheckServer?: Express;
  private healthCheckPort?: number;

  constructor() {
    this.client = new Client({
      intents: [
        GatewayIntentBits.Guilds,
        GatewayIntentBits.GuildMessages,
        GatewayIntentBits.MessageContent,
      ],
    });

    this.commands = new Collection();
    this.isReady = false;

    this.loadCommands();
    this.setupEventHandlers();
  }

  private loadCommands(): void {
    const commandModules = [
      // Consolidated command groups
      configCommand,
      noteCommand,
      listCommand,
      // Standalone commands
      aboutOpenNotesCommand,
      statusBotCommand,
      vibecheckCommand,
      clearCommand,
      // Context menu commands
      noteRequestContextCommand,
    ];

    for (const cmd of commandModules) {
      this.commands.set(cmd.data.name, cmd as Command);
      logger.debug('Loaded command', { name: cmd.data.name });
    }

    logger.info('Commands loaded', { count: this.commands.size });
  }

  private setupEventHandlers(): void {
    this.client.once(Events.ClientReady, () => {
      void this.onReady();
    });
    this.client.on(Events.InteractionCreate, (interaction: Interaction) => {
      void this.onInteraction(interaction);
    });
    this.client.on(Events.MessageCreate, (message: Message) => {
      void this.onMessage(message);
    });
    this.client.on(Events.GuildCreate, (guild: Guild) => {
      void this.onGuildCreate(guild);
    });
    this.client.on(Events.ChannelUpdate, (oldChannel, newChannel) => {
      void this.onChannelUpdate(oldChannel, newChannel);
    });
    this.client.on(Events.Error, this.onError.bind(this));
  }

  private async onReady(): Promise<void> {
    if (!this.client.user) {
      throw new Error('Client user not available');
    }

    this.isReady = true;

    const shardInfo = this.client.shard
      ? { shardId: this.client.shard.ids, shardCount: this.client.shard.count }
      : { shardId: 'none', shardCount: 1 };

    logger.info('Bot ready', {
      username: this.client.user.tag,
      guilds: this.client.guilds.cache.size,
      ...shardInfo,
    });

    this.client.user.setPresence({
      activities: [{ name: 'Community Notes', type: ActivityType.Watching }],
      status: 'online',
    });

    await this.initializeNotePublisher();
    logger.info('Note publisher system initialized');

    this.guildSetupService = new GuildSetupService();
    logger.info('Guild setup service initialized');

    this.guildOnboardingService = new GuildOnboardingService();
    logger.info('Guild onboarding service initialized');

    this.botChannelService = new BotChannelService();
    this.guildConfigService = new GuildConfigService(apiClient);
    this.permissionModeService = new PermissionModeService();
    logger.info('Bot channel service initialized');

    const serverReadiness = await this.waitForServerReady();
    if (!serverReadiness.ready) {
      logger.warn('Proceeding with bot initialization despite server not being ready', {
        waitedMs: serverReadiness.waitedMs,
      });
    }
    await this.ensureBotChannelsForAllGuilds();

    await this.syncCommunityNames();

    await this.initializeMessageMonitoring();
    logger.info('Message monitoring system initialized');

    await this.registerCommands();
  }

  private async registerCommands(): Promise<void> {
    try {
      const rest = new REST({ version: '10' }).setToken(config.discordToken);
      const commandsData = Array.from(this.commands.values()).map(cmd => cmd.data.toJSON());

      logger.info('Registering slash commands', { count: commandsData.length });

      await rest.put(
        Routes.applicationCommands(config.clientId),
        { body: commandsData }
      );

      logger.info('Slash commands registered successfully');
    } catch (error) {
      logger.error('Failed to register commands', { error });
    }
  }

  private async onInteraction(interaction: Interaction): Promise<void> {
    if (interaction.isChatInputCommand() || interaction.isMessageContextMenuCommand()) {
      const command = this.commands.get(interaction.commandName);

      if (!command) {
        logger.warn('Unknown command', { command: interaction.commandName });
        return;
      }

      try {
        await command.execute(interaction);
      } catch (error) {
        logger.error('Command execution failed', {
          command: interaction.commandName,
          error,
        });

        if (interaction.replied || interaction.deferred) {
          await interaction.followUp({
            content: 'An error occurred while executing this command.',
            flags: MessageFlags.Ephemeral,
          });
        } else {
          await interaction.reply({
            content: 'An error occurred while executing this command.',
            flags: MessageFlags.Ephemeral,
          });
        }
      }
    } else if (interaction.isButton()) {
      if (interaction.customId.startsWith('request_reply:')) {
        try {
          await listCommand.handleRequestReplyButton(interaction);
        } catch (error) {
          logger.error('Request reply button failed', { error });
        }
      } else if (
        interaction.customId.startsWith('queue:previous:') ||
        interaction.customId.startsWith('queue:next:')
      ) {
        try {
          await listCommand.handlePaginationButton(interaction);
        } catch (error) {
          logger.error('Pagination button failed', { error });
        }
      } else if (interaction.customId.startsWith('write_note:')) {
        try {
          await listCommand.handleWriteNoteButton(interaction);
        } catch (error) {
          logger.error('Write note button failed', { error });
        }
      } else if (interaction.customId.startsWith('ai_write_note:')) {
        try {
          await listCommand.handleAiWriteNoteButton(interaction);
        } catch (error) {
          logger.error('AI write note button failed', { error });
        }
      } else if (interaction.customId.startsWith('rate:')) {
        try {
          await listCommand.handleRateNoteButton(interaction);
        } catch (error) {
          logger.error('Rate note button failed', { error });
        }
      } else if (interaction.customId.startsWith('force_publish:')) {
        try {
          await listCommand.handleForcePublishButton(interaction);
        } catch (error) {
          logger.error('Force publish button failed', { error });
        }
      } else if (interaction.customId.startsWith('request_queue_page:')) {
        try {
          await listCommand.handleRequestQueuePageButton(interaction);
        } catch (error) {
          logger.error('Request queue page button failed', { error });
        }
      } else if (isVibecheckPromptInteraction(interaction.customId)) {
        try {
          await handleVibecheckPromptInteraction(interaction);
        } catch (error) {
          logger.error('Vibecheck prompt button failed', { error });
        }
      }
    } else if (interaction.isStringSelectMenu()) {
      if (isVibecheckPromptInteraction(interaction.customId)) {
        try {
          await handleVibecheckPromptInteraction(interaction);
        } catch (error) {
          logger.error('Vibecheck prompt select menu failed', { error });
        }
      }
    } else if (interaction.isModalSubmit()) {
      if (interaction.customId.startsWith('note-write:')) {
        try {
          await noteCommand.handleModalSubmit(interaction);
        } catch (error) {
          logger.error('Modal submit failed', { error });
        }
      } else if (interaction.customId.startsWith('write_note_modal:')) {
        try {
          await listCommand.handleModalSubmit(interaction);
        } catch (error) {
          logger.error('Write note modal submit failed', { error });
        }
      }
    }
  }

  private async initializeNotePublisher(): Promise<void> {
    try {
      const noteContextService = new NoteContextService();
      const configService = new NotePublisherConfigService();

      const { getRedisClient } = await import('./redis-client.js');
      const { DistributedLock } = await import('./utils/distributed-lock.js');
      const redisClient = getRedisClient();
      const distributedLock = redisClient ? new DistributedLock(redisClient) : null;

      if (!distributedLock) {
        logger.warn('Redis not available - NotePublisherService will run without distributed locking (not suitable for multi-instance deployment)');
      }

      this.notePublisherService = new NotePublisherService(
        this.client,
        noteContextService,
        configService,
        distributedLock
      );

      this.natsSubscriber = new NatsSubscriber();
      await this.natsSubscriber.connect();

      await this.natsSubscriber.subscribeToScoreUpdates(
        this.notePublisherService.handleScoreUpdate.bind(this.notePublisherService)
      );

      logger.info('Note publisher system connected to NATS and subscribed to score updates');

      this.vibecheckProgressService = new VibecheckProgressService(this.client);
      await this.natsSubscriber.subscribeToProgressUpdates(
        this.vibecheckProgressService.handleProgressEvent.bind(this.vibecheckProgressService)
      );

      logger.info('Vibecheck progress service initialized and subscribed to progress updates');
    } catch (error) {
      logger.error('Failed to initialize note publisher system - JetStream is required', {
        error: error instanceof Error ? error.message : String(error),
        stack: error instanceof Error ? error.stack : undefined,
      });
      throw error;
    }
  }

  private async initializeMessageMonitoring(): Promise<void> {
    try {
      const { getRedisClient } = await import('./redis-client.js');
      const redisClient = getRedisClient();

      if (!redisClient) {
        throw new Error('Redis is required for MessageMonitorService');
      }

      this.messageMonitorService = new MessageMonitorService(
        this.client,
        redisClient
      );
      this.messageMonitorService.initialize();

      logger.info('Message monitoring system initialized successfully');
    } catch (error) {
      logger.error('Failed to initialize message monitoring system', {
        error: error instanceof Error ? error.message : String(error),
        stack: error instanceof Error ? error.stack : undefined,
      });
    }
  }

  private async onMessage(message: Message): Promise<void> {
    if (!this.messageMonitorService) {
      return;
    }

    try {
      await this.messageMonitorService.handleMessage(message);
    } catch (error) {
      logger.error('Message handler failed', {
        messageId: message.id,
        channelId: message.channelId,
        guildId: message.guildId,
        error: error instanceof Error ? error.message : String(error),
        stack: error instanceof Error ? error.stack : undefined,
      });
    }
  }

  private async ensureBotChannelsForAllGuilds(): Promise<void> {
    if (!this.guildOnboardingService || !this.permissionModeService) {
      logger.warn('Services not initialized, skipping channel check');
      return;
    }

    logger.info('Ensuring bot channels exist for all guilds', {
      guildCount: this.client.guilds.cache.size,
    });

    for (const guild of this.client.guilds.cache.values()) {
      try {
        const mode = this.permissionModeService.detectMode(guild);

        if (mode === 'minimal') {
          logger.debug('Guild in minimal mode, skipping bot channel creation on startup', {
            guildId: guild.id,
            guildName: guild.name,
          });
          continue;
        }

        if (!this.botChannelService || !this.guildConfigService) {
          logger.warn('Bot channel services not initialized for full mode guild', {
            guildId: guild.id,
          });
          continue;
        }

        const result = await this.botChannelService.ensureChannelExists(
          guild,
          this.guildConfigService
        );

        await this.guildOnboardingService.postWelcomeToChannel(result.channel);
      } catch (error) {
        logger.error('Failed to ensure bot channel for guild on startup', {
          guildId: guild.id,
          guildName: guild.name,
          error: error instanceof Error ? error.message : String(error),
          stack: error instanceof Error ? error.stack : undefined,
        });
      }
    }

    logger.info('Finished ensuring bot channels for all guilds');
  }

  private async syncCommunityNames(): Promise<void> {
    logger.info('Starting community name sync', {
      guildCount: this.client.guilds.cache.size,
    });

    for (const guild of this.client.guilds.cache.values()) {
      try {
        const communityServer = await apiClient.getCommunityServerByPlatformId(guild.id);
        const storedName = communityServer.data.attributes.name;

        const serverStats = { member_count: guild.memberCount };
        await apiClient.updateCommunityServerName(guild.id, guild.name, serverStats);
        if (storedName !== guild.name) {
          logger.info('Synced community server name', {
            guildId: guild.id,
            oldName: storedName,
            newName: guild.name,
            memberCount: guild.memberCount,
          });
        }

        const monitoredChannels = await apiClient.listMonitoredChannels(
          guild.id,
          false
        );

        for (const resource of monitoredChannels.data) {
          const channelId = resource.attributes.channel_id;
          const storedChannelName = resource.attributes.name;

          try {
            const discordChannel = await this.client.channels.fetch(channelId);

            if (!discordChannel || !('name' in discordChannel)) {
              continue;
            }

            const currentName = discordChannel.name;
            if (storedChannelName !== currentName) {
              await apiClient.updateMonitoredChannel(
                channelId,
                { name: currentName },
                undefined,
                guild.id
              );
              logger.info('Synced monitored channel name', {
                guildId: guild.id,
                channelId,
                oldName: storedChannelName,
                newName: currentName,
              });
            }
          } catch (channelError) {
            logger.warn('Could not fetch Discord channel for name sync', {
              guildId: guild.id,
              channelId,
              error: channelError instanceof Error ? channelError.message : String(channelError),
            });
          }
        }
      } catch (error) {
        logger.warn('Failed to sync names for guild', {
          guildId: guild.id,
          guildName: guild.name,
          error: error instanceof Error ? error.message : String(error),
        });
      }
    }

    logger.info('Finished community name sync');
  }

  private async onGuildCreate(guild: Guild): Promise<void> {
    try {
      logger.info('Bot joined new guild', {
        guildId: guild.id,
        guildName: guild.name,
        memberCount: guild.memberCount,
      });

      if (this.permissionModeService && this.guildOnboardingService) {
        const mode = this.permissionModeService.detectMode(guild);

        if (mode === 'minimal') {
          // In minimal mode, DM is the only option - no channel fallback because
          // minimal mode means we don't have channel creation permissions
          try {
            const owner = await guild.fetchOwner();
            await this.guildOnboardingService.sendWelcomeDM(guild, owner.user, mode);
          } catch (ownerError) {
            logger.error('Failed to send welcome DM to guild owner in minimal mode', {
              guildId: guild.id,
              guildName: guild.name,
              error: ownerError instanceof Error ? ownerError.message : String(ownerError),
            });
          }
        } else if (this.botChannelService && this.guildConfigService) {
          try {
            const result = await this.botChannelService.ensureChannelExists(
              guild,
              this.guildConfigService
            );

            try {
              const owner = await guild.fetchOwner();
              await this.guildOnboardingService.postWelcomeToChannel(result.channel, {
                admin: owner.user,
              });
            } catch (ownerError) {
              logger.debug('Failed to fetch guild owner for vibe check prompt, skipping', {
                guildId: guild.id,
                error: ownerError instanceof Error ? ownerError.message : String(ownerError),
              });
              await this.guildOnboardingService.postWelcomeToChannel(result.channel);
            }
          } catch (error) {
            logger.error('Failed to create bot channel for new guild', {
              guildId: guild.id,
              guildName: guild.name,
              error: error instanceof Error ? error.message : String(error),
              stack: error instanceof Error ? error.stack : undefined,
            });
          }
        } else {
          logger.warn('Bot channel services not initialized for new guild in full mode', {
            guildId: guild.id,
          });
        }
      } else {
        logger.warn('Services not initialized for new guild', {
          guildId: guild.id,
        });
      }

      if (config.autoMonitorChannels && this.guildSetupService) {
        await this.guildSetupService.autoRegisterChannels(guild);
      } else if (!config.autoMonitorChannels) {
        logger.info('Auto-monitoring disabled, skipping channel registration', {
          guildId: guild.id,
          guildName: guild.name,
        });
      } else {
        logger.warn('Guild setup service not initialized', {
          guildId: guild.id,
        });
      }
    } catch (error) {
      logger.error('Failed to handle guild join', {
        guildId: guild.id,
        guildName: guild.name,
        error: error instanceof Error ? error.message : String(error),
        stack: error instanceof Error ? error.stack : undefined,
      });
    }
  }

  async onChannelUpdate(
    oldChannel: DMChannel | NonThreadGuildBasedChannel,
    newChannel: DMChannel | NonThreadGuildBasedChannel
  ): Promise<void> {
    if (!this.guildConfigService) {
      return;
    }

    if (oldChannel.isDMBased() || newChannel.isDMBased()) {
      return;
    }

    if (!('name' in oldChannel) || !('name' in newChannel)) {
      return;
    }

    if (oldChannel.type !== ChannelType.GuildText) {
      return;
    }

    if (oldChannel.name === newChannel.name) {
      return;
    }

    const guild = newChannel.guild;

    try {
      const configuredName = (await this.guildConfigService.get(
        guild.id,
        ConfigKey.BOT_CHANNEL_NAME
      )) as string;

      if (oldChannel.name.toLowerCase() !== configuredName.toLowerCase()) {
        return;
      }

      await this.guildConfigService.set(
        guild.id,
        ConfigKey.BOT_CHANNEL_NAME,
        newChannel.name,
        'system'
      );

      logger.info('Bot channel renamed - config updated', {
        guildId: guild.id,
        guildName: guild.name,
        oldName: oldChannel.name,
        newName: newChannel.name,
      });
    } catch (error) {
      logger.error('Failed to update bot channel config after rename', {
        guildId: guild.id,
        oldName: oldChannel.name,
        newName: newChannel.name,
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }

  private onError(error: Error): void {
    logger.error('Client error', { error: error.message, stack: error.stack });
  }

  private async waitForServerReady(maxWaitMs: number = 60000): Promise<{ ready: boolean; waitedMs: number }> {
    const startTime = Date.now();
    let waitMs = 500;
    const maxBackoff = 8000;

    logger.info('Waiting for server API to be ready...');

    while (Date.now() - startTime < maxWaitMs) {
      try {
        await apiClient.healthCheck();
        const waitedMs = Date.now() - startTime;
        logger.info('Server API is ready', { waitedMs });
        return { ready: true, waitedMs };
      } catch (error) {
        const elapsed = Date.now() - startTime;
        const remaining = maxWaitMs - elapsed;

        if (remaining <= 0) {
          break;
        }

        logger.debug('Server not ready yet, retrying...', {
          error: error instanceof Error ? error.message : String(error),
          nextRetryMs: Math.min(waitMs, remaining),
          elapsedMs: elapsed,
        });

        await this.delay(Math.min(waitMs, remaining));
        waitMs = Math.min(waitMs * 2, maxBackoff);
      }
    }

    const waitedMs = Date.now() - startTime;
    logger.warn('Server API not ready after timeout, continuing with limited functionality', {
      waitedMs,
      maxWaitMs,
    });
    return { ready: false, waitedMs };
  }

  private delay(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  async start(): Promise<void> {
    try {
      logger.info('Starting bot initialization');

      logger.info('Initializing NATS publisher connection');
      try {
        await initializeNatsPublisher();
        logger.info('NATS publisher initialized successfully');
      } catch (error) {
        logger.error('Failed to initialize NATS publisher - bot cannot start without NATS', {
          error: error instanceof Error ? error.message : String(error),
          stack: error instanceof Error ? error.stack : undefined,
        });
        throw error;
      }

      logger.info('Starting cache service');
      cache.start();
      logger.info('Cache service started');

      if (config.healthCheck.enabled) {
        this.startHealthCheckServer();
      }

      logger.info('Connecting to Discord Gateway');
      await this.client.login(config.discordToken);

      logger.info('Bot started successfully');
    } catch (error) {
      logger.error('Failed to start bot', {
        error: error instanceof Error ? error.message : String(error),
        stack: error instanceof Error ? error.stack : undefined,
      });
      throw error;
    }
  }

  private startHealthCheckServer(): void {
    this.healthCheckServer = express();
    this.healthCheckPort = config.healthCheck.port;

    this.healthCheckServer.get('/health', (_req, res) => {
      const health = {
        status: this.isReady ? 'healthy' : 'starting',
        instance: config.instanceId,
        uptime: process.uptime(),
        timestamp: Date.now(),
        shard: this.client.shard
          ? {
              ids: this.client.shard.ids,
              count: this.client.shard.count,
            }
          : null,
        guilds: this.client.guilds.cache.size,
        ping: this.client.ws.ping,
      };

      res.status(200).json(health);
    });

    this.healthCheckServer.get('/ready', (_req, res) => {
      if (this.isReady) {
        res.status(200).json({ ready: true });
      } else {
        res.status(503).json({ ready: false });
      }
    });

    this.healthCheckServer.get('/live', (_req, res) => {
      res.status(200).json({ alive: true });
    });

    this.healthCheckServer.get('/health/distributed', (_req, res) => {
      void (async (): Promise<void> => {
      const checks: Record<string, string | number> = {
        instance: config.instanceId,
      };
      let allHealthy = true;

      try {
        const { getRedisClient } = await import('./redis-client.js');
        const redisClient = getRedisClient();

        if (redisClient) {
          try {
            const pingStart = Date.now();
            await redisClient.ping();
            checks.redis = 'connected';
            checks.redis_latency_ms = Date.now() - pingStart;
          } catch (error) {
            checks.redis = 'error';
            checks.redis_error = error instanceof Error ? error.message : String(error);
            allHealthy = false;
          }
        } else {
          checks.redis = 'not_configured';
        }
      } catch (error) {
        checks.redis = 'unavailable';
        checks.redis_error = error instanceof Error ? error.message : String(error);
        allHealthy = false;
      }

      if (this.natsSubscriber) {
        checks.nats = this.natsSubscriber.isConnected() ? 'connected' : 'disconnected';
        if (!this.natsSubscriber.isConnected()) {
          allHealthy = false;
        }
      } else {
        checks.nats = 'not_initialized';
        allHealthy = false;
      }

      if (this.notePublisherService) {
        try {
          const { getRedisClient } = await import('./redis-client.js');
          const redisClient = getRedisClient();

          if (redisClient) {
            const { DistributedLock } = await import('./utils/distributed-lock.js');
            const lock = new DistributedLock(redisClient);
            const testKey = `healthcheck:lock:${config.instanceId}`;

            try {
              const acquired = await lock.acquire(testKey, { ttlMs: 5000, maxRetries: 1 });
              if (acquired) {
                await lock.release(testKey);
                checks.distributed_lock = 'ok';
              } else {
                checks.distributed_lock = 'contention';
              }
            } catch (error) {
              checks.distributed_lock = 'error';
              checks.lock_error = error instanceof Error ? error.message : String(error);
              allHealthy = false;
            }
          } else {
            checks.distributed_lock = 'redis_unavailable';
          }
        } catch (error) {
          checks.distributed_lock = 'error';
          checks.lock_error = error instanceof Error ? error.message : String(error);
          allHealthy = false;
        }
      } else {
        checks.distributed_lock = 'service_not_initialized';
      }

      if (this.messageMonitorService) {
        try {
          const metrics = await this.messageMonitorService.getMetrics();
          checks.message_queue_size = metrics.queueSize;
          checks.message_queue_utilization = `${metrics.utilizationPercent.toFixed(1)}%`;
          const lastProcessedTime = metrics.performance?.uptimeSeconds
            ? `${Math.floor(metrics.performance.uptimeSeconds)}s ago`
            : 'never';
          checks.last_message_processed = lastProcessedTime;
        } catch (error) {
          checks.message_monitor = 'error';
          checks.monitor_error = error instanceof Error ? error.message : String(error);
        }
      }

      const statusCode = allHealthy ? 200 : 503;
      res.status(statusCode).json({
        status: allHealthy ? 'healthy' : 'degraded',
        checks,
        timestamp: Date.now(),
      });
      })();
    });

    this.healthCheckServer.listen(this.healthCheckPort, () => {
      logger.info('Health check server started', {
        port: this.healthCheckPort,
      });
    });
  }

  async stop(): Promise<void> {
    logger.info('Stopping bot');

    try {
      if (this.messageMonitorService) {
        void this.messageMonitorService.shutdown();
        logger.info('Message monitoring service stopped');
      }
    } catch (error) {
      logger.warn('Message monitoring cleanup failed', { error });
    }

    try {
      if (this.natsSubscriber) {
        await this.natsSubscriber.close();
        logger.info('NATS subscriber closed');
      }
    } catch (error) {
      logger.warn('NATS subscriber cleanup failed', { error });
    }

    try {
      await closeNatsPublisher();
      logger.info('NATS publisher closed');
    } catch (error) {
      logger.warn('NATS publisher cleanup failed', { error });
    }

    if (this.healthCheckServer) {
      logger.info('Stopping health check server');
    }

    try {
      closeRedisClient();
      logger.info('Redis client closed');
    } catch (error) {
      logger.warn('Redis client cleanup failed', { error });
    }

    cache.stop();
    void this.client.destroy();
    this.isReady = false;

    logger.info('Bot stopped');
  }

  getClient(): Client {
    return this.client;
  }

  isRunning(): boolean {
    return this.isReady;
  }
}
