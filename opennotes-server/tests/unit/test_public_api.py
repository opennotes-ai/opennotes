from fastapi import APIRouter

from src.config import settings
from src.public_api import API_PUBLIC_V1_PREFIX, PUBLIC_ADAPTER_ROUTERS


def test_api_public_v1_prefix_constant():
    assert settings.API_PUBLIC_V1_PREFIX == "/api/public/v1"
    assert API_PUBLIC_V1_PREFIX == "/api/public/v1"


def test_public_adapter_routers_shape():
    assert len(PUBLIC_ADAPTER_ROUTERS) == 6
    for router in PUBLIC_ADAPTER_ROUTERS:
        assert isinstance(router, APIRouter)


def test_public_adapter_routers_identity():
    from src.moderation_actions.router import router as moderation_actions_router
    from src.notes.notes_jsonapi_router import router as notes_router
    from src.notes.ratings_jsonapi_router import router as ratings_router
    from src.notes.requests_jsonapi_router import router as requests_router
    from src.users.communities_jsonapi_router import router as communities_router
    from src.users.profiles_jsonapi_router import router as profiles_router

    expected = {
        id(notes_router),
        id(ratings_router),
        id(profiles_router),
        id(communities_router),
        id(requests_router),
        id(moderation_actions_router),
    }
    actual = {id(r) for r in PUBLIC_ADAPTER_ROUTERS}
    assert expected == actual
