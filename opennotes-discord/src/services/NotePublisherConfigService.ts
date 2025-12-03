import { logger } from '../logger.js';
import { apiClient } from '../api-client.js';
import { ApiError } from '../lib/errors.js';

export interface NotePublisherConfig {
  guildId: string;
  channelId?: string;
  enabled: boolean;
  threshold?: number;
}

export interface ServerNotePublisherConfigRow {
  id: string | null;
  community_server_id: string;
  channel_id: string | null;
  enabled: boolean;
  threshold: number | null;
  updated_at: string | null;
  updated_by: string | null;
}

export class NotePublisherConfigService {
  private readonly defaultThreshold: number;

  constructor() {
    this.defaultThreshold = parseFloat(process.env.NOTE_PUBLISHER_SCORE_THRESHOLD || '0.7');

    if (this.defaultThreshold < 0 || this.defaultThreshold > 1) {
      throw new Error('NOTE_PUBLISHER_SCORE_THRESHOLD must be between 0.0 and 1.0');
    }
  }

  async getConfig(guildId: string, channelId?: string): Promise<NotePublisherConfig> {
    try {
      let channelConfig: ServerNotePublisherConfigRow | null = null;
      let serverConfig: ServerNotePublisherConfigRow | null = null;

      if (channelId) {
        channelConfig = await this.fetchConfig(guildId, channelId);
      }

      serverConfig = await this.fetchConfig(guildId);

      const config = channelConfig || serverConfig;

      if (!config) {
        return {
          guildId,
          channelId,
          enabled: true,
          threshold: this.defaultThreshold,
        };
      }

      return {
        guildId: config.community_server_id,
        channelId: config.channel_id || undefined,
        enabled: config.enabled,
        threshold: config.threshold || this.defaultThreshold,
      };
    } catch (error) {
      logger.error('Failed to get note-publisher config', {
        guildId,
        channelId,
        error: error instanceof Error ? error.message : String(error),
      });

      return {
        guildId,
        channelId,
        enabled: true,
        threshold: this.defaultThreshold,
      };
    }
  }

  async setConfig(
    guildId: string,
    enabled: boolean,
    threshold?: number,
    channelId?: string,
    updatedBy?: string
  ): Promise<void> {
    try {
      if (threshold !== undefined && (threshold < 0 || threshold > 1)) {
        throw new Error('Threshold must be between 0.0 and 1.0');
      }

      await apiClient.setNotePublisherConfig(
        guildId,
        enabled,
        threshold,
        channelId,
        updatedBy
      );

      logger.info('Updated note-publisher config', {
        guildId,
        channelId,
        enabled,
        threshold,
      });
    } catch (error) {
      logger.error('Failed to set note-publisher config', {
        guildId,
        channelId,
        enabled,
        threshold,
        error: error instanceof Error ? error.message : String(error),
      });
      throw error;
    }
  }

  async disableChannel(guildId: string, channelId: string, updatedBy?: string): Promise<void> {
    await this.setConfig(guildId, false, undefined, channelId, updatedBy);
  }

  async enableChannel(guildId: string, channelId: string, updatedBy?: string): Promise<void> {
    await this.setConfig(guildId, true, undefined, channelId, updatedBy);
  }

  async setThreshold(
    guildId: string,
    threshold: number,
    channelId?: string,
    updatedBy?: string
  ): Promise<void> {
    const config = await this.getConfig(guildId, channelId);
    await this.setConfig(guildId, config.enabled, threshold, channelId, updatedBy);
  }

  getDefaultThreshold(): number {
    return this.defaultThreshold;
  }

  private async fetchConfig(
    guildId: string,
    channelId?: string
  ): Promise<ServerNotePublisherConfigRow | null> {
    try {
      const response = await apiClient.getNotePublisherConfig(guildId, channelId);
      return response;
    } catch (error) {
      if (error instanceof ApiError && error.statusCode === 404) {
        return null;
      }
      throw error;
    }
  }
}
