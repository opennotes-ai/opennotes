#!/usr/bin/env python3
"""
Seed API keys into the database for Discord bot authentication.

This script ensures that the API key used by the Discord bot exists in the database.
It's idempotent and safe to run multiple times.

Usage:
    # Development/Local (uses hardcoded dev key):
    python scripts/seed_api_keys.py

    # Production (generates new key or uses provided key):
    ENVIRONMENT=production python scripts/seed_api_keys.py

    # Production with specific key value:
    ENVIRONMENT=production OPENNOTES_API_KEY=opk_xxx_yyy python scripts/seed_api_keys.py

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

PLAYGROUND_DEV_API_KEY = "opk_playground_dev_readonly_access_key_2024"
PLAYGROUND_API_KEY_NAME = "Playground (Development)"
PLAYGROUND_SERVICE_USER_USERNAME = "playground-service"
PLAYGROUND_SERVICE_USER_EMAIL = "playground@opennotes.local"
PLAYGROUND_SCOPES = ["simulations:read"]


def generate_api_key() -> tuple[str, str]:
    """Generate a new API key in the format: opk_<prefix>_<secret>"""
    prefix = secrets.token_hex(6)
    secret = secrets.token_urlsafe(32)
    full_key = f"opk_{prefix}_{secret}"
    return full_key, prefix


async def get_or_create_service_user(db: AsyncSession):
    result = await db.execute(
        text("SELECT id, username, is_service_account FROM users WHERE username = :username"),
        {"username": SERVICE_USER_USERNAME},
    )
    row = result.first()

    if row:
        user_id = row[0]
        is_service_account = row[2]

        if not is_service_account:
            await db.execute(
                text("UPDATE users SET is_service_account = true WHERE id = :user_id"),
                {"user_id": user_id},
            )
            print(
                f"✓ Service user '{SERVICE_USER_USERNAME}' already exists (ID: {user_id}) - updated is_service_account flag"
            )
        else:
            print(f"✓ Service user '{SERVICE_USER_USERNAME}' already exists (ID: {user_id})")
        return user_id

    hashed_password = get_password_hash(secrets.token_urlsafe(64))

    result = await db.execute(
        text("""
            INSERT INTO users (username, email, hashed_password, full_name, role, is_active, is_superuser, is_service_account, created_at, updated_at)
            VALUES (:username, :email, :hashed_password, :full_name, :role, :is_active, :is_superuser, :is_service_account, NOW(), NOW())
            RETURNING id
        """),
        {
            "username": SERVICE_USER_USERNAME,
            "email": SERVICE_USER_EMAIL,
            "hashed_password": hashed_password,
            "full_name": "Discord Bot Service Account",
            "role": "admin",
            "is_active": True,
            "is_superuser": False,
            "is_service_account": True,
        },
    )
    user_id = result.scalar_one()

    print(f"✓ Created service user '{SERVICE_USER_USERNAME}' (ID: {user_id})")
    return user_id


async def seed_api_key(
    db: AsyncSession,
    api_key: str,
    key_name: str,
    key_prefix: str | None = None,
    user_id: UUID | None = None,
    scopes: list[str] | None = None,
) -> str:
    if user_id is None:
        user_id = await get_or_create_service_user(db)

    key_hash = get_password_hash(api_key)
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
                text("UPDATE api_keys SET scopes = :scopes::jsonb WHERE id = :id"),
                {"id": api_key_id, "scopes": scopes_json},
            )
            print(f"✓ Updated scopes on API key '{key_name}'")
        else:
            await db.execute(
                text(
                    "UPDATE api_keys SET is_active = true, key_hash = :key_hash, key_prefix = :key_prefix, scopes = :scopes::jsonb WHERE id = :id"
                ),
                {
                    "id": api_key_id,
                    "key_hash": key_hash,
                    "key_prefix": key_prefix,
                    "scopes": scopes_json,
                },
            )
            print(f"✓ Reactivated API key '{key_name}'")
        return api_key

    result = await db.execute(
        text("""
            INSERT INTO api_keys (user_id, name, key_hash, key_prefix, is_active, scopes, created_at)
            VALUES (:user_id, :name, :key_hash, :key_prefix, :is_active, :scopes::jsonb, NOW())
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
    return api_key


