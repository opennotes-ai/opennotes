import { cache } from '../cache.js';
import { logger } from '../logger.js';

export interface NoteContext {
  noteId: string;
  originalMessageId: string;
  channelId: string;
  guildId: string;
  authorId: string;
}

export class NoteContextService {
  private readonly CACHE_TTL = 86400 * 7; // 7 days
  private readonly KEY_PREFIX = 'note_context:';

  async storeNoteContext(context: NoteContext): Promise<void> {
    const key = this.getNoteContextKey(context.noteId);

    try {
      await cache.set(key, context, this.CACHE_TTL);

      logger.debug('Stored note context', {
        noteId: context.noteId,
        originalMessageId: context.originalMessageId,
        channelId: context.channelId,
        guildId: context.guildId,
      });
    } catch (error) {
      logger.error('Failed to store note context', {
        noteId: context.noteId,
        error: error instanceof Error ? error.message : String(error),
      });
      throw error;
    }
  }

  async getNoteContext(noteId: string): Promise<NoteContext | null> {
    const key = this.getNoteContextKey(noteId);

    try {
      const context = await cache.get<NoteContext>(key);

      if (context) {
        logger.debug('Retrieved note context from cache', { noteId });
        return context;
      }

      logger.debug('Note context not found in cache', { noteId });
      return null;
    } catch (error) {
      logger.error('Failed to retrieve note context', {
        noteId,
        error: error instanceof Error ? error.message : String(error),
      });
      return null;
    }
  }

  async deleteNoteContext(noteId: string): Promise<void> {
    const key = this.getNoteContextKey(noteId);

    try {
      await cache.delete(key);
      logger.debug('Deleted note context', { noteId });
    } catch (error) {
      logger.error('Failed to delete note context', {
        noteId,
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }

  private getNoteContextKey(noteId: string): string {
    return `${this.KEY_PREFIX}${noteId}`;
  }
}
