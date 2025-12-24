import { Factory } from 'fishery';
import { jest } from '@jest/globals';

type LogMeta = Record<string, unknown>;
type LogMethod = (message: string, meta?: LogMeta) => void;

export interface MockLogger {
  error: ReturnType<typeof jest.fn<LogMethod>>;
  warn: ReturnType<typeof jest.fn<LogMethod>>;
  info: ReturnType<typeof jest.fn<LogMethod>>;
  debug: ReturnType<typeof jest.fn<LogMethod>>;
}

export type LoggerTransientParams = {
  errorImpl?: LogMethod;
  warnImpl?: LogMethod;
  infoImpl?: LogMethod;
  debugImpl?: LogMethod;
};

export const loggerFactory = Factory.define<MockLogger, LoggerTransientParams>(
  ({ transientParams }) => {
    const { errorImpl, warnImpl, infoImpl, debugImpl } = transientParams;

    return {
      error: errorImpl
        ? jest.fn<LogMethod>(errorImpl)
        : jest.fn<LogMethod>(),
      warn: warnImpl
        ? jest.fn<LogMethod>(warnImpl)
        : jest.fn<LogMethod>(),
      info: infoImpl
        ? jest.fn<LogMethod>(infoImpl)
        : jest.fn<LogMethod>(),
      debug: debugImpl
        ? jest.fn<LogMethod>(debugImpl)
        : jest.fn<LogMethod>(),
    };
  }
);
