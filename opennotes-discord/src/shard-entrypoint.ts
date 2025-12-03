import { OpenNotesShardingManager } from './sharding-manager.js';
import { logger } from './logger.js';
import { config } from './config.js';

async function main(): Promise<void> {
  if (!config.sharding.enabled) {
    logger.error('Sharding is disabled. Use regular bot entrypoint instead.');
    process.exit(1);
  }

  try {
    const shardManager = new OpenNotesShardingManager();

    await shardManager.spawn();

    logger.info('Shard manager initialized successfully');

    setInterval(() => {
      void (async (): Promise<void> => {
        try {
          const stats = await shardManager.getAggregatedStats();
          logger.debug('Cluster stats', {
            totalShards: stats.totalShards,
            totalGuilds: stats.totalGuilds,
            totalUsers: stats.totalUsers,
            averagePing: stats.averagePing,
          });
        } catch (error) {
          logger.warn('Failed to collect cluster stats', {
            error: error instanceof Error ? error.message : String(error),
          });
        }
      })();
    }, 60000);
  } catch (error) {
    logger.error('Failed to start shard manager', {
      error: error instanceof Error ? error.message : String(error),
    });
    process.exit(1);
  }
}

function setupShutdownHandlers(): void {
  const signals = ['SIGTERM', 'SIGINT'];
  let isShuttingDown = false;

  signals.forEach(signal => {
    process.on(signal, () => {
      void (async (): Promise<void> => {
        if (isShuttingDown) {
          logger.warn(`Received ${signal} during shutdown, ignoring`);
          return;
        }
        isShuttingDown = true;
        logger.info(`Received ${signal}, shutting down shard manager`);
        process.exit(0);
      })();
    });
  });

  process.on('uncaughtException', error => {
    logger.error('Uncaught exception', { error: error.message, stack: error.stack });
    if (!isShuttingDown) {
      isShuttingDown = true;
    }
    process.exit(1);
  });

  process.on('unhandledRejection', reason => {
    logger.error('Unhandled rejection', {
      reason: reason instanceof Error ? reason.message : String(reason),
      stack: reason instanceof Error ? reason.stack : undefined,
    });
    if (!isShuttingDown) {
      isShuttingDown = true;
    }
    process.exit(1);
  });
}

setupShutdownHandlers();
void main();
