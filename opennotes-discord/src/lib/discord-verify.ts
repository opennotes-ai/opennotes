export interface VerifyResult {
  valid: boolean;
  error?: string;
}

export async function verifyDiscordRequest(
  request: Request,
  publicKey: string
): Promise<VerifyResult> {
  const signature = request.headers.get('x-signature-ed25519');
  const timestamp = request.headers.get('x-signature-timestamp');

  if (!signature || !timestamp) {
    return {
      valid: false,
      error: 'Missing signature headers'
    };
  }

  try {
    const body = await request.clone().text();
    const isValid = await verifyKey(body, signature, timestamp, publicKey);

    return {
      valid: isValid,
      error: isValid ? undefined : 'Invalid signature'
    };
  } catch (error) {
    return {
      valid: false,
      error: `Verification failed: ${error instanceof Error ? error.message : 'Unknown error'}`
    };
  }
}

async function verifyKey(
  body: string,
  signature: string,
  timestamp: string,
  publicKey: string
): Promise<boolean> {
  try {
    const timestampData = new TextEncoder().encode(timestamp);
    const bodyData = new TextEncoder().encode(body);

    const message = new Uint8Array(timestampData.length + bodyData.length);
    message.set(timestampData);
    message.set(bodyData, timestampData.length);

    const signatureData = hexToUint8Array(signature);
    const publicKeyData = hexToUint8Array(publicKey);

    const cryptoKey = await crypto.subtle.importKey(
      'raw',
      publicKeyData,
      {
        name: 'Ed25519',
        namedCurve: 'Ed25519'
      },
      false,
      ['verify']
    );

    return await crypto.subtle.verify(
      'Ed25519',
      cryptoKey,
      signatureData,
      message
    );
  } catch (error) {
    return false;
  }
}

function hexToUint8Array(hex: string): Uint8Array {
  const matches = hex.match(/.{1,2}/g);
  if (!matches) {
    throw new Error('Invalid hex string');
  }
  return new Uint8Array(matches.map(byte => parseInt(byte, 16)));
}
