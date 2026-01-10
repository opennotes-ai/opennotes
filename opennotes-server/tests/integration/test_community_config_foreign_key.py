from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

import src.database
from src.community_config.models import CommunityConfig
from src.llm_config.models import CommunityServer
from src.users.models import User


def make_unique_username(base: str) -> str:
    """Generate a unique username by appending a UUID suffix."""
    return f"{base}_{uuid4().hex[:8]}"


@pytest.mark.asyncio
async def test_community_config_foreign_key_constraint():
    """Test that community_config has a foreign key constraint to community_servers."""
    async with src.database.async_session_maker() as session:
        # Create a User for updated_by
        username = make_unique_username("testuser")
        user = User(
            username=username,
            email=f"{username}@example.com",
            hashed_password="hashed",
            role="admin",
            is_active=True,
        )
        session.add(user)
        await session.flush()
        user_id = user.id

        # Create a CommunityServer
        community_server = CommunityServer(
            platform="discord",
            platform_community_server_id=uuid4().hex,
            name="Test Server",
        )
        session.add(community_server)
        await session.flush()
        server_id = community_server.id

        # Try to create a CommunityConfig for the server
        config = CommunityConfig(
            community_server_id=server_id,
            config_key="test_key",
            config_value="test_value",
            updated_by=user_id,
        )
        session.add(config)
        await session.commit()

        # Verify the config was created
        result = await session.execute(
            select(CommunityConfig).where(CommunityConfig.community_server_id == server_id)
        )
        configs = result.scalars().all()
        assert len(configs) == 1
        assert configs[0].config_key == "test_key"


@pytest.mark.asyncio
async def test_community_config_fk_rejects_invalid_server():
    """Test that community_config rejects foreign keys to non-existent servers."""
    async with src.database.async_session_maker() as session:
        # Create a User for updated_by
        username = make_unique_username("testuser")
        user = User(
            username=username,
            email=f"{username}@example.com",
            hashed_password="hashed",
            role="admin",
            is_active=True,
        )
        session.add(user)
        await session.flush()
        user_id = user.id

        # Try to create a CommunityConfig with a non-existent server ID
        fake_server_id = uuid4()

        config = CommunityConfig(
            community_server_id=fake_server_id,
            config_key="test_key",
            config_value="test_value",
            updated_by=user_id,
        )
        session.add(config)

        # Should raise IntegrityError due to foreign key violation
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_community_config_cascade_delete_on_server_delete():
    """Test that deleting a community server cascades to delete its configs."""
    async with src.database.async_session_maker() as session:
        # Create a User for updated_by
        username = make_unique_username("testuser")
        user = User(
            username=username,
            email=f"{username}@example.com",
            hashed_password="hashed",
            role="admin",
            is_active=True,
        )
        session.add(user)
        await session.flush()
        user_id = user.id

        # Create a CommunityServer
        community_server = CommunityServer(
            platform="discord",
            platform_community_server_id=uuid4().hex,
            name="Test Server to Delete",
        )
        session.add(community_server)
        await session.flush()
        server_id = community_server.id

        # Create multiple configs for the server
        for i in range(3):
            config = CommunityConfig(
                community_server_id=server_id,
                config_key=f"key_{i}",
                config_value=f"value_{i}",
                updated_by=user_id,
            )
            session.add(config)
        await session.commit()

        # Verify configs exist
        result = await session.execute(
            select(func.count(CommunityConfig.community_server_id)).where(
                CommunityConfig.community_server_id == server_id
            )
        )
        count_before = result.scalar()
        assert count_before == 3

        # Delete the server
        await session.execute(delete(CommunityServer).where(CommunityServer.id == server_id))
        await session.commit()

        # Verify configs are automatically deleted (cascade)
        result = await session.execute(
            select(func.count(CommunityConfig.community_server_id)).where(
                CommunityConfig.community_server_id == server_id
            )
        )
        count_after = result.scalar()
        assert count_after == 0


@pytest.mark.asyncio
async def test_community_config_relationship_loading():
    """Test that CommunityConfig has a proper relationship to CommunityServer."""
    async with src.database.async_session_maker() as session:
        # Create a User for updated_by
        username = make_unique_username("testuser")
        user = User(
            username=username,
            email=f"{username}@example.com",
            hashed_password="hashed",
            role="admin",
            is_active=True,
        )
        session.add(user)
        await session.flush()
        user_id = user.id

        # Create a CommunityServer
        community_server = CommunityServer(
            platform="discord",
            platform_community_server_id=uuid4().hex,
            name="Relationship Test Server",
        )
        session.add(community_server)
        await session.flush()
        server_id = community_server.id

        # Create a config
        config = CommunityConfig(
            community_server_id=server_id,
            config_key="relationship_test",
            config_value="test_value",
            updated_by=user_id,
        )
        session.add(config)
        await session.commit()

        # Query the config and verify we can access its related server
        result = await session.execute(
            select(CommunityConfig).where(CommunityConfig.community_server_id == server_id)
        )
        fetched_config = result.scalar_one()

        # Verify the relationship is available
        assert fetched_config.community_server is not None
        assert fetched_config.community_server.id == server_id
        assert fetched_config.community_server.name == "Relationship Test Server"


@pytest.mark.asyncio
async def test_community_server_has_configs_relationship():
    """Test that CommunityServer has a relationship to its configs."""
    async with src.database.async_session_maker() as session:
        # Create a User for updated_by
        username = make_unique_username("testuser")
        user = User(
            username=username,
            email=f"{username}@example.com",
            hashed_password="hashed",
            role="admin",
            is_active=True,
        )
        session.add(user)
        await session.flush()
        user_id = user.id

        # Create a CommunityServer
        community_server = CommunityServer(
            platform="discord",
            platform_community_server_id=uuid4().hex,
            name="Config Relationship Test",
        )
        session.add(community_server)
        await session.flush()
        server_id = community_server.id

        # Create multiple configs
        for i in range(2):
            config = CommunityConfig(
                community_server_id=server_id,
                config_key=f"key_{i}",
                config_value=f"value_{i}",
                updated_by=user_id,
            )
            session.add(config)
        await session.commit()

        # Query the server and verify its configs are available
        result = await session.execute(
            select(CommunityServer).where(CommunityServer.id == server_id)
        )
        fetched_server = result.scalar_one()

        # Verify the relationship is available
        assert fetched_server.configs is not None
        assert len(fetched_server.configs) == 2
        assert all(isinstance(config, CommunityConfig) for config in fetched_server.configs)
        assert all(config.community_server_id == server_id for config in fetched_server.configs)
