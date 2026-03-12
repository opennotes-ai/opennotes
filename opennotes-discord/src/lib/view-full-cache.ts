import { cache } from '../cache.js';
import { logger } from '../logger.js';

export async function storeViewFullContent(
  customId: string,
  fullText: string,
  ttlSeconds: number,
  context: Record<string, unknown>,
  warningMessage: string
): Promise<boolean> {
  try {
    const stored = await cache.set(customId, fullText, ttlSeconds);
    if (!stored) {
      logger.warn(warningMessage, {
        ...context,
        custom_id: customId,
        error: 'cache.set returned false',
      });
    }
    return stored;
  } catch (error) {
    logger.warn(warningMessage, {
      ...context,
      custom_id: customId,
      error: error instanceof Error ? error.message : String(error),
    });
    return false;
  }
}
