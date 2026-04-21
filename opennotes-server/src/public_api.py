from dataclasses import dataclass, field

from fastapi import APIRouter

from src.config import settings
from src.moderation_actions.router import router as moderation_actions_jsonapi_router
from src.notes.notes_jsonapi_router import router as notes_jsonapi_router
from src.notes.ratings_jsonapi_router import router as ratings_jsonapi_router
from src.notes.requests_jsonapi_router import router as requests_jsonapi_router
from src.users.communities_jsonapi_router import router as communities_jsonapi_router
from src.users.profiles_jsonapi_router import router as profiles_jsonapi_router

API_PUBLIC_V1_PREFIX: str = settings.API_PUBLIC_V1_PREFIX


@dataclass(frozen=True)
class PublicRouterSpec:
    """Describes how a router should be mounted on the public API surface.

    path_allowlist is None = every route on the router is public.
    path_allowlist is a set = only routes whose .path is in the set are public.
    method_allowlist is None = every method on matched paths is public.
    method_allowlist is a set = only routes with at least one matching method
    are public.
    Use an allowlist when a router mixes adapter-contract routes with self-service
    or admin routes that must stay internal (e.g., profiles mixes /user-profiles/lookup
    with /profiles/me and /profiles/{id}/opennotes-admin).
    """

    router: APIRouter
    path_allowlist: frozenset[str] | None = field(default=None)
    method_allowlist: frozenset[str] | None = field(default=None)


PUBLIC_ADAPTER_ROUTERS: list[PublicRouterSpec] = [
    PublicRouterSpec(router=notes_jsonapi_router),
    PublicRouterSpec(router=ratings_jsonapi_router),
    PublicRouterSpec(
        router=profiles_jsonapi_router,
        path_allowlist=frozenset({"/user-profiles/lookup"}),
    ),
    PublicRouterSpec(router=communities_jsonapi_router),
    PublicRouterSpec(router=requests_jsonapi_router),
    PublicRouterSpec(
        router=moderation_actions_jsonapi_router,
        path_allowlist=frozenset({"/moderation-actions", "/moderation-actions/{action_id}"}),
        method_allowlist=frozenset({"GET"}),
    ),
]
