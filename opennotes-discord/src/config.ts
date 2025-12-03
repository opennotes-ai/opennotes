import dotenv from 'dotenv';

dotenv.config();

interface Config {
  discordToken: string;
  clientId: string;
  serverUrl: string;
  apiKey?: string;
  internalServiceSecret?: string;
  jwtSecretKey?: string;
  environment: 'development' | 'production';
  logLevel: 'debug' | 'info' | 'warn' | 'error';
  autoMonitorChannels: boolean;
  notifyMissingOpenAIKey: boolean;
  useRedisRateLimiting: boolean;
  instanceId: string;
  similaritySearchDefaultThreshold: number;
  sharding: {
    enabled: boolean;
    totalShards: number | 'auto';
    shardList?: number[];
    respawn: boolean;
  };
  healthCheck: {
    enabled: boolean;
    port: number;
  };
}

function getEnvVar(key: string, defaultValue?: string): string {
  const value = process.env[key] || defaultValue;
  if (!value) {
    throw new Error(`Missing required environment variable: ${key}`);
  }
  return value;
}

function validateApiKey(key: string | undefined, environment: string): string | undefined {
  if (environment === 'test') {
    return key?.trim();
  }

  if (!key) {
    if (environment === 'production') {
      throw new Error('OPENNOTES_API_KEY is required in production');
    }
    console.warn('Warning: OPENNOTES_API_KEY is not set. API requests may fail.');
    return undefined;
  }

  const trimmed = key.trim();

  const exactPlaceholders = ['your_api_key_here', 'changeme', 'placeholder', 'test_key', 'example_key'];
  if (exactPlaceholders.some(p => trimmed.toLowerCase() === p)) {
    throw new Error('Invalid API key: appears to be a placeholder value');
  }

  if (trimmed.length < 16) {
    throw new Error('Invalid API key: too short (minimum 16 characters)');
  }

  return trimmed;
}

function validateSecuritySecret(
  key: string | undefined,
  envVarName: string,
  environment: string
): string | undefined {
  if (environment === 'test') {
    return key?.trim();
  }

  if (!key) {
    if (environment === 'production') {
      throw new Error(`${envVarName} is required in production`);
    }
    console.warn(`Warning: ${envVarName} is not set. Security headers will not be sent.`);
    return undefined;
  }

  const trimmed = key.trim();

  const exactPlaceholders = ['your_secret_here', 'changeme', 'placeholder', 'test_secret', 'example_secret'];
  if (exactPlaceholders.some(p => trimmed.toLowerCase() === p)) {
    throw new Error(`Invalid ${envVarName}: appears to be a placeholder value`);
  }

  if (trimmed.length < 32) {
    if (environment === 'production') {
      throw new Error(`Invalid ${envVarName}: too short (minimum 32 characters in production)`);
    }
    console.warn(`Warning: ${envVarName} is shorter than 32 characters. This is not recommended.`);
  }

  return trimmed;
}

const environment = getEnvVar('NODE_ENV', 'development') as 'development' | 'production';

function parseShardConfig(): { totalShards: number | 'auto'; shardList?: number[] } {
  const totalShardsEnv = getEnvVar('DISCORD_TOTAL_SHARDS', 'auto');
  const totalShards = totalShardsEnv === 'auto' ? 'auto' : parseInt(totalShardsEnv, 10);

  const shardListEnv = process.env.DISCORD_SHARD_LIST;
  let shardList: number[] | undefined;

  if (shardListEnv) {
    shardList = shardListEnv.split(',').map(s => parseInt(s.trim(), 10));
    if (shardList.some(isNaN)) {
      throw new Error('Invalid DISCORD_SHARD_LIST: must be comma-separated numbers');
    }
  }

  return { totalShards, shardList };
}

export const config: Config = {
  discordToken: getEnvVar('DISCORD_TOKEN'),
  clientId: getEnvVar('DISCORD_CLIENT_ID'),
  serverUrl: getEnvVar('OPENNOTES_SERVICE_URL', 'http://localhost:8000'),
  apiKey: validateApiKey(process.env.OPENNOTES_API_KEY, environment),
  internalServiceSecret: validateSecuritySecret(
    process.env.INTERNAL_SERVICE_SECRET,
    'INTERNAL_SERVICE_SECRET',
    environment
  ),
  jwtSecretKey: validateSecuritySecret(
    process.env.JWT_SECRET_KEY,
    'JWT_SECRET_KEY',
    environment
  ),
  environment,
  logLevel: (getEnvVar('LOG_LEVEL', 'info') as 'debug' | 'info' | 'warn' | 'error'),
  autoMonitorChannels: getEnvVar('AUTO_MONITOR_CHANNELS', 'true').toLowerCase() === 'true',
  notifyMissingOpenAIKey: getEnvVar('NOTIFY_MISSING_OPENAI_KEY', 'true').toLowerCase() === 'true',
  useRedisRateLimiting: getEnvVar('USE_REDIS_RATE_LIMITING', 'false').toLowerCase() === 'true',
  instanceId: getEnvVar('INSTANCE_ID', `${process.env.HOSTNAME || 'unknown'}-${process.pid}`),
  similaritySearchDefaultThreshold: parseFloat(getEnvVar('SIMILARITY_SEARCH_DEFAULT_THRESHOLD', '0.6')),
  sharding: {
    enabled: getEnvVar('DISCORD_SHARDING_ENABLED', 'true').toLowerCase() === 'true',
    ...parseShardConfig(),
    respawn: getEnvVar('DISCORD_SHARD_RESPAWN', 'true').toLowerCase() === 'true',
  },
  healthCheck: {
    enabled: getEnvVar('HEALTH_CHECK_ENABLED', 'true').toLowerCase() === 'true',
    port: parseInt(getEnvVar('HEALTH_CHECK_PORT', '3000'), 10),
  },
};
