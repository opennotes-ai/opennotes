from fastapi import APIRouter

from src.config import settings
from src.public_api import API_PUBLIC_V1_PREFIX, PUBLIC_ADAPTER_ROUTERS, PublicRouterSpec


def test_api_public_v1_prefix_constant():
    assert settings.API_PUBLIC_V1_PREFIX == "/api/public/v1"
    assert API_PUBLIC_V1_PREFIX == "/api/public/v1"


def test_public_adapter_routers_shape():
    assert len(PUBLIC_ADAPTER_ROUTERS) == 6
    for spec in PUBLIC_ADAPTER_ROUTERS:
        assert isinstance(spec, PublicRouterSpec)
        assert isinstance(spec.router, APIRouter)


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
    actual = {id(spec.router) for spec in PUBLIC_ADAPTER_ROUTERS}
    assert expected == actual


def test_profiles_router_has_path_allowlist():
    from src.users.profiles_jsonapi_router import router as profiles_router

    profiles_spec = next(spec for spec in PUBLIC_ADAPTER_ROUTERS if spec.router is profiles_router)
    # Only /user-profiles/lookup is public; /profiles/me and
    # /profiles/{id}/opennotes-admin must stay on /api/v2 only.
    assert profiles_spec.path_allowlist == frozenset({"/user-profiles/lookup"})


def test_moderation_actions_router_has_read_only_path_allowlist():
    from src.moderation_actions.router import router as moderation_actions_router

    moderation_actions_spec = next(
        spec for spec in PUBLIC_ADAPTER_ROUTERS if spec.router is moderation_actions_router
    )
    # Public adapters may list/fetch moderation actions, but create/update stays
    # on the legacy/internal mount where community-admin authority is enforced.
    assert moderation_actions_spec.path_allowlist == frozenset(
        {"/moderation-actions", "/moderation-actions/{action_id}"}
    )
    assert moderation_actions_spec.method_allowlist == frozenset({"GET"})


def test_unrestricted_routers_have_no_path_allowlist():
    from src.moderation_actions.router import router as moderation_actions_router
    from src.users.profiles_jsonapi_router import router as profiles_router

    for spec in PUBLIC_ADAPTER_ROUTERS:
        if spec.router is profiles_router or spec.router is moderation_actions_router:
            continue
        assert spec.path_allowlist is None, (
            f"Unexpected path_allowlist on {spec.router}; only profiles and "
            "moderation-actions are expected to need allowlisting right now."
        )
