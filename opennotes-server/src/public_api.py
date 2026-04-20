from fastapi import APIRouter

from src.config import settings
from src.moderation_actions.router import router as moderation_actions_jsonapi_router
from src.notes.notes_jsonapi_router import router as notes_jsonapi_router
from src.notes.ratings_jsonapi_router import router as ratings_jsonapi_router
from src.notes.requests_jsonapi_router import router as requests_jsonapi_router
from src.users.communities_jsonapi_router import router as communities_jsonapi_router
from src.users.profiles_jsonapi_router import router as profiles_jsonapi_router

API_PUBLIC_V1_PREFIX: str = settings.API_PUBLIC_V1_PREFIX

PUBLIC_ADAPTER_ROUTERS: list[APIRouter] = [
    notes_jsonapi_router,
    ratings_jsonapi_router,
    profiles_jsonapi_router,
    communities_jsonapi_router,
    requests_jsonapi_router,
    moderation_actions_jsonapi_router,
]
