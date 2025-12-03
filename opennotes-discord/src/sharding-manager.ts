import { ShardingManager, Shard } from 'discord.js';
import { config } from './config.js';
import { logger } from './logger.js';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

export class OpenNotesShardingManager {
  private manager: ShardingManager;
  private shardStats: Map<number, ShardStats> = new Map();

  constructor() {
    const botPath = join(__dirname, 'index.js');

    this.manager = new ShardingManager(botPath, {
      token: config.discordToken,
      totalShards: config.sharding.totalShards,
      shardList: config.sharding.shardList,
      respawn: config.sharding.respawn,
      mode: 'process',
    });

    this.setupEventHandlers();
  }

  private setupEventHandlers(): void {
    this.manager.on('shardCreate', (shard: Shard) => {
      logger.info('Shard created', {
        shardId: shard.id,
        totalShards: this.manager.totalShards,
      });

      this.initializeShardStats(shard.id);
      this.setupShardEventHandlers(shard);
    });
  }

  private initializeShardStats(shardId: number): void {
    this.shardStats.set(shardId, {
      shardId,
      status: 'starting',
      guilds: 0,
      ping: 0,
      uptime: 0,
      lastHeartbeat: Date.now(),
      restarts: 0,
    });
  }

  private setupShardEventHandlers(shard: Shard): void {
    shard.on('ready', () => {
      logger.info('Shard ready', { shardId: shard.id });
      this.updateShardStatus(shard.id, 'ready');
    });

    shard.on('disconnect', () => {
      logger.warn('Shard disconnected', { shardId: shard.id });
      this.updateShardStatus(shard.id, 'disconnected');
    });

    shard.on('reconnecting', () => {
      logger.info('Shard reconnecting', { shardId: shard.id });
      this.updateShardStatus(shard.id, 'reconnecting');
    });

    shard.on('death', () => {
      logger.error('Shard died', { shardId: shard.id });
      this.updateShardStatus(shard.id, 'dead');
      this.incrementShardRestarts(shard.id);

      if (config.sharding.respawn) {
        logger.info('Shard will respawn automatically', { shardId: shard.id });
      }
    });

    shard.on('error', (error: Error) => {
      logger.error('Shard error', {
        shardId: shard.id,
        error: error.message,
        stack: error.stack,
      });
    });

    this.setupShardStatsCollection(shard);
  }

  private setupShardStatsCollection(shard: Shard): void {
    setInterval(() => {
      void (async (): Promise<void> => {
        try {
          const stats = await shard.fetchClientValue('ws.ping') as number;
          const guilds = await shard.fetchClientValue('guilds.cache.size') as number;
          const uptime = await shard.fetchClientValue('uptime') as number;

          this.updateShardStats(shard.id, {
            ping: stats,
            guilds,
            uptime,
            lastHeartbeat: Date.now(),
          });
        } catch {
          logger.debug('Failed to fetch shard stats (shard may not be ready)', {
            shardId: shard.id,
          });
        }
      })();
    }, 30000);
  }

  private updateShardStatus(shardId: number, status: ShardStatus): void {
    const stats = this.shardStats.get(shardId);
    if (stats) {
      stats.status = status;
      this.shardStats.set(shardId, stats);
    }
  }

  private updateShardStats(shardId: number, update: Partial<ShardStats>): void {
    const stats = this.shardStats.get(shardId);
    if (stats) {
      this.shardStats.set(shardId, { ...stats, ...update });
    }
  }

  private incrementShardRestarts(shardId: number): void {
    const stats = this.shardStats.get(shardId);
    if (stats) {
      stats.restarts += 1;
      this.shardStats.set(shardId, stats);
    }
  }

  async getAggregatedStats(): Promise<AggregatedStats> {
    try {
      const results = await this.manager.broadcastEval(client => ({
        guilds: client.guilds.cache.size,
        users: client.guilds.cache.reduce((acc, guild) => acc + guild.memberCount, 0),
        channels: client.channels.cache.size,
        uptime: client.uptime || 0,
        ping: client.ws.ping,
      }));

      const totalGuilds = results.reduce((acc, r) => acc + r.guilds, 0);
      const totalUsers = results.reduce((acc, r) => acc + r.users, 0);
      const totalChannels = results.reduce((acc, r) => acc + r.channels, 0);
      const avgPing = results.reduce((acc, r) => acc + r.ping, 0) / results.length;
      const maxUptime = Math.max(...results.map(r => r.uptime));

      return {
        totalShards: typeof this.manager.totalShards === 'number' ? this.manager.totalShards : 0,
        totalGuilds,
        totalUsers,
        totalChannels,
        averagePing: Math.round(avgPing),
        uptime: maxUptime,
        shards: Array.from(this.shardStats.values()),
      };
    } catch (error) {
      logger.error('Failed to get aggregated stats', {
        error: error instanceof Error ? error.message : String(error),
      });
      throw error;
    }
  }

  async spawn(): Promise<void> {
    try {
      logger.info('Spawning shards', {
        totalShards: config.sharding.totalShards,
        shardList: config.sharding.shardList,
        respawn: config.sharding.respawn,
      });

      await this.manager.spawn({ timeout: 60000 });

      logger.info('All shards spawned successfully', {
        totalShards: this.manager.totalShards,
      });

      this.startStatsLogger();
    } catch (error) {
      logger.error('Failed to spawn shards', {
        error: error instanceof Error ? error.message : String(error),
      });
      throw error;
    }
  }

  private startStatsLogger(): void {
    setInterval(() => {
      void (async (): Promise<void> => {
        try {
          const stats = await this.getAggregatedStats();
          logger.info('Shard cluster stats', {
            totalShards: stats.totalShards,
            totalGuilds: stats.totalGuilds,
            totalUsers: stats.totalUsers,
            averagePing: stats.averagePing,
            uptimeHours: Math.round(stats.uptime / (1000 * 60 * 60)),
          });
        } catch {
          logger.debug('Stats logger failed (shards may not be ready)');
        }
      })();
    }, 300000);
  }

  getManager(): ShardingManager {
    return this.manager;
  }

  getShardStats(): Map<number, ShardStats> {
    return this.shardStats;
  }
}

interface ShardStats {
  shardId: number;
  status: ShardStatus;
  guilds: number;
  ping: number;
  uptime: number;
  lastHeartbeat: number;
  restarts: number;
}

type ShardStatus = 'starting' | 'ready' | 'disconnected' | 'reconnecting' | 'dead';

interface AggregatedStats {
  totalShards: number;
  totalGuilds: number;
  totalUsers: number;
  totalChannels: number;
  averagePing: number;
  uptime: number;
  shards: ShardStats[];
  [key: string]: number | ShardStats[];
}
