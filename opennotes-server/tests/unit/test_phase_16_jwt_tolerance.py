from unittest.mock import AsyncMock, patch

import pytest

from src.auth.auth import create_access_token, verify_token


@pytest.mark.asyncio
async def test_jwt_without_role_claim_accepted():
    token = create_access_token(
        data={"sub": "00000000-0000-0000-0000-000000000001", "username": "test"}
    )
    with patch("src.auth.auth.is_token_revoked_check", new=AsyncMock(return_value=False)):
        data = await verify_token(token)
    assert data is not None
    assert data.username == "test"
    assert data.role is None


@pytest.mark.asyncio
async def test_jwt_with_role_claim_still_accepted():
    token = create_access_token(
        data={
            "sub": "00000000-0000-0000-0000-000000000001",
            "username": "test",
            "role": "admin",
        }
    )
    with patch("src.auth.auth.is_token_revoked_check", new=AsyncMock(return_value=False)):
        data = await verify_token(token)
    assert data is not None
    assert data.username == "test"
    assert data.role == "admin"
