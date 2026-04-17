#!/usr/bin/env python3
"""
Seed API keys into the database for Discord bot and playground authentication.

This script ensures that the API keys used by the Discord bot and playground
service exist in the database. It's idempotent and safe to run multiple times.

Usage:
    # Development/Local (uses hardcoded dev keys):
    python scripts/seed_api_keys.py

    # Production (generates new keys or uses provided keys):
    ENVIRONMENT=production python scripts/seed_api_keys.py

    # Production with specific key values:
    ENVIRONMENT=production OPENNOTES_API_KEY=opk_xxx_yyy PLAYGROUND_API_KEY=opk_xxx_yyy python scripts/seed_api_keys.py

    Or via mise:
    mise run db:seed-api-keys
"""

import asyncio
import json
import os
import secrets
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.password import get_password_hash
from src.database import get_engine

DEV_API_KEY = "XcvlCe7ewY4z4VzbWeogvkJZA-5hxY_xJn5PJmZJN0c"
DEV_API_KEY_NAME = "Discord Bot (Development)"
PROD_API_KEY_NAME = "Discord Bot (Production)"
SERVICE_USER_USERNAME = "discord-bot-service"
SERVICE_USER_EMAIL = "discord-bot@opennotes.local"
DISCORD_BOT_SCOPES = ["platform:adapter"]

PLAYGROUND_DEV_API_KEY = "opk_playground_dev_readonly_access_key_2024"
PLAYGROUND_API_KEY_NAME = "Playground (Development)"
PROD_PLAYGROUND_API_KEY_NAME = "Playground (Production)"
PLAYGROUND_SERVICE_USER_USERNAME = "playground-service"
PLAYGROUND_SERVICE_USER_EMAIL = "playground@opennotes.local"
PLAYGROUND_SCOPES = ["simulations:read"]

PLATFORM_DEV_API_KEY = "opk_platform_dev_api_keys_create_2026"
PLATFORM_API_KEY_NAME = "Platform (Development)"
PROD_PLATFORM_API_KEY_NAME = "Platform (Production)"
PLATFORM_SERVICE_USER_USERNAME = "platform-service"
PLATFORM_SERVICE_USER_EMAIL = "platform@opennotes.local"
PLATFORM_SCOPES = ["api-keys:create"]


def generate_api_key() -> tuple[str, str]:
    """Generate a new API key in the format: opk_<prefix>_<secret>"""
    prefix = secrets.token_hex(6)
    secret = secrets.token_urlsafe(32)
    full_key = f"opk_{prefix}_{secret}"
    return full_key, prefix


async def get_or_create_service_user(db: AsyncSession):
    result = await db.execute(
        text(
            "SELECT id, username, principal_type, platform_roles FROM users WHERE username = :username"
        ),
        {"username": SERVICE_USER_USERNAME},
    )
    row = result.first()

    if row:
        user_id = row[0]
        principal_type = row[2]
        platform_roles = row[3] or []

        updates = []
        if principal_type != "system":
            updates.append("principal_type='system'")
            await db.execute(
                text("UPDATE users SET principal_type = 'system' WHERE id = :user_id"),
                {"user_id": user_id},
            )
        if "platform_admin" not in platform_roles:
            updates.append("platform_roles+=platform_admin")
            await db.execute(
                text(
                    "UPDATE users SET platform_roles = '[\"platform_admin\"]'::json WHERE id = :user_id"
                ),
                {"user_id": user_id},
            )

        suffix = f" - patched {', '.join(updates)}" if updates else ""
        print(f"✓ Service user '{SERVICE_USER_USERNAME}' already exists (ID: {user_id}){suffix}")
        return user_id

    hashed_password = get_password_hash(secrets.token_urlsafe(64))

    result = await db.execute(
        text("""
            INSERT INTO users (username, email, hashed_password, full_name, is_active, principal_type, platform_roles, created_at, updated_at)
            VALUES (:username, :email, :hashed_password, :full_name, :is_active, :principal_type, '["platform_admin"]'::json, NOW(), NOW())
            RETURNING id
        """),
        {
            "username": SERVICE_USER_USERNAME,
            "email": SERVICE_USER_EMAIL,
            "hashed_password": hashed_password,
            "full_name": "Discord Bot Service Account",
            "is_active": True,
            "principal_type": "system",
        },
    )
    user_id = result.scalar_one()

    print(f"✓ Created service user '{SERVICE_USER_USERNAME}' (ID: {user_id})")
    return user_id


