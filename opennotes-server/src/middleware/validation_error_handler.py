from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sanitary import Sanitizer

SENSITIVE_KEYS = frozenset(
    {
        "password",
        "current_password",
        "new_password",
        "hashed_password",
        "secret",
        "token",
        "api_key",
        "refresh_token",
    }
)

sanitizer = Sanitizer(keys=SENSITIVE_KEYS)

_REPLACEMENT = "********"


def _sanitize_loc(loc: tuple[str | int, ...] | list[str | int]) -> list[str | int]:
    return [
        _REPLACEMENT if isinstance(part, str) and part.lower() in SENSITIVE_KEYS else part
        for part in loc
    ]


async def sanitized_validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    sanitized_errors = []
    for error in exc.errors():
        sanitized_error: dict[str, object] = {
            "type": error.get("type", ""),
            "loc": _sanitize_loc(error.get("loc", ())),
            "msg": error.get("msg", ""),
        }
        sanitized_errors.append(sanitized_error)
    return JSONResponse(
        status_code=422,
        content={"detail": sanitized_errors},
    )
