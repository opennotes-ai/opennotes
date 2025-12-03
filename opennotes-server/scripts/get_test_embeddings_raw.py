#!/usr/bin/env python
"""
Script to fetch real embeddings for specific fact-check items used in tests using raw SQL.
"""

import asyncio
import json
from pathlib import Path

from sqlalchemy import text

from src.database import async_session_maker


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
            # Query using raw SQL to avoid model relationship issues
            query = text("""
                SELECT id, title, rating, content, embedding
                FROM fact_check_items
                WHERE title = :title AND dataset_name = 'snopes'
                LIMIT 1
            """)

            result = await session.execute(query, {"title": title})
            row = result.fetchone()

            if row:
                print(f"Found: {title}")
                print(f"  - ID: {row.id}")
                print(f"  - Rating: {row.rating}")
                print(f"  - Has embedding: {row.embedding is not None}")

                if row.embedding:
                    # embedding is stored as a vector in postgres
                    # Convert to Python list for use in test
                    embedding_list = (
                        list(row.embedding) if hasattr(row.embedding, "__iter__") else None
                    )
                    if embedding_list:
                        print(f"  - Embedding length: {len(embedding_list)}")
                        print(f"  - First 5 values: {embedding_list[:5]}")

                    results[title] = {
                        "id": row.id,
                        "rating": row.rating,
                        "content": row.content[:200] + "..."
                        if len(row.content) > 200
                        else row.content,
                        "embedding_sample": embedding_list[:10] if embedding_list else None,
                        "embedding_full": embedding_list,  # Store full embedding
                    }
                else:
                    print("  - WARNING: No embedding found!")
                    results[title] = {
                        "id": row.id,
                        "rating": row.rating,
                        "content": row.content[:200] + "..."
                        if len(row.content) > 200
                        else row.content,
                        "embedding_sample": None,
                        "embedding_full": None,
                    }
            else:
                print(f"NOT FOUND: {title}")
                results[title] = None

        # Save results to file for inspection
        with Path("/tmp/test_embeddings.json").open("w") as f:
            # Convert to serializable format
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
                        "embedding_length": len(data["embedding_full"])
                        if data["embedding_full"]
                        else 0,
                    }
                else:
                    serializable_results[title] = None
            json.dump(serializable_results, f, indent=2, default=str)

        print("\nResults saved to /tmp/test_embeddings.json")

        # If we have embeddings, also create a Python file with the actual values
        # that we can copy into the test
        if any(data and data.get("embedding_full") for data in results.values()):
            with Path("/tmp/test_embeddings.py").open("w") as f:
                f.write("# Real embeddings from fact_check_items table\n")
                f.write("# Copy these into the test file\n\n")
                f.write("TEST_EMBEDDINGS = {\n")

                for title, data in results.items():
                    if data and data.get("embedding_full"):
                        # Write only first 100 values for brevity, but note we have the full 1536
                        embedding_repr = repr(data["embedding_full"][:100])
                        f.write(
                            f'    "{title}": {embedding_repr}[...],  # truncated, full length: {len(data["embedding_full"])}\n'
                        )

                f.write("}\n")

            print("Python embeddings saved to /tmp/test_embeddings.py")

        return results


if __name__ == "__main__":
    asyncio.run(get_test_embeddings())
