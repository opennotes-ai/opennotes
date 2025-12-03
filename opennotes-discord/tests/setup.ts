// Test environment setup
process.env.REDIS_URL = process.env.REDIS_URL || 'redis://localhost:6379';
process.env.NODE_ENV = 'test';
process.env.DISCORD_TOKEN = process.env.DISCORD_TOKEN || 'testing-discord-token-for-testing';
process.env.DISCORD_CLIENT_ID = process.env.DISCORD_CLIENT_ID || 'testing-client-id-for-testing';
process.env.OPENNOTES_SERVICE_URL = process.env.OPENNOTES_SERVICE_URL || 'http://localhost:8000';
process.env.OPENNOTES_API_KEY = process.env.OPENNOTES_API_KEY || 'testing-api-key-for-tests-12345';
