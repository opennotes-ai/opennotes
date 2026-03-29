import jwt from 'jsonwebtoken';
import { config } from '../config.js';
import { logger } from '../logger.js';

const PLATFORM_CLAIMS_EXPIRY_SECONDS = 300;
const JWT_ALGORITHM = 'HS256';

export interface PlatformClaims {
  platform: string;
  scope: string;
  sub: string;
  community_id: string;
  can_administer_community: boolean;
  type: 'platform_claims';
  iat: number;
  exp: number;
}

export function createPlatformClaimsToken(
  platform: string,
  scope: string,
  userId: string,
  communityId: string,
  canAdministerCommunity: boolean
): string | null {
  if (!config.jwtSecretKey) {
    logger.warn('JWT_SECRET_KEY not configured, cannot create platform claims token');
    return null;
  }

  const now = Math.floor(Date.now() / 1000);
  const exp = now + PLATFORM_CLAIMS_EXPIRY_SECONDS;

  const payload: PlatformClaims = {
    platform,
    scope,
    sub: userId,
    community_id: communityId,
    can_administer_community: canAdministerCommunity,
    type: 'platform_claims',
    iat: now,
    exp: exp,
  };

  return jwt.sign(payload, config.jwtSecretKey, {
    algorithm: JWT_ALGORITHM,
  });
}
