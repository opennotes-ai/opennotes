import importlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from src.moderation_actions.crud import list_moderation_actions
from src.moderation_actions.models import ActionState, ActionTier, ActionType, ReviewGroup
from src.moderation_actions.schemas import ModerationActionCreate, ModerationActionUpdate

router_mod = importlib.import_module("src.moderation_actions.router")


def _request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/"})


def _create_body(community_server_id: UUID) -> ModerationActionCreate:
    return ModerationActionCreate(
        request_id=uuid4(),
        community_server_id=community_server_id,
        action_type=ActionType.HIDE,
        action_tier=ActionTier.TIER_1_IMMEDIATE,
        review_group=ReviewGroup.COMMUNITY,
        classifier_evidence={"labels": ["spam"], "scores": [0.9]},
    )


def _forbidden() -> HTTPException:
    return HTTPException(status_code=403, detail="forbidden")


@pytest.mark.asyncio
async def test_create_checks_community_admin_for_non_service_user(monkeypatch):
    community_id = uuid4()
    verify_admin = AsyncMock(side_effect=_forbidden())
    monkeypatch.setattr(router_mod, "is_service_account", lambda user: False)
    monkeypatch.setattr(router_mod, "verify_community_admin_by_uuid", verify_admin)

    with pytest.raises(HTTPException):
        await router_mod.create_moderation_action_endpoint(
            body=_create_body(community_id),
            request=_request(),
            db=object(),
            current_user=object(),
        )

    verify_admin.assert_awaited_once()
    assert verify_admin.await_args.args[0] == community_id


@pytest.mark.asyncio
async def test_get_checks_community_membership_for_non_service_user(monkeypatch):
    community_id = uuid4()
    verify_member = AsyncMock(side_effect=_forbidden())
    monkeypatch.setattr(router_mod, "is_service_account", lambda user: False)
    monkeypatch.setattr(
        router_mod,
        "get_moderation_action",
        AsyncMock(return_value=SimpleNamespace(community_server_id=community_id)),
    )
    monkeypatch.setattr(router_mod, "verify_community_membership_by_uuid", verify_member)

    with pytest.raises(HTTPException):
        await router_mod.get_moderation_action_endpoint(
            action_id=uuid4(),
            request=_request(),
            db=object(),
            current_user=object(),
        )

    verify_member.assert_awaited_once()
    assert verify_member.await_args.args[0] == community_id


@pytest.mark.asyncio
async def test_patch_checks_community_admin_for_non_service_user(monkeypatch):
    community_id = uuid4()
    verify_admin = AsyncMock(side_effect=_forbidden())
    monkeypatch.setattr(router_mod, "is_service_account", lambda user: False)
    monkeypatch.setattr(
        router_mod,
        "get_moderation_action",
        AsyncMock(return_value=SimpleNamespace(community_server_id=community_id)),
    )
    monkeypatch.setattr(router_mod, "verify_community_admin_by_uuid", verify_admin)

    with pytest.raises(HTTPException):
        await router_mod.patch_moderation_action_endpoint(
            action_id=uuid4(),
            body=ModerationActionUpdate(action_state=ActionState.APPLIED),
            request=_request(),
            db=object(),
            current_user=object(),
        )

    verify_admin.assert_awaited_once()
    assert verify_admin.await_args.args[0] == community_id


@pytest.mark.asyncio
async def test_list_service_account_uses_unscoped_query(monkeypatch):
    list_actions = AsyncMock(return_value=[])
    monkeypatch.setattr(router_mod, "is_service_account", lambda user: True)
    monkeypatch.setattr(router_mod, "list_moderation_actions", list_actions)

    response = await router_mod.list_moderation_actions_endpoint(
        request=_request(),
        db=object(),
        current_user=object(),
        community_server_id=None,
        action_state=None,
        action_tier=None,
    )

    assert response.status_code == 200
    list_actions.assert_awaited_once()
    assert list_actions.await_args.kwargs["community_server_id"] is None
    assert list_actions.await_args.kwargs["community_server_id__in"] is None


@pytest.mark.asyncio
async def test_list_filter_checks_membership_for_non_service_user(monkeypatch):
    community_id = uuid4()
    verify_member = AsyncMock()
    list_actions = AsyncMock(return_value=[])
    monkeypatch.setattr(router_mod, "is_service_account", lambda user: False)
    monkeypatch.setattr(router_mod, "verify_community_membership_by_uuid", verify_member)
    monkeypatch.setattr(router_mod, "list_moderation_actions", list_actions)

    response = await router_mod.list_moderation_actions_endpoint(
        request=_request(),
        db=object(),
        current_user=object(),
        community_server_id=community_id,
        action_state=None,
        action_tier=None,
    )

    assert response.status_code == 200
    verify_member.assert_awaited_once()
    assert verify_member.await_args.args[0] == community_id
    assert list_actions.await_args.kwargs["community_server_id"] == community_id


@pytest.mark.asyncio
async def test_list_without_user_communities_returns_empty_response(monkeypatch):
    list_actions = AsyncMock()
    monkeypatch.setattr(router_mod, "is_service_account", lambda user: False)
    monkeypatch.setattr(
        router_mod,
        "get_user_community_ids",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(router_mod, "list_moderation_actions", list_actions)

    response = await router_mod.list_moderation_actions_endpoint(
        request=_request(),
        db=object(),
        current_user=object(),
        community_server_id=None,
        action_state=None,
        action_tier=None,
    )

    assert response.status_code == 200
    assert json.loads(response.body)["data"] == []
    list_actions.assert_not_called()


class _FakeScalars:
    def all(self):
        return []


class _FakeResult:
    def scalars(self):
        return _FakeScalars()


class _FakeDB:
    query = None

    async def execute(self, query):
        self.query = query
        return _FakeResult()


@pytest.mark.asyncio
async def test_list_moderation_actions_filters_by_allowed_community_ids():
    db = _FakeDB()

    result = await list_moderation_actions(
        db=db,
        community_server_id=None,
        community_server_id__in=[uuid4()],
        action_state=None,
        action_tier=None,
        limit=50,
        offset=0,
    )

    assert result == []
    assert db.query is not None
    assert "community_server_id IN" in str(db.query)
