from uuid import UUID

import uuid_utils
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

UID_COOKIE_NAME = "vibecheck_uid"
UID_COOKIE_MAX_AGE = 60 * 60 * 24 * 365 * 2


class UidCookieMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        raw = request.cookies.get(UID_COOKIE_NAME)
        uid: UUID | None = None
        if raw is not None:
            try:
                uid = UUID(raw)
            except ValueError:
                uid = None

        if uid is None:
            fresh = uuid_utils.uuid7()
            uid = UUID(str(fresh))
            request.state.uid = uid
            request.state.uid_to_set = uid
        else:
            request.state.uid = uid
            request.state.uid_to_set = None

        response = await call_next(request)
        if getattr(request.state, "uid_to_set", None) is not None:
            response.set_cookie(
                key=UID_COOKIE_NAME,
                value=str(request.state.uid_to_set),
                max_age=UID_COOKIE_MAX_AGE,
                httponly=True,
                secure=True,
                samesite="lax",
            )
        return response


def get_uid(request: Request) -> UUID:
    return request.state.uid
