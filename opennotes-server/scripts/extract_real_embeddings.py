#!/usr/bin/env python
"""
Simple script to extract real embeddings from the database and format them for the test.
"""

import asyncio
import json
from pathlib import Path

from sqlalchemy import text

from src.database import async_session_maker


async def get_embeddings():
    """Get embeddings and output them in a format ready for the test file."""

    async with async_session_maker() as session:
        # Query for Hitler sex doll fact check
        query = text("""
            SELECT embedding::text
            FROM fact_check_items
            WHERE title = 'Did Hitler Invent the Inflatable Sex Doll?'
            AND dataset_name = 'snopes'
            LIMIT 1
        """)
        result = await session.execute(query)
        hitler_row = result.fetchone()

        # Query for Kamala Harris fact check
        query = text("""
            SELECT embedding::text
            FROM fact_check_items
            WHERE title = 'Did Kamala Harris Support Abortion Until the Time of Giving Birth?'
            AND dataset_name = 'snopes'
            LIMIT 1
        """)
        result = await session.execute(query)
        kamala_row = result.fetchone()

        if hitler_row and hitler_row[0]:
            # Parse the string representation to actual list
            hitler_embedding = json.loads(hitler_row[0])
            print(f"Hitler embedding: {len(hitler_embedding)} dimensions")
            print(f"First 10 values: {hitler_embedding[:10]}")
        else:
            hitler_embedding = None
            print("No Hitler embedding found")

        if kamala_row and kamala_row[0]:
            # Parse the string representation to actual list
            kamala_embedding = json.loads(kamala_row[0])
            print(f"Kamala embedding: {len(kamala_embedding)} dimensions")
            print(f"First 10 values: {kamala_embedding[:10]}")
        else:
            kamala_embedding = None
            print("No Kamala embedding found")

        # Write Python code that can be copied directly into the test
        if hitler_embedding or kamala_embedding:
            with Path("/tmp/real_embeddings_for_test.py").open("w") as f:
                f.write("# Real embeddings from fact_check_items table\n")
                f.write("# Copy this into the test file to replace mock embeddings\n\n")

                if hitler_embedding:
                    f.write("# Hitler sex doll embedding (1536 dimensions)\n")
                    f.write(f"HITLER_EMBEDDING = {hitler_embedding}\n\n")

                if kamala_embedding:
                    f.write("# Kamala Harris abortion embedding (1536 dimensions)\n")
                    f.write(f"KAMALA_EMBEDDING = {kamala_embedding}\n")

            print("\nEmbeddings written to /tmp/real_embeddings_for_test.py")
            print("You can now use these in the test file.")

            return {"hitler": hitler_embedding, "kamala": kamala_embedding}

        return None


if __name__ == "__main__":
    asyncio.run(get_embeddings())
