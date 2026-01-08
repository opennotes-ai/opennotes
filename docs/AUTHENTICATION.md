# Open Notes Authentication Architecture

## Overview

Open Notes uses a flexible dual-authentication system that supports both JWT tokens (for user authentication) and API keys (for service-to-service authentication).

## Authentication Methods

### 1. JWT Tokens (User Authentication)

Used for web clients and user-facing applications.

**Flow:**
1. User logs in with username/password → `/api/v1/auth/login`
2. Server returns access token (30min) and refresh token (7 days)
3. Client includes token in `Authorization: Bearer {token}` header
4. Server verifies JWT signature and extracts user info

**Endpoints:**
- `POST /api/v1/auth/register` - Create new user account
- `POST /api/v1/auth/login` - Login and receive tokens
- `POST /api/v1/auth/refresh` - Refresh access token
- `POST /api/v1/auth/logout` - Revoke refresh token
- `POST /api/v1/auth/logout-all` - Revoke all user's refresh tokens

**Configuration:**
```yaml
JWT_SECRET_KEY: your-secret-key-here  # openssl rand -hex 32
JWT_ALGORITHM: HS256
ACCESS_TOKEN_EXPIRE_MINUTES: 30
REFRESH_TOKEN_EXPIRE_DAYS: 7
```

### 2. API Keys (Service Authentication)

Used for service-to-service communication (e.g., Discord bot → API server).

**Benefits:**
- No shared secrets between services
- Long-lived credentials (up to 1 year)
- Easy rotation without downtime
- Scoped to specific users/services

**Flow:**
1. Service account created via `/api/v1/auth/register`
2. API key generated via `/api/v1/users/me/api-keys`
3. Service includes key in `Authorization: Bearer {api_key}` header
4. Server verifies API key hash and returns associated user

**Endpoints:**
- `POST /api/v1/users/me/api-keys` - Create API key
- `GET /api/v1/users/me/api-keys` - List user's API keys
- `DELETE /api/v1/users/me/api-keys/{id}` - Revoke API key

## Server Implementation

### Authentication Dependency

The server provides three authentication dependencies:

```python
# JWT only (strict user authentication)
get_current_active_user

# JWT or API key (flexible authentication)
get_current_user_or_api_key  # ← Used by most endpoints

# Role-based access control
require_role("admin")
require_superuser
```

### Endpoint Protection

Most API endpoints use `get_current_user_or_api_key`, which accepts both authentication methods:

```python
@router.post("/api/v1/notes")
async def create_note(
    note_create: NoteCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],  # Flexible
) -> NoteResponse:
    ...
```

This allows:
- Web users to authenticate with JWT tokens
- Services (like Discord bot) to authenticate with API keys
- Same endpoint serves both use cases

## Discord Bot Authentication

### Current Setup

The Discord bot uses API key authentication:

```typescript
// src/config.ts
export const config: Config = {
  serverUrl: getEnvVar('OPENNOTES_SERVICE_URL', 'http://localhost:8000'),
  apiKey: process.env.OPENNOTES_API_KEY,  // Service API key
  // No JWT_SECRET - bot doesn't generate tokens!
};

// src/lib/api-client.ts
if (this.apiKey) {
  headers['Authorization'] = `Bearer ${this.apiKey}`;
}
```

### Service Account

**User**: `discord-bot-svc`
**API Key**: Configured in `OPENNOTES_API_KEY` environment variable
**Expires**: 2026-10-23 (1 year from creation)

**Environment Configuration:**
```yaml
# opennotes/.env.yaml
OPENNOTES_API_KEY: XcvlCe7ewY4z4VzbWeogvkJZA-5hxY_xJn5PJmZJN0c
```

## API Key Rotation Procedure

### When to Rotate

- Scheduled rotation (recommended: every 6-12 months)
- Security incident or suspected compromise
- Service upgrade or migration
- Employee offboarding (if they had access)

### Rotation Steps

#### 1. Generate New API Key

