#!/usr/bin/env python3
"""Test script to reproduce the Discord bot request creation error."""

import asyncio
import json
import sys
from datetime import datetime

import httpx


async def test_request_creation():
    """Test creating a request with fact-check match data."""

    # This mimics the exact request from Discord bot
    request_payload = {
        "request_id": f"discord-test-{datetime.now().timestamp()}",
        "tweet_id": 4536233844,  # Large integer that needs to be a string in response
        "original_message_content": """**Fact-Check Match Found** (Confidence: 76.4%)

**Source:** SNOPES - False
**Title:** Did Hitler Invent the Inflatable Sex Doll?

**Summary:** Readers shared a 2016 blog post with the headline, "Did Adolf Hitler Really Invent the Sex Doll?" The post prompted many curious readers to inquire as to whether the leader of Germany's Nazi Party did in fact invent inflatable sex dolls. The article was posted to a website called The 13th Floor, a horror-genre blog which focuses on stories that are creepy and macabre in nature. There is no evidence that Hitler invented the sex doll, and claims that he did appear to be an urban legend.

**Source URL:** N/A

**Matched Message:**
> I heard that hitler invented the inflatable sex doll

**Match Metadata:**
- Dataset Item ID: 8f3c5c26-505c-4335-a9c6-55d782e3f807
- Similarity Score: 0.7639
- Dataset Tags: snopes, fact-check, misinformation""",
        "requested_by": "system-factcheck",
        "discord_message_id": "1436038555091865653",
        "discord_channel_id": "1423068966670176410",
        "discord_author_id": "696877497287049258",
        "discord_timestamp": "2025-11-06T17:04:31.840Z",
        "metadata": {
            "dataset_item_id": "8f3c5c26-505c-4335-a9c6-55d782e3f807",
            "similarity_score": 0.7639,
            "dataset_name": "snopes",
            "dataset_tags": ["snopes", "fact-check", "misinformation"],
        },
    }

    # Get API key from environment or use test key
    api_key = "opk_R1LT1prP_gqWOrI0c4xwt-1D5DbfU6hOzn5kvvH6h6cRzzzKJO8tsg"

    base_url = "http://localhost:8000"

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            print(f"Sending request to {base_url}/api/v1/requests")
            print(f"Request ID: {request_payload['request_id']}")
            print(
                f"Tweet ID: {request_payload['tweet_id']} (type: {type(request_payload['tweet_id']).__name__})"
            )
            print()

            response = await client.post(
                f"{base_url}/api/v1/requests",
                json=request_payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )

            print(f"Status Code: {response.status_code}")
            print(f"Response Headers: {dict(response.headers)}")
            print()

            if response.status_code == 200 or response.status_code == 201:
                print("✅ SUCCESS!")
                response_data = response.json()
                print(
                    f"Response tweet_id: {response_data.get('tweet_id')} (type: {type(response_data.get('tweet_id')).__name__})"
                )
                print(f"Response note_id: {response_data.get('note_id')}")
                print(json.dumps(response_data, indent=2))
                return True
            else:
                print("❌ FAILED!")
                print(f"Response: {response.text}")

                # If 409, try to list requests to see if it was created
                if response.status_code == 409:
                    print("\nChecking if request exists...")
                    list_response = await client.get(
                        f"{base_url}/api/v1/requests",
                        headers={"Authorization": f"Bearer {api_key}"},
                    )
                    if list_response.status_code == 200:
                        requests = list_response.json().get("requests", [])
                        matching = [
                            r
                            for r in requests
                            if r["request_id"] == request_payload["request_id"]
                        ]
                        if matching:
                            print(
                                f"Found existing request: {json.dumps(matching[0], indent=2)}"
                            )

                return False

        except Exception as e:
            print(f"❌ EXCEPTION: {e}")
            import traceback

            traceback.print_exc()
            return False


if __name__ == "__main__":
    success = asyncio.run(test_request_creation())
    sys.exit(0 if success else 1)
