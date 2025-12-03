#!/usr/bin/env python3
"""
Seed development API keys into the database.

This script ensures that the development API key used by the Discord bot
exists in the database. It's idempotent and safe to run multiple times.

Usage:
    python scripts/seed_api_keys.py

    Or via mise:
    mise run db:seed-api-keys
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.password import get_password_hash
from src.database import get_engine

DEV_API_KEY = "XcvlCe7ewY4z4VzbWeogvkJZA-5hxY_xJn5PJmZJN0c"
DEV_API_KEY_NAME = "Discord Bot (Development)"
SERVICE_USER_USERNAME = "discord-bot-service"
SERVICE_USER_EMAIL = "discord-bot@opennotes.local"


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

    hashed_password = get_password_hash("unused-service-account-password")

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


async def seed_dev_api_key(db: AsyncSession) -> None:
    user_id = await get_or_create_service_user(db)

    key_hash = get_password_hash(DEV_API_KEY)

    result = await db.execute(
        text("SELECT id, is_active FROM api_keys WHERE user_id = :user_id AND name = :name"),
        {"user_id": user_id, "name": DEV_API_KEY_NAME},
    )
    row = result.first()

    if row:
        api_key_id, is_active = row
        if is_active:
            print(f"✓ Development API key '{DEV_API_KEY_NAME}' already exists and is active")
        else:
            await db.execute(
                text("UPDATE api_keys SET is_active = true, key_hash = :key_hash WHERE id = :id"),
                {"id": api_key_id, "key_hash": key_hash},
            )
            print(f"✓ Reactivated development API key '{DEV_API_KEY_NAME}'")
        return

    result = await db.execute(
        text("""
            INSERT INTO api_keys (user_id, name, key_hash, is_active, created_at)
            VALUES (:user_id, :name, :key_hash, :is_active, NOW())
            RETURNING id
        """),
        {
            "user_id": user_id,
            "name": DEV_API_KEY_NAME,
            "key_hash": key_hash,
            "is_active": True,
        },
    )
    api_key_id = result.scalar_one()

    print(f"✓ Created development API key '{DEV_API_KEY_NAME}' (ID: {api_key_id})")
    print(f"  Key value: {DEV_API_KEY}")
    print(f"  User ID: {user_id}")
    print("  Never expires: True")


async def main() -> None:
    import os

    environment = os.environ.get("ENVIRONMENT", "unknown")

    print("================================================")
    print("Open Notes - Development API Key Seeding")
    print("================================================")
    print(f"Environment: {environment}")
    print()

    # Safety check: Only auto-seed in development environments
    if environment not in ["development", "local"]:
        print(f"⚠️  WARNING: Skipping API key seeding in '{environment}' environment")
        print("   Auto-seeding is only enabled for development/local environments")
        print("   Production API keys should be manually managed for security")
        print()
        sys.exit(0)

    async with AsyncSession(get_engine()) as session:
        try:
            # Check if this is a fresh database (no API keys yet)
            result = await session.execute(text("SELECT COUNT(*) FROM api_keys"))
            existing_key_count = result.scalar_one()

            if existing_key_count == 0:
                print(
                    "Info: First-time setup: Initializing fresh database with development API key"
                )
            else:
                print(f"Info: Existing database found with {existing_key_count} API key(s)")

            print()

            await seed_dev_api_key(session)
            await session.commit()
            print()
            print("✓ API key seeding completed successfully")
            print()
        except Exception as e:
            await session.rollback()
            print(f"✗ Error seeding API keys: {e}")
            print()
            print("Note: This is not critical. API keys can be manually created via the API.")
            sys.exit(0)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Fatal error: {e}")
        sys.exit(0)
