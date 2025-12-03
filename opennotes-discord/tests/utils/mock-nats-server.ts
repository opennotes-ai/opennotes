import { NatsConnection, connect, StringCodec, JetStreamClient, StorageType, RetentionPolicy } from 'nats';

export async function checkNatsAvailability(port: number = 4222): Promise<boolean> {
  try {
    const nc = await connect({
      servers: `nats://localhost:${port}`,
      maxReconnectAttempts: 1,
      reconnectTimeWait: 100,
      timeout: 1000,
    });
    await nc.close();
    return true;
  } catch {
    return false;
  }
}

export class MockNatsServer {
  private nc?: NatsConnection;
  private js?: JetStreamClient;
  private readonly codec = StringCodec();
  private readonly streamName: string;

  constructor() {
    const testId = Date.now();
    this.streamName = `OPENNOTES_${testId}`;
  }

  async start(port: number = 4222): Promise<string> {
    const url = `nats://localhost:${port}`;

    try {
      this.nc = await connect({
        servers: url,
        maxReconnectAttempts: 3,
        reconnectTimeWait: 100,
        name: 'mock-nats-test-server',
      });

      this.js = this.nc.jetstream();
      await this._ensureStream();

      return url;
    } catch (error) {
      throw new Error(
        `Failed to connect to NATS server at ${url}. ` +
          `Make sure NATS is running: docker compose up nats -d`
      );
    }
  }

  private async _ensureStream(): Promise<void> {
    if (!this.js) {
      throw new Error('JetStream client not initialized');
    }

    const jsm = await this.nc!.jetstreamManager();

    try {
      const info = await jsm.streams.info(this.streamName);
      console.log(`Stream '${this.streamName}' already exists with ${info.state.messages} messages`);
    } catch (error) {
      console.log(`Creating stream '${this.streamName}'...`);
      try {
        const streamInfo = await jsm.streams.add({
          name: this.streamName,
          subjects: [`${this.streamName}.>`],
          retention: RetentionPolicy.Limits,
          storage: StorageType.File,
          max_age: 86400_000_000_000,
          max_msgs: 10000,
          max_bytes: 10485760,
          duplicate_window: 120_000_000_000,
        });
        console.log(`Stream '${this.streamName}' created successfully:`, streamInfo.config);
      } catch (createError) {
        console.error(`Failed to create stream '${this.streamName}':`, createError);
        throw createError;
      }
    }
  }

  async publishScoreUpdate(event: any): Promise<void> {
    if (!this.js) {
      throw new Error('Mock NATS server not started');
    }

    const subject = `${this.streamName}.note_score_updated`;
    const data = this.codec.encode(JSON.stringify(event));

    await this.js.publish(subject, data);
  }

  async publishMultiple(events: any[]): Promise<void> {
    if (!this.nc) {
      throw new Error('Mock NATS server not started');
    }

    for (const event of events) {
      await this.publishScoreUpdate(event);
    }
  }

  async publishConcurrent(events: any[]): Promise<void> {
    if (!this.js) {
      throw new Error('Mock NATS server not started');
    }

    const subject = `${this.streamName}.note_score_updated`;

    const promises = events.map((event) => {
      const data = this.codec.encode(JSON.stringify(event));
      return this.js!.publish(subject, data);
    });

    await Promise.all(promises);
  }

  async purgeStream(): Promise<void> {
    if (!this.js) {
      throw new Error('Mock NATS server not started');
    }

    const jsm = await this.nc!.jetstreamManager();
    try {
      await jsm.streams.purge(this.streamName);
      console.log(`Stream '${this.streamName}' purged successfully`);
    } catch (error) {
      console.error(`Failed to purge stream '${this.streamName}':`, error);
    }
  }

  async close(): Promise<void> {
    try {
      if (this.js) {
        const jsm = await this.nc!.jetstreamManager();
        try {
          await jsm.streams.delete(this.streamName);
          console.log(`Stream '${this.streamName}' deleted successfully`);
        } catch (error) {
          console.error(`Failed to delete stream '${this.streamName}':`, error);
        }
      }
    } catch (error) {
      console.error('Error during stream cleanup:', error);
    }

    if (this.nc) {
      await this.nc.drain();
      await this.nc.close();
      this.nc = undefined;
    }
  }

  getConnection(): NatsConnection | undefined {
    return this.nc;
  }

  getStreamName(): string {
    return this.streamName;
  }

  getSubject(): string {
    return `${this.streamName}.note_score_updated`;
  }
}
