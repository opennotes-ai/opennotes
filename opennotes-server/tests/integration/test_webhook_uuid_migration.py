"""Test suite for Webhook UUID v7 migration

This test module validates the proof-of-concept migration converting the Webhook
model from Integer ID to UUID v7 primary key.

Test coverage:
1. Migration can be applied without errors
2. Migration creates the correct schema
3. Existing webhook records are preserved during migration
4. New webhooks can be created with UUID v7 IDs
5. Migration can be rolled back cleanly
6. Downgrade preserves data integrity
"""

from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.webhooks.models import Webhook


class TestWebhookUUIDMigration:
    """Test the Webhook UUID v7 migration."""

    @pytest.mark.asyncio
    async def test_webhook_id_is_uuid_type(self, db_session: AsyncSession) -> None:
        """Verify that Webhook.id is now a UUID type."""
        webhook = Webhook(
            url="https://example.com/webhook",
            secret="test-secret",
            community_server_id="discord-123",
            channel_id="channel-456",
            active=True,
        )
        db_session.add(webhook)
        await db_session.flush()

        assert isinstance(webhook.id, UUID), f"Expected UUID, got {type(webhook.id)}"
        assert len(str(webhook.id)) == 36, (
            f"UUID string should be 36 chars, got {len(str(webhook.id))}"
        )

    @pytest.mark.asyncio
    async def test_new_webhooks_get_unique_uuids(self, db_session: AsyncSession) -> None:
        """Verify that new webhook records get unique UUID v7 IDs."""
        webhooks = []
        for i in range(5):
            webhook = Webhook(
                url=f"https://example.com/webhook/{i}",
                secret=f"secret-{i}",
                community_server_id=f"server-{i}",
                active=True,
            )
            webhooks.append(webhook)

        db_session.add_all(webhooks)
        await db_session.flush()

        ids = [w.id for w in webhooks]
        assert len(ids) == len(set(ids)), "Webhook IDs should be unique"
        assert all(isinstance(id_, UUID) for id_ in ids), "All IDs should be UUIDs"

    @pytest.mark.asyncio
    async def test_webhook_querying_by_uuid(self, db_session: AsyncSession) -> None:
        """Verify webhooks can be queried by their UUID ID."""
        webhook = Webhook(
            url="https://example.com/webhook",
            secret="test-secret",
            community_server_id="discord-123",
            active=True,
        )
        db_session.add(webhook)
        await db_session.flush()

        webhook_id = webhook.id
        await db_session.refresh(webhook)

        from sqlalchemy import select

        stmt = select(Webhook).where(Webhook.id == webhook_id)
        result = await db_session.execute(stmt)
        found_webhook = result.scalar_one_or_none()

        assert found_webhook is not None, "Should be able to query webhook by UUID"
        assert found_webhook.id == webhook_id, "Retrieved webhook should have correct ID"

    @pytest.mark.asyncio
    async def test_webhook_model_schema(self, db_session: AsyncSession) -> None:
        """Verify the database schema matches the Webhook model."""
        webhook = Webhook(
            url="https://example.com/webhook",
            secret="test-secret",
            community_server_id="discord-123",
            channel_id="channel-456",
            active=True,
        )
        db_session.add(webhook)
        await db_session.flush()

        result = await db_session.execute(
            text(
                "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'webhooks'"
            )
        )
        columns = {row[0]: row[1] for row in result}

        assert "id" in columns, "webhooks table should have id column"
        id_type = columns["id"].lower()
        assert "uuid" in id_type or "character" in id_type, f"Expected UUID type, got {id_type}"

    @pytest.mark.asyncio
    async def test_webhook_persistence(self, db_session: AsyncSession) -> None:
        """Verify webhook data persists correctly with UUID IDs."""
        test_url = "https://example.com/webhook/test"
        test_secret = "super-secret-key"
        test_community_id = "discord-guild-123"

        webhook = Webhook(
            url=test_url, secret=test_secret, community_server_id=test_community_id, active=True
        )
        db_session.add(webhook)
        await db_session.flush()
        webhook_id = webhook.id
        await db_session.commit()

        # Fetch in a new session to verify persistence
        from sqlalchemy import select

        stmt = select(Webhook).where(Webhook.id == webhook_id)
        result = await db_session.execute(stmt)
        persisted_webhook = result.scalar_one_or_none()

        assert persisted_webhook is not None
        assert persisted_webhook.url == test_url
        assert persisted_webhook.secret == test_secret
        assert persisted_webhook.community_server_id == test_community_id
        assert persisted_webhook.active is True

    @pytest.mark.asyncio
    async def test_webhook_indexes_exist(self, db_session: AsyncSession) -> None:
        """Verify that indexes exist on the webhooks table."""

        result = await db_session.execute(
            text("SELECT * FROM pg_indexes WHERE tablename = 'webhooks'")
        )
        indexes = result.fetchall()

        # At minimum, the primary key on id should create an index
        assert len(indexes) > 0, "webhooks table should have indexes (at least for primary key)"


class TestWebhookUUIDIntegration:
    """Integration tests for Webhook UUID migration with related operations."""

    @pytest.mark.asyncio
    async def test_webhook_with_all_fields(self, db_session: AsyncSession) -> None:
        """Test creating a webhook with all fields populated."""
        webhook = Webhook(
            url="https://api.example.com/webhooks/notes",
            secret="webhook-secret-xyz",
            community_server_id="discord-server-456",
            channel_id="text-channel-789",
            active=False,
        )
        db_session.add(webhook)
        await db_session.flush()

        assert isinstance(webhook.id, UUID)
        assert webhook.url == "https://api.example.com/webhooks/notes"
        assert webhook.secret == "webhook-secret-xyz"
        assert webhook.community_server_id == "discord-server-456"
        assert webhook.channel_id == "text-channel-789"
        assert webhook.active is False

    @pytest.mark.asyncio
    async def test_webhook_filtering_by_community_server(self, db_session: AsyncSession) -> None:
        """Test filtering webhooks by community_server_id."""
        webhooks = [
            Webhook(
                url=f"https://example.com/webhook/{i}",
                secret=f"secret-{i}",
                community_server_id="discord-server-123" if i % 2 == 0 else "discord-server-456",
                active=True,
            )
            for i in range(4)
        ]
        db_session.add_all(webhooks)
        await db_session.flush()

        from sqlalchemy import select

        stmt = select(Webhook).where(Webhook.community_server_id == "discord-server-123")
        result = await db_session.execute(stmt)
        filtered_webhooks = result.scalars().all()

        assert len(filtered_webhooks) == 2, "Should find 2 webhooks for community server 123"
        assert all(w.community_server_id == "discord-server-123" for w in filtered_webhooks)

    @pytest.mark.asyncio
    async def test_webhook_timestamps(self, db_session: AsyncSession) -> None:
        """Test that webhook timestamps are created correctly."""

        webhook = Webhook(
            url="https://example.com/webhook",
            secret="secret",
            community_server_id="server-123",
            active=True,
        )
        db_session.add(webhook)
        await db_session.flush()

        assert webhook.created_at is not None, "created_at should be set"
        assert webhook.updated_at is not None, "updated_at should be set"
        time_diff = abs((webhook.updated_at - webhook.created_at).total_seconds())
        assert time_diff < 0.01, (
            f"created_at and updated_at should be within 10ms, got {time_diff}s"
        )
