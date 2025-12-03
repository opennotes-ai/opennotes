#!/usr/bin/env python
"""
Script to fetch real embeddings for specific fact-check items used in tests.
"""

import asyncio
import json
from pathlib import Path

from sqlalchemy import select

from src.database import async_session_maker
from src.fact_checking.models import FactCheckItem


async def get_test_embeddings():
    """Fetch embeddings for specific test items."""

    # Define the titles we're looking for (from the test)
    test_items = [
        "Did Hitler Invent the Inflatable Sex Doll?",
        "Did Kamala Harris Support Abortion Until the Time of Giving Birth?",
    ]

    async with async_session_maker() as session:
        results = {}

        for title in test_items:
            # Query for the specific item
            stmt = select(FactCheckItem).where(
                FactCheckItem.title == title, FactCheckItem.dataset_name == "snopes"
            )
            result = await session.execute(stmt)
            item = result.scalar_one_or_none()

            if item:
                print(f"Found: {title}")
                print(f"  - ID: {item.id}")
                print(f"  - Rating: {item.rating}")
                print(f"  - Has embedding: {item.embedding is not None}")
                if item.embedding:
                    print(f"  - Embedding length: {len(item.embedding)}")
                    # Store the first 10 values as a sample
                    results[title] = {
                        "id": item.id,
                        "rating": item.rating,
                        "content": item.content[:200] + "..."
                        if len(item.content) > 200
                        else item.content,
                        "embedding_sample": item.embedding[:10] if item.embedding else None,
                        "embedding_full": item.embedding,  # Store full embedding
                    }
            else:
                print(f"NOT FOUND: {title}")
                results[title] = None

        # Save results to file for inspection
        with Path("/tmp/test_embeddings.json").open("w") as f:
            # Convert to serializable format (embedding might be bytes)
            serializable_results = {}
            for title, data in results.items():
                if data:
                    serializable_results[title] = {
                        "id": data["id"],
                        "rating": data["rating"],
                        "content": data["content"],
                        "embedding_sample": data["embedding_sample"][:5]
                        if data["embedding_sample"]
                        else None,
                        "has_full_embedding": data["embedding_full"] is not None,
                    }
                else:
                    serializable_results[title] = None
            json.dump(serializable_results, f, indent=2)

        print("\nResults saved to /tmp/test_embeddings.json")

        return results


if __name__ == "__main__":
    asyncio.run(get_test_embeddings())
