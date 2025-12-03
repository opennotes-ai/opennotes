import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.auth.password import get_password_hash
from src.main import app
from src.users.audit_helper import create_audit_log
from src.users.models import AuditLog, User


@pytest.mark.asyncio
async def test_register_creates_audit_log(db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "username": "newuser",
                "email": "newuser@example.com",
                "password": "SecurePass123!",
                "full_name": "New User",
            },
        )

    assert response.status_code == 201
    user_data = response.json()

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.user_id == user_data["id"], AuditLog.action == "CREATE_USER"
        )
    )
    audit_log = result.scalar_one_or_none()

    assert audit_log is not None
    assert audit_log.action == "CREATE_USER"
    assert audit_log.resource == "user"
    assert str(audit_log.user_id) == user_data["id"]


@pytest.mark.asyncio
async def test_login_success_creates_audit_log(db):
    user = User(
        username="loginuser",
        email="loginuser@example.com",
        hashed_password=get_password_hash("SecurePass123!"),
        full_name="Login User",
        role="user",
        is_active=True,
        is_superuser=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": "loginuser", "password": "SecurePass123!"},
        )

    assert response.status_code == 200

    result = await db.execute(
        select(AuditLog).where(AuditLog.user_id == user.id, AuditLog.action == "LOGIN_SUCCESS")
    )
    audit_log = result.scalar_one_or_none()

    assert audit_log is not None
    assert audit_log.action == "LOGIN_SUCCESS"
    assert audit_log.resource == "authentication"
    assert audit_log.user_id == user.id


@pytest.mark.asyncio
async def test_login_failure_wrong_password_creates_audit_log(db):
    user = User(
        username="failuser",
        email="failuser@example.com",
        hashed_password=get_password_hash("SecurePass123!"),
        full_name="Fail User",
        role="user",
        is_active=True,
        is_superuser=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": "failuser", "password": "WrongPassword123!"},
        )

    assert response.status_code == 401

    result = await db.execute(
        select(AuditLog).where(AuditLog.user_id == user.id, AuditLog.action == "LOGIN_FAILED")
    )
    audit_log = result.scalar_one_or_none()

    assert audit_log is not None
    assert audit_log.action == "LOGIN_FAILED"
    assert audit_log.resource == "authentication"
    assert audit_log.user_id == user.id
    assert "invalid_password" in audit_log.details


@pytest.mark.asyncio
async def test_login_failure_user_not_found_creates_audit_log(db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": "nonexistent", "password": "SecurePass123!"},
        )

    assert response.status_code == 401

    result = await db.execute(
        select(AuditLog).where(AuditLog.user_id.is_(None), AuditLog.action == "LOGIN_FAILED")
    )
    audit_log = result.scalar_one_or_none()

    assert audit_log is not None
    assert audit_log.action == "LOGIN_FAILED"
    assert audit_log.resource == "authentication"
    assert audit_log.user_id is None
    assert "user_not_found" in audit_log.details


@pytest.mark.asyncio
async def test_token_refresh_success_creates_audit_log(db):
    user = User(
        username="refreshuser",
        email="refreshuser@example.com",
        hashed_password=get_password_hash("SecurePass123!"),
        full_name="Refresh User",
        role="user",
        is_active=True,
        is_superuser=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login_response = await client.post(
            "/api/v1/auth/login",
            data={"username": "refreshuser", "password": "SecurePass123!"},
        )
        assert login_response.status_code == 200
        tokens = login_response.json()
        refresh_token = tokens["refresh_token"]

        refresh_response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )

    assert refresh_response.status_code == 200

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.user_id == user.id, AuditLog.action == "TOKEN_REFRESH_SUCCESS"
        )
    )
    audit_log = result.scalar_one_or_none()

    assert audit_log is not None
    assert audit_log.action == "TOKEN_REFRESH_SUCCESS"
    assert audit_log.resource == "authentication"
    assert audit_log.user_id == user.id


@pytest.mark.asyncio
async def test_logout_creates_audit_log(db, auth_headers_for_user):
    user_id = auth_headers_for_user["user_id"]

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login_response = await client.post(
            "/api/v1/auth/login",
            data={"username": user.username, "password": "TestPassword123!"},
        )
        assert login_response.status_code == 200
        tokens = login_response.json()
        refresh_token = tokens["refresh_token"]

        logout_response = await client.post(
            f"/api/v1/auth/logout?refresh_token={refresh_token}",
            headers={
                "Authorization": f"Bearer {tokens['access_token']}",
            },
        )

    assert logout_response.status_code == 204

    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.user_id == user.id, AuditLog.action == "LOGOUT_SUCCESS")
        .order_by(AuditLog.created_at.desc())
    )
    audit_log = result.scalar_one_or_none()

    assert audit_log is not None
    assert audit_log.action == "LOGOUT_SUCCESS"
    assert audit_log.resource == "authentication"
    assert audit_log.user_id == user.id


@pytest.mark.asyncio
async def test_get_login_history_endpoint(auth_headers_for_user):
    headers = {
        "Authorization": f"Bearer {auth_headers_for_user['access_token']}",
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/users/me/login-history", headers=headers)

    assert response.status_code == 200
    audit_logs = response.json()

    assert isinstance(audit_logs, list)
    if len(audit_logs) > 0:
        log = audit_logs[0]
        assert "id" in log
        assert "user_id" in log
        assert "action" in log
        assert "resource" in log
        assert "created_at" in log
        assert log["action"] in [
            "LOGIN_SUCCESS",
            "LOGIN_FAILED",
            "TOKEN_REFRESH_SUCCESS",
            "TOKEN_REFRESH_FAILED",
            "LOGOUT_SUCCESS",
            "LOGOUT_FAILED",
            "LOGOUT_ALL_SUCCESS",
            "CREATE_USER",
        ]


@pytest.mark.asyncio
async def test_get_login_history_pagination(auth_headers_for_user):
    headers = {
        "Authorization": f"Bearer {auth_headers_for_user['access_token']}",
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/users/me/login-history?limit=5&offset=0", headers=headers
        )

    assert response.status_code == 200
    audit_logs = response.json()

    assert isinstance(audit_logs, list)
    assert len(audit_logs) <= 5


@pytest.mark.asyncio
async def test_get_login_history_only_returns_own_logs(db, auth_headers_for_user):
    other_user = User(
        username="otheruser",
        email="otheruser@example.com",
        hashed_password=get_password_hash("SecurePass123!"),
        full_name="Other User",
        role="user",
        is_active=True,
        is_superuser=False,
    )
    db.add(other_user)
    await db.commit()
    await db.refresh(other_user)

    await create_audit_log(
        db=db,
        user_id=other_user.id,
        action="LOGIN_SUCCESS",
        resource="authentication",
        resource_id=str(other_user.id),
        details={"username": other_user.username},
        ip_address="192.168.1.100",
        user_agent="test-agent",
    )
    await db.commit()

    user_id = auth_headers_for_user["user_id"]
    headers = {
        "Authorization": f"Bearer {auth_headers_for_user['access_token']}",
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/users/me/login-history", headers=headers)

    assert response.status_code == 200
    audit_logs = response.json()

    for log in audit_logs:
        assert log["user_id"] == user_id
        assert log["user_id"] != other_user.id
