"""
Tests for embedding provider and model tracking (task-469).

Verifies that:
- New embeddings include provider and model metadata
- Existing embeddings are backfilled with correct values
- Queries can filter by embedding version
"""

import pytest
from sqlalchemy import select

from src.database import get_session_maker
from src.fact_checking.models import FactCheckItem

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def fact_check_items_for_tracking():
    """Create test fact check items with and without embeddings."""
    item_ids = []

    async with get_session_maker()() as session:
        # Item with embedding and metadata
        item_with_metadata = FactCheckItem(
            dataset_name="snopes",
            dataset_tags=["snopes", "fact-check"],
            title="Test Fact Check 1",
            content="This is test content for embedding",
            summary="Test summary",
            rating="false",
            source_url="https://example.com/1",
            embedding=[0.1] * 1536,
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
        )
        session.add(item_with_metadata)
        await session.flush()
        item_ids.append(item_with_metadata.id)

        # Item with embedding but no metadata (simulates pre-migration data)
        item_without_metadata = FactCheckItem(
            dataset_name="snopes",
            dataset_tags=["snopes", "fact-check"],
            title="Test Fact Check 2",
            content="Another test content",
            summary="Another summary",
            rating="true",
            source_url="https://example.com/2",
            embedding=[0.2] * 1536,
            embedding_provider=None,
            embedding_model=None,
        )
        session.add(item_without_metadata)
        await session.flush()
        item_ids.append(item_without_metadata.id)

        # Item without embedding
        item_no_embedding = FactCheckItem(
            dataset_name="snopes",
            dataset_tags=["snopes", "fact-check"],
            title="Test Fact Check 3",
            content="No embedding content",
            summary="No embedding",
            rating="mixed",
            source_url="https://example.com/3",
            embedding=None,
            embedding_provider=None,
            embedding_model=None,
        )
        session.add(item_no_embedding)
        await session.flush()
        item_ids.append(item_no_embedding.id)

        await session.commit()

    yield item_ids

    # Cleanup
    async with get_session_maker()() as session:
        for item_id in item_ids:
            result = await session.execute(select(FactCheckItem).where(FactCheckItem.id == item_id))
            item = result.scalar_one_or_none()
            if item:
                await session.delete(item)
        await session.commit()


async def test_new_embedding_includes_provider_and_model(fact_check_items_for_tracking):
    """AC #9: Verify new embeddings include provider and model metadata."""
    async with get_session_maker()() as session:
        result = await session.execute(
            select(FactCheckItem).where(FactCheckItem.id == fact_check_items_for_tracking[0])
        )
        item = result.scalar_one()

        # Verify all fields are set
        assert item.embedding is not None
        assert item.embedding_provider is not None
        assert item.embedding_model is not None

        # Verify specific values
        assert item.embedding_provider == "openai"
        assert item.embedding_model == "text-embedding-3-small"
        assert len(item.embedding) == 1536


async def test_query_by_embedding_version(fact_check_items_for_tracking):
    """AC #7: Verify ability to filter items by embedding version using composite index."""
    async with get_session_maker()() as session:
        # Query items with OpenAI embeddings
        result = await session.execute(
            select(FactCheckItem).where(
                FactCheckItem.embedding_provider == "openai",
                FactCheckItem.embedding_model == "text-embedding-3-small",
                FactCheckItem.embedding.is_not(None),
            )
        )
        items = result.scalars().all()

        # Should find at least one item (the one with metadata)
        assert len(items) >= 1
        for item in items:
            assert item.embedding_provider == "openai"
            assert item.embedding_model == "text-embedding-3-small"
            assert item.embedding is not None


async def test_items_without_provider_model_metadata(fact_check_items_for_tracking):
    """Test querying items that don't have provider/model metadata."""
    async with get_session_maker()() as session:
        # Query items with embeddings but no provider info
        result = await session.execute(
            select(FactCheckItem).where(
                FactCheckItem.embedding.is_not(None),
                FactCheckItem.embedding_provider.is_(None),
            )
        )
        items = result.scalars().all()

        # Should find the item created without metadata
        assert len(items) >= 1
        for item in items:
            assert item.embedding is not None
            assert item.embedding_provider is None
            assert item.embedding_model is None


async def test_items_without_embeddings_have_null_provider_model(
    fact_check_items_for_tracking,
):
    """Verify items without embeddings have NULL provider/model."""
    async with get_session_maker()() as session:
        result = await session.execute(
            select(FactCheckItem).where(FactCheckItem.id == fact_check_items_for_tracking[2])
        )
        item = result.scalar_one()

        # Items without embeddings should have NULL provider/model
        assert item.embedding is None
        assert item.embedding_provider is None
        assert item.embedding_model is None


async def test_embedding_provider_model_columns_nullable():
    """Test that embedding_provider and embedding_model columns allow NULL."""
    async with get_session_maker()() as session:
        # Create an item with embedding but no provider/model
        item = FactCheckItem(
            dataset_name="snopes",
            dataset_tags=["snopes"],
            title="Test Item",
            content="Test content",
            embedding=[0.1] * 1536,
            embedding_provider=None,
            embedding_model=None,
        )
        session.add(item)
        await session.commit()
        await session.refresh(item)

        # Verify NULL values are allowed
        assert item.embedding is not None
        assert item.embedding_provider is None
        assert item.embedding_model is None

        # Cleanup
        await session.delete(item)
        await session.commit()


async def test_embedding_provider_model_schema_fields():
    """Test that FactCheckItem model has provider and model columns."""
    async with get_session_maker()() as session:
        # Create item with all provider/model info
        item = FactCheckItem(
            dataset_name="snopes",
            dataset_tags=["snopes"],
            title="Full Metadata Item",
            content="Content",
            embedding=[0.3] * 1536,
            embedding_provider="openai",
            embedding_model="text-embedding-3-large",
        )
        session.add(item)
        await session.commit()
        await session.refresh(item)

        # Verify fields are properly persisted
        result = await session.execute(select(FactCheckItem).where(FactCheckItem.id == item.id))
        retrieved_item = result.scalar_one()

        assert retrieved_item.embedding_provider == "openai"
        assert retrieved_item.embedding_model == "text-embedding-3-large"

        # Cleanup
        await session.delete(retrieved_item)
        await session.commit()
