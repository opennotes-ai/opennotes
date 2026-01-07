/**
 * Middleware.io APM instrumentation for the Discord bot.
 *
 * This file MUST be loaded via --require before any other imports
 * for automatic instrumentation to work correctly.
 *
 * Usage: node --require ./instrumentation.cjs dist/index.js
 *
 * Environment variables:
 * - MW_API_KEY: Middleware.io API key (required)
 * - MW_TARGET: Middleware.io endpoint URL (required for serverless/Cloud Run)
 * - MW_SERVICE_NAME: Service name (defaults to 'opennotes-discord')
 * - MW_SAMPLE_RATE: Trace sampling rate 0-100 (defaults to 100)
 * - MIDDLEWARE_APM_ENABLED: Set to 'true' to enable (defaults to false)
 *
 * Reference: https://docs.middleware.io/apm-configuration/node-js
 */

const MW_API_KEY = process.env.MW_API_KEY;
const MW_TARGET = process.env.MW_TARGET;
const MW_SERVICE_NAME = process.env.MW_SERVICE_NAME || 'opennotes-discord';
const MIDDLEWARE_APM_ENABLED = process.env.MIDDLEWARE_APM_ENABLED === 'true';

if (MIDDLEWARE_APM_ENABLED && MW_API_KEY && MW_TARGET) {
  try {
    const tracker = require('@middleware.io/node-apm');

    tracker.track({
      serviceName: MW_SERVICE_NAME,
      accessToken: MW_API_KEY,
      target: MW_TARGET,
      enableProfiling: true,
      customResourceAttributes: {
        'deployment.environment': process.env.NODE_ENV || 'development',
        'service.version': process.env.SERVICE_VERSION || process.env.npm_package_version || '0.0.1',
      },
    });

    console.log(
      JSON.stringify({
        timestamp: new Date().toISOString(),
        level: 'INFO',
        message: `Middleware.io APM initialized: service=${MW_SERVICE_NAME}, target=${MW_TARGET}`,
      })
    );

    module.exports = { tracker };
  } catch (error) {
    console.error(
      JSON.stringify({
        timestamp: new Date().toISOString(),
        level: 'ERROR',
        message: 'Failed to initialize Middleware.io APM',
        error: error.message,
      })
    );
    module.exports = { tracker: null };
  }
} else {
  if (!MIDDLEWARE_APM_ENABLED) {
    console.log(
      JSON.stringify({
        timestamp: new Date().toISOString(),
        level: 'INFO',
        message: 'Middleware.io APM disabled (MIDDLEWARE_APM_ENABLED != true)',
      })
    );
  } else if (!MW_API_KEY || !MW_TARGET) {
    console.log(
      JSON.stringify({
        timestamp: new Date().toISOString(),
        level: 'WARN',
        message: 'Middleware.io APM enabled but missing MW_API_KEY or MW_TARGET',
      })
    );
  }
  module.exports = { tracker: null };
}