```bash
# Login as service user (or use existing access token)
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=discord-bot-svc&password=SERVICE_PASSWORD"

# Create new API key
curl -X POST http://localhost:8000/api/v1/users/me/api-keys \
  -H "Authorization: Bearer ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "discord-bot-2026",
    "expires_in_days": 365
  }'

# Response includes the new API key (only shown once!)
{
  "id": 123,
  "name": "discord-bot-2026",
  "key": "NEW_API_KEY_HERE",
  "created_at": "2025-10-24T...",
  "expires_at": "2026-10-24T..."
}
```

#### 2. Update Environment Configuration

```bash
# Update .env.yaml
cd /Users/mike/code/opennotes-ai/multiverse/opennotes
# Edit .env.yaml and update OPENNOTES_API_KEY with new key

# For Docker deployments
docker compose restart opennotes-discord

# For Kubernetes deployments
kubectl create secret generic discord-bot-api-key \
  --from-literal=OPENNOTES_API_KEY=NEW_API_KEY_HERE \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl rollout restart deployment/opennotes-discord
```

#### 3. Verify New Key Works

```bash
# Test API call with new key
curl -X GET http://localhost:8000/health \
  -H "Authorization: Bearer NEW_API_KEY_HERE"

# Check Discord bot logs
docker compose logs -f opennotes-discord

# Verify bot commands work in Discord
/status  # Should return server status
```

#### 4. Revoke Old API Key

```bash
# List API keys to find old key ID
curl -X GET http://localhost:8000/api/v1/users/me/api-keys \
  -H "Authorization: Bearer NEW_API_KEY_HERE"

# Revoke old key
curl -X DELETE http://localhost:8000/api/v1/users/me/api-keys/OLD_KEY_ID \
  -H "Authorization: Bearer NEW_API_KEY_HERE"
```

#### 5. Update Documentation

Update this file and `.env.yaml` comments with:
- New expiration date
- Rotation date
- Any changes to the procedure

### Emergency Rotation

If API key is compromised:

```bash
# 1. Immediately revoke compromised key
curl -X DELETE http://localhost:8000/api/v1/users/me/api-keys/COMPROMISED_KEY_ID \
  -H "Authorization: Bearer ACCESS_TOKEN"

# 2. Generate and deploy new key (Steps 1-3 above)
# Bot will be offline briefly during rotation

# 3. Review API access logs
docker compose logs opennotes-server | grep "discord-bot-svc"

# 4. Check for unauthorized access
# Review recent API calls, note creations, rating submissions
```

## Security Best Practices

### For Production

1. **Rotate keys regularly** (every 6-12 months)
2. **Use expiration dates** (365 days recommended)
3. **Secure storage**: Use secrets management (Kubernetes secrets, AWS Secrets Manager)
4. **Monitoring**: Track API key usage via NATS events (subject: `events.api_key.used`)
5. **Least privilege**: Create separate keys for each service
6. **Audit logging**: Review API access logs regularly

### Key Management

```bash
# List all API keys for audit
mise run api-keys:list

# Check API key expiration dates
mise run api-keys:check-expiry

# Automated rotation (future enhancement)
mise run api-keys:rotate --service discord-bot
```

## Troubleshooting

### "401 Unauthorized" Errors

```bash
# Check API key is set
echo $OPENNOTES_API_KEY

# Verify key is valid
curl -X GET http://localhost:8000/api/v1/users/me \
  -H "Authorization: Bearer $OPENNOTES_API_KEY"

# Check API key status in database
docker exec -it opennotes-postgres psql -U opennotes -d opennotes \
  -c "SELECT id, name, is_active, expires_at FROM api_keys WHERE user_id = (SELECT id FROM users WHERE username = 'discord-bot-svc');"
```

### "Invalid authentication credentials"

Possible causes:
- API key expired (check `expires_at` field)
- API key revoked (check `is_active` field)
- Wrong API key format (should be 32+ character string)
- Service user account disabled

## Migration Notes

**Historical Note**: This task (task-115) investigated migrating from JWT to API key authentication. Investigation revealed the Discord bot was ALREADY using API keys since its creation and never generated JWTs. No migration was necessary.

## References

- FastAPI Security: https://fastapi.tiangolo.com/tutorial/security/
- API Key Best Practices: https://cloud.google.com/docs/authentication/api-keys
- JWT Specification: https://datatracker.ietf.org/doc/html/rfc7519
