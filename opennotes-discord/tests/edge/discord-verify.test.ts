import { describe, it, expect } from '@jest/globals';
import { verifyDiscordRequest } from '../../src/lib/discord-verify';

describe('Discord Signature Verification', () => {
  it('should fail verification with missing signature headers', async () => {
    const request = new Request('http://localhost/test', {
      method: 'POST',
      body: JSON.stringify({ test: 'data' }),
    });

    const result = await verifyDiscordRequest(request, 'test_key');

    expect(result.valid).toBe(false);
    expect(result.error).toContain('Missing signature headers');
  });

  it('should fail verification with invalid signature', async () => {
    const request = new Request('http://localhost/test', {
      method: 'POST',
      headers: {
        'x-signature-ed25519': 'invalid_signature',
        'x-signature-timestamp': '1234567890',
      },
      body: JSON.stringify({ test: 'data' }),
    });

    const result = await verifyDiscordRequest(request, 'test_public_key');

    expect(result.valid).toBe(false);
  });

  it('should return error message on verification failure', async () => {
    const request = new Request('http://localhost/test', {
      method: 'POST',
      headers: {
        'x-signature-ed25519': 'abc123',
        'x-signature-timestamp': '1234567890',
      },
      body: JSON.stringify({ test: 'data' }),
    });

    const result = await verifyDiscordRequest(request, 'invalid_key');

    expect(result.valid).toBe(false);
    expect(result.error).toBeDefined();
  });
});
