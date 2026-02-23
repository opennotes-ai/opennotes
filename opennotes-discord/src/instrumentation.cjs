/**
 * Generic OpenTelemetry instrumentation for the Discord bot.
 *
 * This file MUST be loaded via --require before any other imports
 * for automatic instrumentation to work correctly.
 *
 * Usage: node --require ./src/instrumentation.cjs dist/index.js
 *
 * Environment variables:
 * - OTEL_EXPORTER_OTLP_ENDPOINT: OTLP endpoint (default: http://localhost:4317)
 * - OTEL_EXPORTER_OTLP_HEADERS: Auth headers in 'key=value' format
 * - OTEL_SERVICE_NAME: Service name (defaults to 'opennotes-discord')
 * - OTEL_SDK_DISABLED: Set to 'true' to disable OTel (useful for tests)
 * - ENABLE_TRACING: Set to 'true' to enable (defaults to false)
 * - ENABLE_CONSOLE_TRACING: Set to 'true' for console span export
 * - OTEL_METRICS_EXPORTER: Set to 'none' to disable metrics export
 * - OTEL_EXPORTER_OTLP_METRICS_ENDPOINT: Metrics-specific OTLP endpoint (falls back to OTEL_EXPORTER_OTLP_ENDPOINT)
 *
 * Created: task-998
 */

const ENABLE_TRACING = process.env.ENABLE_TRACING === 'true';
const OTEL_SDK_DISABLED = process.env.OTEL_SDK_DISABLED === 'true';
const SERVICE_NAME = process.env.OTEL_SERVICE_NAME || 'opennotes-discord';
const SERVICE_VERSION = process.env.SERVICE_VERSION || process.env.npm_package_version || '0.0.1';
const ENVIRONMENT = process.env.NODE_ENV || 'development';

if (ENABLE_TRACING && !OTEL_SDK_DISABLED) {
  try {
    const { NodeSDK } = require('@opentelemetry/sdk-node');
    const { Resource } = require('@opentelemetry/resources');
    const {
      ATTR_SERVICE_NAME,
      ATTR_SERVICE_VERSION,
      ATTR_DEPLOYMENT_ENVIRONMENT,
    } = require('@opentelemetry/semantic-conventions');
    const { OTLPTraceExporter } = require('@opentelemetry/exporter-trace-otlp-grpc');
    const { OTLPMetricExporter } = require('@opentelemetry/exporter-metrics-otlp-grpc');
    const { PeriodicExportingMetricReader } = require('@opentelemetry/sdk-metrics');
    const { getNodeAutoInstrumentations } = require('@opentelemetry/auto-instrumentations-node');
    const { BatchSpanProcessor, ConsoleSpanExporter } = require('@opentelemetry/sdk-trace-base');
    const { propagation, context: otelContext } = require('@opentelemetry/api');
    const {
      W3CTraceContextPropagator,
      W3CBaggagePropagator,
      CompositePropagator,
    } = require('@opentelemetry/core');

    const BAGGAGE_KEYS_TO_PROPAGATE = [
      'discord.user_id',
      'discord.username',
      'discord.guild_id',
      'request_id',
    ];

    class BaggageSpanProcessor {
      onStart(span, parentContext) {
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

      onEnd() {}
      shutdown() {
        return Promise.resolve();
      }
      forceFlush() {
        return Promise.resolve();
      }
    }

    const resource = new Resource({
      [ATTR_SERVICE_NAME]: SERVICE_NAME,
      [ATTR_SERVICE_VERSION]: SERVICE_VERSION,
      [ATTR_DEPLOYMENT_ENVIRONMENT]: ENVIRONMENT,
    });

    propagation.setGlobalPropagator(
      new CompositePropagator({
        propagators: [new W3CTraceContextPropagator(), new W3CBaggagePropagator()],
      })
    );

    const endpoint =
      process.env.OTEL_EXPORTER_OTLP_ENDPOINT ||
      process.env.OTLP_ENDPOINT ||
      'http://localhost:4317';

    const headersStr = process.env.OTEL_EXPORTER_OTLP_HEADERS || process.env.OTLP_HEADERS;
    const headers = {};
    if (headersStr) {
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
    }

    const traceExporter = new OTLPTraceExporter({
      url: endpoint,
      headers: Object.keys(headers).length > 0 ? headers : undefined,
    });

    const spanProcessors = [new BaggageSpanProcessor(), new BatchSpanProcessor(traceExporter)];

    if (process.env.ENABLE_CONSOLE_TRACING === 'true') {
      spanProcessors.push(new BatchSpanProcessor(new ConsoleSpanExporter()));
      console.log(
        JSON.stringify({
          timestamp: new Date().toISOString(),
          level: 'INFO',
          message: 'Console span exporter enabled',
        })
      );
    }

    const metricsDisabled = process.env.OTEL_METRICS_EXPORTER === 'none';
    const metricReaders = [];

    if (!metricsDisabled) {
      const metricsEndpoint =
        process.env.OTEL_EXPORTER_OTLP_METRICS_ENDPOINT || endpoint;

      const metricExporter = new OTLPMetricExporter({
        url: metricsEndpoint,
        headers: Object.keys(headers).length > 0 ? headers : undefined,
      });

      metricReaders.push(
        new PeriodicExportingMetricReader({
          exporter: metricExporter,
          exportIntervalMillis: 60000,
        })
      );
    }

    const sdk = new NodeSDK({
      resource,
      spanProcessors,
      metricReaders,
      instrumentations: [
        getNodeAutoInstrumentations({
          '@opentelemetry/instrumentation-fs': { enabled: false },
          '@opentelemetry/instrumentation-dns': { enabled: false },
        }),
      ],
    });

    sdk.start();

    console.log(
      JSON.stringify({
        timestamp: new Date().toISOString(),
        level: 'INFO',
        message: `OpenTelemetry initialized: service=${SERVICE_NAME}, version=${SERVICE_VERSION}, env=${ENVIRONMENT}, endpoint=${endpoint}, metrics=${metricsDisabled ? 'disabled' : 'enabled'}`,
      })
    );

    process.on('SIGTERM', () => {
      sdk
        .shutdown()
        .then(() => {
          console.log(
            JSON.stringify({
              timestamp: new Date().toISOString(),
              level: 'INFO',
              message: 'OpenTelemetry SDK shut down gracefully',
            })
          );
        })
        .catch((err) => {
          console.error(
            JSON.stringify({
              timestamp: new Date().toISOString(),
              level: 'ERROR',
              message: 'Error shutting down OpenTelemetry SDK',
              error: err.message,
            })
          );
        });
    });

    module.exports = { sdk };
  } catch (error) {
    console.error(
      JSON.stringify({
        timestamp: new Date().toISOString(),
        level: 'ERROR',
        message: 'Failed to initialize OpenTelemetry',
        error: error.message,
      })
    );
    module.exports = { sdk: null };
  }
} else {
  if (OTEL_SDK_DISABLED) {
    console.log(
      JSON.stringify({
        timestamp: new Date().toISOString(),
        level: 'INFO',
        message: 'OpenTelemetry SDK disabled via OTEL_SDK_DISABLED=true',
      })
    );
  } else if (!ENABLE_TRACING) {
    console.log(
      JSON.stringify({
        timestamp: new Date().toISOString(),
        level: 'INFO',
        message: 'OpenTelemetry disabled (ENABLE_TRACING != true)',
      })
    );
  }
  module.exports = { sdk: null };
}
