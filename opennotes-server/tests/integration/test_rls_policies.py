from uuid import uuid4

import pendulum
import pytest
from sqlalchemy import insert, text

from src.database import get_engine, get_session_maker
from src.llm_config.models import CommunityServer
from src.moderation_actions.models import ModerationAction
from src.notes.models import Request
from src.users.profile_models import CommunityMember, UserProfile
from src.webhooks.delivery_models import WebhookDelivery
from src.webhooks.models import Webhook


@pytest.mark.integration
class TestRLSPolicies:
    async def _seed_test_data(self):
        community_id = uuid4()
        member_profile_id = uuid4()
        request_id = uuid4()
        moderation_action_id = uuid4()
        webhook_id = uuid4()
        webhook_delivery_id = uuid4()

        now = pendulum.now("UTC")

        async with get_session_maker()() as session:
            await session.execute(
                insert(CommunityServer).values(
                    id=community_id,
                    platform="discord",
                    platform_community_server_id=f"rls-test-guild-{community_id}",
                    name="RLS Test Community",
                )
            )

            await session.execute(
                insert(UserProfile).values(
                    id=member_profile_id,
                    display_name="RLS Test Member",
                )
            )

            await session.execute(
                insert(CommunityMember).values(
                    id=uuid4(),
                    community_id=community_id,
                    profile_id=member_profile_id,
                    is_active=True,
                    joined_at=now,
                )
            )

            await session.execute(
                insert(Request).values(
                    id=request_id,
                    request_id=f"rls-test-req-{request_id}",
                    community_server_id=community_id,
                    requested_by="rls-test-user",
                    status="COMPLETED",
                )
            )

            await session.execute(
                insert(ModerationAction).values(
                    id=moderation_action_id,
                    request_id=request_id,
                    community_server_id=community_id,
                    action_type="hide",
                    action_tier="tier_1_immediate",
                    action_state="proposed",
                    review_group="community",
                )
            )

            await session.execute(
                insert(Webhook).values(
                    id=webhook_id,
                    url="https://example.com/rls-test-webhook",
                    secret="rls-test-secret",
                    community_server_id=community_id,
                    active=True,
                )
            )

            await session.execute(
                insert(WebhookDelivery).values(
                    id=webhook_delivery_id,
                    webhook_id=webhook_id,
                    event_type="test.event",
                    event_id=str(uuid4()),
                    payload={"test": True},
                    status="pending",
                )
            )

            await session.commit()

        return {
            "community_id": community_id,
            "member_profile_id": member_profile_id,
            "request_id": request_id,
            "moderation_action_id": moderation_action_id,
            "webhook_id": webhook_id,
            "webhook_delivery_id": webhook_delivery_id,
        }

    @pytest.mark.asyncio
    async def test_member_sees_own_community_moderation_actions(self):
        ids = await self._seed_test_data()

        engine = get_engine()
        async with engine.connect() as conn, conn.begin():
            await conn.execute(text("GRANT USAGE ON SCHEMA public TO authenticated"))
            await conn.execute(text("GRANT USAGE ON SCHEMA auth TO authenticated"))
            await conn.execute(text("GRANT SELECT ON moderation_actions TO authenticated"))
            await conn.execute(text("GRANT SELECT ON community_members TO authenticated"))
            await conn.execute(text("GRANT EXECUTE ON FUNCTION auth.uid() TO authenticated"))
            await conn.execute(
                text("GRANT EXECUTE ON FUNCTION public.is_community_member(uuid) TO authenticated")
            )

            await conn.execute(
                text(f"""
                    CREATE OR REPLACE FUNCTION auth.uid()
                    RETURNS uuid
                    LANGUAGE sql
                    STABLE
                    AS $$ SELECT '{ids["member_profile_id"]}'::uuid $$
                """)
            )

            await conn.execute(text("SET LOCAL ROLE authenticated"))

            result = await conn.execute(text("SELECT id FROM moderation_actions"))
            rows = result.fetchall()

            assert len(rows) == 1
            assert rows[0][0] == ids["moderation_action_id"]

            await conn.execute(text("RESET ROLE"))

    @pytest.mark.asyncio
    async def test_non_member_sees_zero_moderation_actions(self):
        await self._seed_test_data()

        non_member_id = uuid4()

        engine = get_engine()
        async with engine.connect() as conn, conn.begin():
            await conn.execute(text("GRANT USAGE ON SCHEMA public TO authenticated"))
            await conn.execute(text("GRANT USAGE ON SCHEMA auth TO authenticated"))
            await conn.execute(text("GRANT SELECT ON moderation_actions TO authenticated"))
            await conn.execute(text("GRANT SELECT ON community_members TO authenticated"))
            await conn.execute(text("GRANT EXECUTE ON FUNCTION auth.uid() TO authenticated"))
            await conn.execute(
                text("GRANT EXECUTE ON FUNCTION public.is_community_member(uuid) TO authenticated")
            )

            await conn.execute(
                text(f"""
                    CREATE OR REPLACE FUNCTION auth.uid()
                    RETURNS uuid
                    LANGUAGE sql
                    STABLE
                    AS $$ SELECT '{non_member_id}'::uuid $$
                """)
            )

            await conn.execute(text("SET LOCAL ROLE authenticated"))

            result = await conn.execute(text("SELECT id FROM moderation_actions"))
            rows = result.fetchall()

            assert len(rows) == 0

            await conn.execute(text("RESET ROLE"))

    @pytest.mark.asyncio
    async def test_authenticated_sees_zero_webhooks(self):
        await self._seed_test_data()

        engine = get_engine()
        async with engine.connect() as conn, conn.begin():
            await conn.execute(text("GRANT USAGE ON SCHEMA public TO authenticated"))
            await conn.execute(text("GRANT SELECT ON webhooks TO authenticated"))

            await conn.execute(text("SET LOCAL ROLE authenticated"))

            result = await conn.execute(text("SELECT id FROM webhooks"))
            rows = result.fetchall()

            assert len(rows) == 0

            await conn.execute(text("RESET ROLE"))

    @pytest.mark.asyncio
    async def test_authenticated_sees_zero_webhook_deliveries(self):
        await self._seed_test_data()

        engine = get_engine()
        async with engine.connect() as conn, conn.begin():
            await conn.execute(text("GRANT USAGE ON SCHEMA public TO authenticated"))
            await conn.execute(text("GRANT SELECT ON webhook_deliveries TO authenticated"))

            await conn.execute(text("SET LOCAL ROLE authenticated"))

            result = await conn.execute(text("SELECT id FROM webhook_deliveries"))
            rows = result.fetchall()

            assert len(rows) == 0

            await conn.execute(text("RESET ROLE"))
