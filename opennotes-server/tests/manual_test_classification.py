#!/usr/bin/env python3
"""
Manual test script to verify NOT_MISLEADING notes appear in queue.
Run this with: uv run python tests/manual_test_classification.py
"""

import asyncio
from datetime import UTC, datetime

import httpx


async def main():  # noqa: PLR0911 (too many returns - acceptable for test script)
    base_url = "http://localhost:8000"

    # Register a test user
    user_data = {
        "username": f"testuser_{int(datetime.now(UTC).timestamp())}",
        "email": f"test_{int(datetime.now(UTC).timestamp())}@example.com",
        "password": "TestPassword123!",
        "full_name": "Test User",
    }

    print("1. Registering test user...")
    async with httpx.AsyncClient() as client:
        register_response = await client.post(f"{base_url}/api/v1/auth/register", json=user_data)
        if register_response.status_code != 201:
            print(f"❌ Registration failed: {register_response.text}")
            return

        user = register_response.json()
        print(f"✅ User registered: {user['username']}")

        # Login to get token
        print("\n2. Logging in...")
        login_response = await client.post(
            f"{base_url}/api/v1/auth/login",
            data={
                "username": user_data["username"],
                "password": user_data["password"],
            },
        )

        if login_response.status_code != 200:
            print(f"❌ Login failed: {login_response.text}")
            return

        token_data = login_response.json()
        token = token_data["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("✅ Logged in successfully")

        # Create a NOT_MISLEADING note
        print("\n3. Creating NOT_MISLEADING note...")
        note_data = {
            "classification": "NOT_MISLEADING",
            "summary": f"This post is accurate and helpful - manual test {int(datetime.now(UTC).timestamp() * 1000)}",
            "author_participant_id": f"discord_user_{user['id']}",
        }

        create_response = await client.post(
            f"{base_url}/api/v1/notes", json=note_data, headers=headers
        )

        if create_response.status_code != 201:
            print(f"❌ Note creation failed: {create_response.text}")
            return

        created_note = create_response.json()
        print("✅ Note created:")
        print(f"   - Note ID: {created_note['id']}")
        print(f"   - Classification: {created_note['classification']}")
        print(f"   - Status: {created_note['status']}")

        # Verify note appears in NEEDS_MORE_RATINGS queue
        print("\n4. Checking note appears in NEEDS_MORE_RATINGS queue...")
        list_response = await client.get(
            f"{base_url}/api/v1/notes?status_filter=NEEDS_MORE_RATINGS&size=100", headers=headers
        )

        if list_response.status_code != 200:
            print(f"❌ List notes failed: {list_response.text}")
            return

        notes_data = list_response.json()
        note_ids = [note["id"] for note in notes_data["notes"]]

        if created_note["id"] in note_ids:
            print("✅ NOT_MISLEADING note appears in NEEDS_MORE_RATINGS queue")
            print(f"   - Total notes in queue: {notes_data['total']}")
        else:
            print("❌ NOT_MISLEADING note DOES NOT appear in queue!")
            print(f"   - Expected note id: {created_note['id']}")
            print(f"   - Found note ids: {note_ids[:10]}... (showing first 10)")
            return

        # Create a MISINFORMED note for comparison
        print("\n5. Creating MISINFORMED_OR_POTENTIALLY_MISLEADING note...")
        misinformed_note_data = {
            "classification": "MISINFORMED_OR_POTENTIALLY_MISLEADING",
            "summary": f"This post contains misinformation - manual test {int(datetime.now(UTC).timestamp() * 1000) + 1}",
            "author_participant_id": f"discord_user_{user['id']}",
        }

        create_response2 = await client.post(
            f"{base_url}/api/v1/notes", json=misinformed_note_data, headers=headers
        )

        if create_response2.status_code != 201:
            print(f"❌ Note creation failed: {create_response2.text}")
            return

        created_note2 = create_response2.json()
        print("✅ Note created:")
        print(f"   - Note ID: {created_note2['id']}")
        print(f"   - Classification: {created_note2['classification']}")
        print(f"   - Status: {created_note2['status']}")

        # Verify both notes appear together
        print("\n6. Verifying both classifications appear in queue...")
        list_response2 = await client.get(
            f"{base_url}/api/v1/notes?status_filter=NEEDS_MORE_RATINGS&size=100", headers=headers
        )

        notes_data2 = list_response2.json()
        note_ids2 = [note["id"] for note in notes_data2["notes"]]

        not_misleading_present = created_note["id"] in note_ids2
        misinformed_present = created_note2["id"] in note_ids2

        if not_misleading_present and misinformed_present:
            print("✅ Both classifications appear in queue")
            print("   - NOT_MISLEADING note: Present")
            print("   - MISINFORMED note: Present")
            print(f"   - Total notes: {notes_data2['total']}")
        else:
            print("❌ One or both notes missing from queue!")
            print(f"   - NOT_MISLEADING present: {not_misleading_present}")
            print(f"   - MISINFORMED present: {misinformed_present}")
            return

        print("\n" + "=" * 60)
        print("✅ All tests passed! NOT_MISLEADING notes work correctly.")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