async def get_or_create_playground_user(db: AsyncSession):
    result = await db.execute(
        text("SELECT id, username, is_service_account FROM users WHERE username = :username"),
        {"username": PLAYGROUND_SERVICE_USER_USERNAME},
    )
    row = result.first()

    if row:
        user_id = row[0]
        is_service_account = row[2]

        if is_service_account:
            await db.execute(
                text("UPDATE users SET is_service_account = false WHERE id = :user_id"),
                {"user_id": user_id},
            )
            print(
                f"✓ Playground user '{PLAYGROUND_SERVICE_USER_USERNAME}' already exists (ID: {user_id}) - cleared is_service_account flag"
            )
        else:
            print(
                f"✓ Playground user '{PLAYGROUND_SERVICE_USER_USERNAME}' already exists (ID: {user_id})"
            )
        return user_id

    hashed_password = get_password_hash(secrets.token_urlsafe(64))

    result = await db.execute(
        text("""
            INSERT INTO users (username, email, hashed_password, full_name, role, is_active, is_superuser, is_service_account, created_at, updated_at)
            VALUES (:username, :email, :hashed_password, :full_name, :role, :is_active, :is_superuser, :is_service_account, NOW(), NOW())
            RETURNING id
        """),
        {
            "username": PLAYGROUND_SERVICE_USER_USERNAME,
            "email": PLAYGROUND_SERVICE_USER_EMAIL,
            "hashed_password": hashed_password,
            "full_name": "Playground User",
            "role": "user",
            "is_active": True,
            "is_superuser": False,
            "is_service_account": False,
        },
    )
    user_id = result.scalar_one()

    print(f"✓ Created playground user '{PLAYGROUND_SERVICE_USER_USERNAME}' (ID: {user_id})")
    return user_id


async def seed_playground_api_key(db: AsyncSession) -> None:
    user_id = await get_or_create_playground_user(db)
    api_key = await seed_api_key(
        db,
        PLAYGROUND_DEV_API_KEY,
        PLAYGROUND_API_KEY_NAME,
        key_prefix="playground",
        user_id=user_id,
        scopes=PLAYGROUND_SCOPES,
    )
    print(f"  Key value: {api_key}")


async def seed_dev_api_key(db: AsyncSession) -> None:
    api_key = await seed_api_key(db, DEV_API_KEY, DEV_API_KEY_NAME)
    print(f"  Key value: {api_key}")


async def seed_prod_api_key(db: AsyncSession) -> str:
    """Seed a production API key. Generates a new key or uses OPENNOTES_API_KEY env var."""
    provided_key = os.environ.get("OPENNOTES_API_KEY", "")

    if provided_key and not provided_key.startswith("CHANGE_THIS"):
        api_key = provided_key
        key_prefix = None
        if api_key.startswith("opk_"):
            parts = api_key.split("_", 2)
            if len(parts) == 3:
                key_prefix = parts[1]
        print("Using provided API key from OPENNOTES_API_KEY env var")
    else:
        api_key, key_prefix = generate_api_key()
        print("Generated new API key (no valid OPENNOTES_API_KEY provided)")

    await seed_api_key(db, api_key, PROD_API_KEY_NAME, key_prefix)
    return api_key


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
                api_key = await seed_prod_api_key(session)
                await session.commit()
                print()
                print("=" * 60)
                print("⚠️  IMPORTANT: Save this API key securely!")
                print("=" * 60)
                print()
                print(f"  OPENNOTES_API_KEY: {api_key}")
                print()
                print("Add this to your secrets.yaml and re-encrypt with SOPS:")
                print(f'  opennotes_api_key: "{api_key}"')
                print()
                print("Then redeploy for the change to take effect.")
                print("=" * 60)
            elif environment in ["development", "local"]:
                await seed_dev_api_key(session)
                await seed_playground_api_key(session)
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
        sys.exit(0)
