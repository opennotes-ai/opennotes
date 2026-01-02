/**
 * OpenTelemetry SDK initialization for the Discord bot.
 *
 * Configures distributed tracing with:
 * - W3C Trace Context propagation (traceparent/tracestate headers)
 * - W3C Baggage propagation (user context)
 * - OTLP HTTP exporter for Middleware.io
 * - Auto-instrumentation for HTTP/fetch calls
 */

import { NodeSDK } from '@opentelemetry/sdk-node';
import { Resource } from '@opentelemetry/resources';
import { ATTR_SERVICE_NAME, ATTR_SERVICE_VERSION, SEMRESATTRS_DEPLOYMENT_ENVIRONMENT } from '@opentelemetry/semantic-conventions';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import {
  BatchSpanProcessor,
  ConsoleSpanExporter,
  SimpleSpanProcessor,
  SpanProcessor,
  ReadableSpan,
} from '@opentelemetry/sdk-trace-base';
import type { Span as SdkSpan } from '@opentelemetry/sdk-trace-base';
import { HttpInstrumentation } from '@opentelemetry/instrumentation-http';
import { FetchInstrumentation } from '@opentelemetry/instrumentation-fetch';
import {
  context,
  trace,
  propagation,
  Span,
  SpanStatusCode,
  Tracer,
  Context,
} from '@opentelemetry/api';
import {
  W3CTraceContextPropagator,
  W3CBaggagePropagator,
  CompositePropagator,
} from '@opentelemetry/core';

const SERVICE_NAME = 'opennotes-discord';
const SERVICE_VERSION = process.env.SERVICE_VERSION || process.env.npm_package_version || '0.0.1';
const ENVIRONMENT = process.env.NODE_ENV || 'development';

const BAGGAGE_KEYS_TO_PROPAGATE = [
  'discord.user_id',
  'discord.username',
  'discord.guild_id',
  'request_id',
];

class BaggageSpanProcessor implements SpanProcessor {
  onStart(span: SdkSpan, parentContext: Context): void {
    const baggage = propagation.getBaggage(parentContext);
    if (!baggage) return;

    for (const key of BAGGAGE_KEYS_TO_PROPAGATE) {
      const entry = baggage.getEntry(key);
      if (entry) {
        const attrKey = key.replace(/\./g, '_');
        span.setAttribute(attrKey, entry.value);
      }
    }
  }

  onEnd(_span: ReadableSpan): void {}
  shutdown(): Promise<void> {
    return Promise.resolve();
  }
  forceFlush(): Promise<void> {
    return Promise.resolve();
  }
}

let sdk: NodeSDK | null = null;
let isInitialized = false;

export interface TelemetryConfig {
  otlpEndpoint?: string;
  otlpHeaders?: Record<string, string>;
  enableConsoleExport?: boolean;
  enabled?: boolean;
}

function parseOtlpHeaders(headersStr: string | undefined): Record<string, string> {
  if (!headersStr) return {};

  const headers: Record<string, string> = {};
  for (const pair of headersStr.split(',')) {
    const eqIndex = pair.indexOf('=');
    if (eqIndex > 0) {
      const key = pair.slice(0, eqIndex).trim();
      const value = pair.slice(eqIndex + 1).trim();
      if (key && value) {
        headers[key] = value;
      }
    }
  }
  return headers;
}

function ensureTracesPath(endpoint: string): string {
  if (endpoint.endsWith('/v1/traces')) {
    return endpoint;
  }
  return endpoint.replace(/\/$/, '') + '/v1/traces';
}

export function initTelemetry(config?: TelemetryConfig): void {
  if (isInitialized) {
    console.log('[Telemetry] Already initialized, skipping');
    return;
  }

  const enabled = config?.enabled ?? process.env.ENABLE_TRACING === 'true';

  if (!enabled) {
    console.log('[Telemetry] Tracing disabled');
    return;
  }

  const otlpEndpoint = config?.otlpEndpoint || process.env.OTLP_ENDPOINT;
  const otlpHeaders = config?.otlpHeaders || parseOtlpHeaders(process.env.OTLP_HEADERS);
  const enableConsoleExport = config?.enableConsoleExport ?? process.env.ENABLE_CONSOLE_TRACING === 'true';

  const resource = new Resource({
    [ATTR_SERVICE_NAME]: SERVICE_NAME,
    [ATTR_SERVICE_VERSION]: SERVICE_VERSION,
    [SEMRESATTRS_DEPLOYMENT_ENVIRONMENT]: ENVIRONMENT,
  });

  propagation.setGlobalPropagator(
    new CompositePropagator({
      propagators: [
        new W3CTraceContextPropagator(),
        new W3CBaggagePropagator(),
      ],
    })
  );

  const spanProcessors: SpanProcessor[] = [new BaggageSpanProcessor()];
  console.log('[Telemetry] Baggage span processor enabled');

  if (otlpEndpoint) {
    const tracesUrl = ensureTracesPath(otlpEndpoint);
    const exporter = new OTLPTraceExporter({
      url: tracesUrl,
      headers: otlpHeaders,
    });
    spanProcessors.push(new BatchSpanProcessor(exporter));
    console.log(`[Telemetry] OTLP exporter configured: ${tracesUrl}`);
  }

  if (enableConsoleExport) {
    spanProcessors.push(new SimpleSpanProcessor(new ConsoleSpanExporter()));
    console.log('[Telemetry] Console exporter enabled');
  }

  if (spanProcessors.length === 1) {
    console.log('[Telemetry] No exporters configured, tracing will be no-op');
    return;
  }

  sdk = new NodeSDK({
    resource,
    spanProcessors,
    instrumentations: [
      new HttpInstrumentation({
        ignoreIncomingRequestHook: (request) => {
          return request.url === '/health' || request.url === '/metrics';
        },
      }),
      new FetchInstrumentation(),
    ],
  });

  sdk.start();
  isInitialized = true;

  console.log(`[Telemetry] Initialized for ${SERVICE_NAME} v${SERVICE_VERSION} (${ENVIRONMENT})`);
}

export function shutdownTelemetry(): Promise<void> {
  if (sdk) {
    return sdk.shutdown();
  }
  return Promise.resolve();
}

export function getTracer(name: string = SERVICE_NAME): Tracer {
  return trace.getTracer(name);
}

export function getCurrentSpan(): Span | undefined {
  return trace.getActiveSpan();
}

export function getActiveContext(): Context {
  return context.active();
}

export function withSpan<T>(
  tracer: Tracer,
  spanName: string,
  fn: (span: Span) => T | Promise<T>,
  attributes?: Record<string, string | number | boolean>
): Promise<T> {
  return tracer.startActiveSpan(spanName, async (span) => {
    if (attributes) {
      for (const [key, value] of Object.entries(attributes)) {
        span.setAttribute(key, value);
      }
    }
    try {
      const result = await fn(span);
      span.setStatus({ code: SpanStatusCode.OK });
      return result;
    } catch (error) {
      span.setStatus({
        code: SpanStatusCode.ERROR,
        message: error instanceof Error ? error.message : String(error),
      });
      span.recordException(error instanceof Error ? error : new Error(String(error)));
      throw error;
    } finally {
      span.end();
    }
  });
}

export function injectTraceContext(headers: Record<string, string>): Record<string, string> {
  const carrier: Record<string, string> = { ...headers };
  propagation.inject(context.active(), carrier);
  return carrier;
}

export function extractTraceContext(headers: Record<string, string>): Context {
  return propagation.extract(context.active(), headers);
}

export { context, trace, propagation, SpanStatusCode };