async def seed_api_key(
    db: AsyncSession,
    key_hash: str,
    key_name: str,
    key_prefix: str | None = None,
    user_id: UUID | None = None,
    scopes: list[str] | None = None,
) -> None:
    if user_id is None:
        user_id = await get_or_create_service_user(db)

    scopes_json = json.dumps(scopes) if scopes is not None else None

    result = await db.execute(
        text(
            "SELECT id, is_active, scopes::text FROM api_keys WHERE user_id = :user_id AND name = :name"
        ),
        {"user_id": user_id, "name": key_name},
    )
    row = result.first()

    if row:
        api_key_id, is_active, existing_scopes_text = row
        existing_scopes = json.loads(existing_scopes_text) if existing_scopes_text else None
        needs_scope_update = existing_scopes != scopes

        if is_active and not needs_scope_update:
            print(f"✓ API key '{key_name}' already exists and is active")
        elif is_active and needs_scope_update:
            await db.execute(
                text("UPDATE api_keys SET scopes = CAST(:scopes AS jsonb) WHERE id = :id"),
                {"id": api_key_id, "scopes": scopes_json},
            )
            print(f"✓ Updated scopes on API key '{key_name}'")
        else:
            await db.execute(
                text(
                    "UPDATE api_keys SET is_active = true, key_hash = :key_hash, key_prefix = :key_prefix, scopes = CAST(:scopes AS jsonb) WHERE id = :id"
                ),
                {
                    "id": api_key_id,
                    "key_hash": key_hash,
                    "key_prefix": key_prefix,
                    "scopes": scopes_json,
                },
            )
            print(f"✓ Reactivated API key '{key_name}'")
        return

    result = await db.execute(
        text("""
            INSERT INTO api_keys (user_id, name, key_hash, key_prefix, is_active, scopes, created_at)
            VALUES (:user_id, :name, :key_hash, :key_prefix, :is_active, CAST(:scopes AS jsonb), NOW())
            RETURNING id
        """),
        {
            "user_id": user_id,
            "name": key_name,
            "key_hash": key_hash,
            "key_prefix": key_prefix,
            "is_active": True,
            "scopes": scopes_json,
        },
    )
    api_key_id = result.scalar_one()

    print(f"✓ Created API key '{key_name}' (ID: {api_key_id})")
    print(f"  User ID: {user_id}")
    print("  Never expires: True")
    if scopes:
        print(f"  Scopes: {scopes}")


async def get_or_create_playground_user(db: AsyncSession):
    result = await db.execute(
        text("SELECT id, username, principal_type FROM users WHERE username = :username"),
        {"username": PLAYGROUND_SERVICE_USER_USERNAME},
    )
    row = result.first()

    if row:
        user_id = row[0]
        principal_type = row[2]

        if principal_type != "agent":
            await db.execute(
                text("UPDATE users SET principal_type = 'agent' WHERE id = :user_id"),
                {"user_id": user_id},
            )
            print(
                f"✓ Playground user '{PLAYGROUND_SERVICE_USER_USERNAME}' already exists (ID: {user_id}) - updated principal_type to agent"
            )
        else:
            print(
                f"✓ Playground user '{PLAYGROUND_SERVICE_USER_USERNAME}' already exists (ID: {user_id})"
            )
        return user_id

    hashed_password = get_password_hash(secrets.token_urlsafe(64))

    result = await db.execute(
        text("""
            INSERT INTO users (username, email, hashed_password, full_name, is_active, principal_type, platform_roles, created_at, updated_at)
            VALUES (:username, :email, :hashed_password, :full_name, :is_active, :principal_type, '[]'::json, NOW(), NOW())
            RETURNING id
        """),
        {
            "username": PLAYGROUND_SERVICE_USER_USERNAME,
            "email": PLAYGROUND_SERVICE_USER_EMAIL,
            "hashed_password": hashed_password,
            "full_name": "Playground User",
            "is_active": True,
            "principal_type": "agent",
        },
    )
    user_id = result.scalar_one()

    print(f"✓ Created playground user '{PLAYGROUND_SERVICE_USER_USERNAME}' (ID: {user_id})")
    return user_id


