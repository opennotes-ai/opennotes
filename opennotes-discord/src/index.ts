import { Bot } from './bot.js';
import { logger } from './logger.js';

const bot = new Bot();

async function main(): Promise<void> {
  try {
    await bot.start();
  } catch (error) {
    logger.error('Failed to start application', { error });
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
        logger.info(`Received ${signal}, shutting down gracefully`);
        await bot.stop();
        process.exit(0);
      })();
    });
  });

  process.on('uncaughtException', (error: Error) => {
    void (async () => {
      logger.error('Uncaught exception', { error: error.message, stack: error.stack });
      if (!isShuttingDown) {
        isShuttingDown = true;
        try {
          await Promise.race([
            bot.stop(),
            new Promise((_, reject) => setTimeout(() => reject(new Error('Shutdown timeout')), 5000))
          ]);
        } catch (cleanupError) {
          logger.error('Error during cleanup', {
            error: cleanupError instanceof Error ? cleanupError.message : String(cleanupError)
          });
        }
      }
      process.exit(1);
    })();
  });

  process.on('unhandledRejection', (reason) => {
    void (async () => {
      logger.error('Unhandled rejection', {
        reason: reason instanceof Error ? reason.message : String(reason),
        stack: reason instanceof Error ? reason.stack : undefined
      });
      if (!isShuttingDown) {
        isShuttingDown = true;
        try {
          await Promise.race([
            bot.stop(),
            new Promise((_, reject) => setTimeout(() => reject(new Error('Shutdown timeout')), 5000))
          ]);
        } catch (cleanupError) {
          logger.error('Error during cleanup', {
            error: cleanupError instanceof Error ? cleanupError.message : String(cleanupError)
          });
        }
      }
      process.exit(1);
    })();
  });
}

setupShutdownHandlers();
void main();
