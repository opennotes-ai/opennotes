from uuid import uuid4

import pytest

from src.auth.auth import create_access_token
from src.users.models import User


@pytest.fixture
async def admin_user(db):
    user = User(
        id=uuid4(),
        username="sim_admin_user",
        email="sim_admin@opennotes.local",
        hashed_password="hashed_password_placeholder",
        role="admin",
        is_active=True,
        is_superuser=True,
        is_service_account=False,
        discord_id=f"discord_sim_admin_{uuid4().hex[:8]}",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.fixture
async def admin_auth_headers(admin_user):
    token_data = {
        "sub": str(admin_user.id),
        "username": admin_user.username,
        "role": admin_user.role,
    }
    access_token = create_access_token(token_data)
    return {"Authorization": f"Bearer {access_token}"}