async def get_or_create_platform_user(db: AsyncSession):
    result = await db.execute(
        text("SELECT id, username, principal_type FROM users WHERE username = :username"),
        {"username": PLATFORM_SERVICE_USER_USERNAME},
    )
    row = result.first()

    if row:
        user_id = row[0]
        principal_type = row[2]

        if principal_type != "system":
            await db.execute(
                text("UPDATE users SET principal_type = 'system' WHERE id = :user_id"),
                {"user_id": user_id},
            )
            print(
                f"✓ Platform user '{PLATFORM_SERVICE_USER_USERNAME}' already exists (ID: {user_id}) - updated principal_type to system"
            )
        else:
            print(
                f"✓ Platform user '{PLATFORM_SERVICE_USER_USERNAME}' already exists (ID: {user_id})"
            )
        return user_id

    hashed_password = get_password_hash(secrets.token_urlsafe(64))

    result = await db.execute(
        text("""
            INSERT INTO users (username, email, hashed_password, full_name, is_active, principal_type, platform_roles, created_at, updated_at)
            VALUES (:username, :email, :hashed_password, :full_name, :is_active, :principal_type, '["platform_admin"]'::json, NOW(), NOW())
            RETURNING id
        """),
        {
            "username": PLATFORM_SERVICE_USER_USERNAME,
            "email": PLATFORM_SERVICE_USER_EMAIL,
            "hashed_password": hashed_password,
            "full_name": "Platform Service Account",
            "is_active": True,
            "principal_type": "system",
        },
    )
    user_id = result.scalar_one()
    print(f"✓ Created platform user '{PLATFORM_SERVICE_USER_USERNAME}' (ID: {user_id})")
    return user_id


async def seed_playground_api_key(db: AsyncSession) -> None:
    user_id = await get_or_create_playground_user(db)
    key_hash = get_password_hash(PLAYGROUND_DEV_API_KEY)
    await seed_api_key(
        db,
        key_hash,
        PLAYGROUND_API_KEY_NAME,
        key_prefix="playground",
        user_id=user_id,
        scopes=PLAYGROUND_SCOPES,
    )


async def seed_platform_api_key(db: AsyncSession) -> None:
    user_id = await get_or_create_platform_user(db)
    key_hash = get_password_hash(PLATFORM_DEV_API_KEY)
    await seed_api_key(
        db,
        key_hash,
        PLATFORM_API_KEY_NAME,
        key_prefix="platform",
        user_id=user_id,
        scopes=PLATFORM_SCOPES,
    )


async def seed_dev_api_key(db: AsyncSession) -> None:
    key_hash = get_password_hash(DEV_API_KEY)
    await seed_api_key(db, key_hash, DEV_API_KEY_NAME, scopes=DISCORD_BOT_SCOPES)


def _resolve_provided_key(env_var: str) -> tuple[str, str | None] | None:
    provided_key = os.environ.get(env_var, "")
    if not provided_key or provided_key.startswith("CHANGE_THIS"):
        return None
    key_prefix: str | None = None
    if provided_key.startswith("opk_"):
        parts = provided_key.split("_", 2)
        if len(parts) == 3:
            key_prefix = parts[1]
    return provided_key, key_prefix


def _push_plaintext_to_gsm(secret_id: str, plaintext: str) -> None:
    """Push a minted plaintext API key to Google Secret Manager.

    Writes a new version on the pre-existing secret shell `secret_id` in the
    configured GCP project. Operators must have created the shell via infra
    apply; this function does not create secrets from scratch on purpose so the
    seed job stays narrowly scoped to roles/secretmanager.secretVersionAdder.

    The plaintext is never logged and never returned.
    """
    from google.api_core import exceptions as gax_exceptions
    from google.cloud import secretmanager

    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT_ID")
    if not project_id:
        raise RuntimeError(
            "GOOGLE_CLOUD_PROJECT (or GCP_PROJECT_ID) must be set to push seeded API keys "
            "to Google Secret Manager."
        )

    client = secretmanager.SecretManagerServiceClient()
    parent = f"projects/{project_id}/secrets/{secret_id}"

    try:
        client.add_secret_version(
            parent=parent,
            payload={"data": plaintext.encode("utf-8")},
        )
    except gax_exceptions.NotFound as exc:
        raise RuntimeError(
            f"Secret shell '{secret_id}' does not exist in project '{project_id}'. "
            "Run the infrastructure apply first to create the secret shell "
            "(tofu apply on the opennotes-server secrets module), then re-run seeding."
        ) from exc

    print(f"✓ Pushed new version of secret '{secret_id}' to Google Secret Manager")


