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

const SEVERITY_NUMBERS: Record<LogLevel, number> = {
  [LogLevel.DEBUG]: 5,
  [LogLevel.INFO]: 9,
  [LogLevel.WARN]: 13,
  [LogLevel.ERROR]: 17,
};

const SERVICE_NAME = 'opennotes-discord';

type LogMeta = Record<string, unknown>;

function getTraceContext(): Record<string, unknown> {
  try {
    // OpenTelemetry API is provided by @middleware.io/node-apm
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { trace } = require('@opentelemetry/api');
    const span = trace.getActiveSpan();
    if (span) {
      const ctx = span.spanContext();
      return {
        otelTraceID: ctx.traceId,
        otelSpanID: ctx.spanId,
        otelTraceSampled: (ctx.traceFlags & 1) === 1,
        otelServiceName: SERVICE_NAME,
      };
    }
  } catch {
    // OpenTelemetry not available
  }
  return {};
}

class Logger {
  private level: LogLevel;

  constructor(level: string) {
    this.level = LOG_LEVELS[level] || LogLevel.INFO;
  }

  private log(level: LogLevel, message: string, meta?: LogMeta): void {
    if (level < this.level) {return;}

    const timestamp = new Date().toISOString();
    const levelName = LogLevel[level];
    const traceContext = getTraceContext();

    const logEntry = {
      timestamp,
      level: levelName,
      severity_text: levelName,
      severity_number: SEVERITY_NUMBERS[level],
      message,
      ...traceContext,
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
