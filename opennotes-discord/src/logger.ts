import { config } from './config.js';

enum LogLevel {
  DEBUG = 0,
  INFO = 1,
  WARN = 2,
  ERROR = 3,
}

const LOG_LEVELS: Record<string, LogLevel> = {
  debug: LogLevel.DEBUG,
  info: LogLevel.INFO,
  warn: LogLevel.WARN,
  error: LogLevel.ERROR,
};

type LogMeta = Record<string, unknown>;

class Logger {
  private level: LogLevel;

  constructor(level: string) {
    this.level = LOG_LEVELS[level] || LogLevel.INFO;
  }

  private log(level: LogLevel, message: string, meta?: LogMeta): void {
    if (level < this.level) {return;}

    const timestamp = new Date().toISOString();
    const levelName = LogLevel[level];

    const logEntry = {
      timestamp,
      level: levelName,
      message,
      ...meta,
    };

    console.log(JSON.stringify(logEntry));
  }

  debug(message: string, meta?: LogMeta): void {
    this.log(LogLevel.DEBUG, message, meta);
  }

  info(message: string, meta?: LogMeta): void {
    this.log(LogLevel.INFO, message, meta);
  }

  warn(message: string, meta?: LogMeta): void {
    this.log(LogLevel.WARN, message, meta);
  }

  error(message: string, meta?: LogMeta): void {
    this.log(LogLevel.ERROR, message, meta);
  }
}

export const logger = new Logger(config.logLevel);
