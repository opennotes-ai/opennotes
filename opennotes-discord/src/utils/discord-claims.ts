import jwt from 'jsonwebtoken';
import { config } from '../config.js';
import { logger } from '../logger.js';

const DISCORD_CLAIMS_EXPIRY_SECONDS = 300;
// CRITICAL: Must match server's JWT_ALGORITHM setting (default: HS256)
const JWT_ALGORITHM = 'HS256';

export interface DiscordClaims {
  sub: string;
  user_id: string;
  guild_id: string;
  has_manage_server: boolean;
  iat: number;
  exp: number;
  type: 'discord_claims';
}

/**
 * Create a signed JWT containing Discord claims for secure server communication.
 *
 * This token should be passed to the server in the X-Discord-Claims header.
 * The server validates the signature before trusting the claims.
 *
 * @param userId - Discord user ID (snowflake)
 * @param guildId - Discord guild ID (snowflake)
 * @param hasManageServer - Whether user has Manage Server permission
 * @returns Signed JWT token string, or null if JWT_SECRET_KEY not configured
 */
export function createDiscordClaimsToken(
  userId: string,
  guildId: string,
  hasManageServer: boolean
): string | null {
  if (!config.jwtSecretKey) {
    logger.warn('JWT_SECRET_KEY not configured, cannot create Discord claims token');
    return null;
  }

  const now = Math.floor(Date.now() / 1000);
  const exp = now + DISCORD_CLAIMS_EXPIRY_SECONDS;

  const payload: DiscordClaims = {
    sub: userId,
    user_id: userId,
    guild_id: guildId,
    has_manage_server: hasManageServer,
    iat: now,
    exp: exp,
    type: 'discord_claims',
  };

  return jwt.sign(payload, config.jwtSecretKey, {
    algorithm: JWT_ALGORITHM,
  });
}