async def _seed_and_save_prod_key(db: AsyncSession) -> None:
    override = _resolve_provided_key("OPENNOTES_API_KEY")
    pushed_from_override = override is not None
    if override is not None:
        api_key, key_prefix = override
    else:
        api_key, key_prefix = generate_api_key()

    key_hash = get_password_hash(api_key)
    await seed_api_key(db, key_hash, PROD_API_KEY_NAME, key_prefix, scopes=DISCORD_BOT_SCOPES)

    if not pushed_from_override:
        _push_plaintext_to_gsm("opennotes-api-key", api_key)


async def _seed_and_save_prod_playground_key(db: AsyncSession) -> None:
    override = _resolve_provided_key("PLAYGROUND_API_KEY")
    pushed_from_override = override is not None
    if override is not None:
        api_key, key_prefix = override
    else:
        api_key, key_prefix = generate_api_key()

    user_id = await get_or_create_playground_user(db)
    key_hash = get_password_hash(api_key)
    await seed_api_key(
        db,
        key_hash,
        PROD_PLAYGROUND_API_KEY_NAME,
        key_prefix,
        user_id=user_id,
        scopes=PLAYGROUND_SCOPES,
    )

    if not pushed_from_override:
        _push_plaintext_to_gsm("playground-api-key", api_key)


async def _seed_and_save_prod_platform_key(db: AsyncSession) -> None:
    override = _resolve_provided_key("PLATFORM_API_KEY")
    pushed_from_override = override is not None
    if override is not None:
        api_key, key_prefix = override
    else:
        api_key, key_prefix = generate_api_key()

    user_id = await get_or_create_platform_user(db)
    key_hash = get_password_hash(api_key)
    await seed_api_key(
        db,
        key_hash,
        PROD_PLATFORM_API_KEY_NAME,
        key_prefix,
        user_id=user_id,
        scopes=PLATFORM_SCOPES,
    )

    if not pushed_from_override:
        _push_plaintext_to_gsm("platform-api-key", api_key)


async def main() -> None:
    environment = os.environ.get("ENVIRONMENT", "unknown")
    is_production = environment == "production"

    print("================================================")
    print("Open Notes - API Key Seeding")
    print("================================================")
    print(f"Environment: {environment}")
    print()

    async with AsyncSession(get_engine()) as session:
        try:
            result = await session.execute(text("SELECT COUNT(*) FROM api_keys"))
            existing_key_count = result.scalar_one()

            if existing_key_count == 0:
                print("Info: First-time setup: Initializing fresh database with API key")
            else:
                print(f"Info: Existing database found with {existing_key_count} API key(s)")

            print()

            if is_production:
                await _seed_and_save_prod_key(session)
                await _seed_and_save_prod_playground_key(session)
                await _seed_and_save_prod_platform_key(session)
                await session.commit()
                print()
                print("=" * 60)
                print("API keys seeded and pushed to Google Secret Manager:")
                print("  - Discord bot:  secret/opennotes-api-key")
                print("  - Playground:   secret/playground-api-key")
                print("  - Platform:     secret/platform-api-key")
                print("=" * 60)
                print()
                print("  Redeploy dependent services to pick up the new secret versions.")
                print("  Plaintext keys were never written to disk or stdout.")
                print("=" * 60)
            elif environment in ["development", "local"]:
                await seed_dev_api_key(session)
                await seed_playground_api_key(session)
                await seed_platform_api_key(session)
                await session.commit()
                print()
                print("✓ API key seeding completed successfully")
            else:
                print(f"⚠️  WARNING: Skipping API key seeding in '{environment}' environment")
                print("   Set ENVIRONMENT=production or ENVIRONMENT=local to seed keys")
                sys.exit(0)

            print()
        except Exception as e:
            await session.rollback()
            print(f"✗ Error seeding API keys: {e}")
            print()
            print("Note: This is not critical. API keys can be manually created via the API.")
            sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Fatal error: {e}")
        sys.exit(1)
