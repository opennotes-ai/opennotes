from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...types import Response


def _get_kwargs() -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/profile/auth/revoke",
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | None:
    if response.status_code == 204:
        return None

    if response.status_code == 401:
        return None

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Any]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
) -> Response[Any]:
    """Revoke Profile Token

     Revoke the current profile access token.

    This endpoint:
    1. Extracts the token from the Authorization header
    2. Adds the token's JTI to the Redis revocation blacklist
    3. The token will be rejected on future verification attempts

    Use this endpoint to invalidate the current access token after logout
    or when a token may be compromised.

    Note: Existing tokens without jti claim (created before this feature)
    cannot be revoked individually and will expire naturally.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any]
    """

    kwargs = _get_kwargs()

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
) -> Response[Any]:
    """Revoke Profile Token

     Revoke the current profile access token.

    This endpoint:
    1. Extracts the token from the Authorization header
    2. Adds the token's JTI to the Redis revocation blacklist
    3. The token will be rejected on future verification attempts

    Use this endpoint to invalidate the current access token after logout
    or when a token may be compromised.

    Note: Existing tokens without jti claim (created before this feature)
    cannot be revoked individually and will expire naturally.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any]
    """

    kwargs = _get_kwargs()

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)
