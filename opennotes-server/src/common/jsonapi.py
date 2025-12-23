"""JSON:API 1.1 common infrastructure for reusable components.

This module provides base classes and helper functions for building JSON:API
compliant endpoints across the application. It implements the JSON:API 1.1
specification with select 1.2 features: https://jsonapi.org/format/

Components:
- Response schemas: JSONAPIResource, JSONAPIListResponse, JSONAPISingleResponse
- Meta schemas: JSONAPIMeta, JSONAPILinks
- Error schemas: JSONAPIError, JSONAPIErrorResponse, JSONAPIErrorSource
- Helper functions: create_pagination_links, create_error_response, model_to_resource
- Content type constant: JSONAPI_CONTENT_TYPE

Usage:
    from src.common.jsonapi import (
        JSONAPIResource,
        JSONAPIListResponse,
        create_pagination_links,
        create_error_response,
        model_to_resource,
        JSONAPI_CONTENT_TYPE,
    )

    resource = model_to_resource(model=note, resource_type="notes")
    links = create_pagination_links(base_url, page=1, size=20, total=100)
"""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")

JSONAPI_CONTENT_TYPE = "application/vnd.api+json"


class JSONAPIVersion(BaseModel):
    """JSON:API version information."""

    version: str = "1.1"


class JSONAPIMeta(BaseModel):
    """JSON:API meta object for pagination and collection metadata."""

    count: int | None = None
    page: int | None = None
    pages: int | None = None
    limit: int | None = None
    offset: int | None = None


class JSONAPILinks(BaseModel):
    """JSON:API links object for pagination and resource links.

    Uses field aliases for 'self' and 'next' which are Python reserved words.
    Always use by_alias=True when serializing.
    Includes JSON:API 1.1 'describedby' link for API documentation.
    """

    model_config = ConfigDict(extra="allow", json_schema_mode="serialization")

    self_: str | None = Field(default=None, serialization_alias="self")
    first: str | None = None
    last: str | None = None
    prev: str | None = None
    next_: str | None = Field(default=None, serialization_alias="next")
    describedby: str | None = None


class JSONAPIResourceIdentifier(BaseModel):
    """JSON:API resource identifier object (type + id only)."""

    type: str
    id: str


class JSONAPIResource(BaseModel):
    """JSON:API resource object with attributes.

    A resource object represents a single resource in the JSON:API response.
    It contains the resource type, unique identifier, and attributes.
    Optionally includes relationships and links.
    """

    model_config = ConfigDict(from_attributes=True)

    type: str
    id: str
    attributes: dict[str, Any]
    relationships: dict[str, Any] | None = None
    links: dict[str, str] | None = None


class JSONAPIError(BaseModel):
    """JSON:API error object.

    Represents a single error in the JSON:API error format.
    Includes JSON:API 1.2 source field for error location information.
    """

    status: str
    title: str
    detail: str | None = None
    source: "JSONAPIErrorSource | None" = None


class JSONAPIErrorSource(BaseModel):
    """JSON:API error source object for indicating error location.

    Supports JSON:API 1.2 draft source fields including header field.
    """

    pointer: str | None = None
    parameter: str | None = None
    header: str | None = None


class JSONAPIErrorResponse(BaseModel):
    """JSON:API error response containing one or more errors."""

    model_config = ConfigDict(from_attributes=True)

    errors: list[JSONAPIError]
    jsonapi: dict[str, str] = {"version": "1.1"}


class JSONAPIListResponse(BaseModel, Generic[T]):
    """JSON:API response for a collection of resources.

    Generic type T should be a JSONAPIResource or compatible type.
    """

    model_config = ConfigDict(from_attributes=True)

    data: list[T]
    jsonapi: dict[str, str] = {"version": "1.1"}
    links: JSONAPILinks | None = None
    meta: JSONAPIMeta | None = None


class JSONAPISingleResponse(BaseModel, Generic[T]):
    """JSON:API response for a single resource.

    Generic type T should be a JSONAPIResource or compatible type.
    """

    model_config = ConfigDict(from_attributes=True)

    data: T
    jsonapi: dict[str, str] = {"version": "1.1"}
    links: dict[str, str] | None = None


def create_pagination_links(
    base_url: str,
    page: int,
    size: int,
    total: int,
    query_params: dict[str, str] | None = None,
) -> JSONAPILinks:
    """Generate JSON:API pagination links.

    Creates links for navigating paginated collections following the JSON:API
    specification. Includes self, first, last, prev, and next links as appropriate.

    Args:
        base_url: The base URL for the endpoint (without query parameters)
        page: Current page number (1-indexed)
        size: Number of items per page
        total: Total number of items in the collection
        query_params: Additional query parameters to preserve in links

    Returns:
        JSONAPILinks with populated pagination URLs

    Example:
        links = create_pagination_links(
            base_url="http://api.example.com/notes",
            page=2,
            size=20,
            total=100,
            query_params={"filter[status]": "NEEDS_MORE_RATINGS"}
        )
    """
    if query_params is None:
        query_params = {}

    total_pages = (total + size - 1) // size if size > 0 and total > 0 else 0

    def build_url(page_num: int) -> str:
        params = dict(query_params)
        params["page[number]"] = str(page_num)
        params["page[size]"] = str(size)
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{base_url}?{query}"

    return JSONAPILinks(
        self_=build_url(page),
        first=build_url(1) if total > 0 else None,
        last=build_url(total_pages) if total > 0 else None,
        prev=build_url(page - 1) if page > 1 else None,
        next_=build_url(page + 1) if page < total_pages else None,
    )


def create_error_response(
    status_code: int,
    title: str,
    detail: str | None = None,
    source_parameter: str | None = None,
    source_pointer: str | None = None,
    source_header: str | None = None,
) -> JSONAPIErrorResponse:
    """Create a JSON:API formatted error response.

    Creates a properly formatted error response following the JSON:API 1.1
    specification with optional source information (JSON:API 1.2 draft).
    Use this with FastAPI's JSONResponse for consistent error handling.

    Args:
        status_code: HTTP status code (e.g., 404, 422, 500)
        title: Short human-readable summary of the error
        detail: Optional detailed explanation of the error
        source_parameter: Optional query parameter that caused the error
        source_pointer: Optional JSON pointer to error location in request body
        source_header: Optional header name that caused the error

    Returns:
        JSONAPIErrorResponse ready for serialization

    Example:
        error = create_error_response(
            status_code=404,
            title="Not Found",
            detail="Note abc123 not found"
        )
        return JSONResponse(
            status_code=404,
            content=error.model_dump(by_alias=True),
            media_type=JSONAPI_CONTENT_TYPE
        )

        error = create_error_response(
            status_code=422,
            title="Validation Error",
            detail="Invalid status value",
            source_parameter="filter[status]"
        )
    """
    source = None
    if source_parameter or source_pointer or source_header:
        source = JSONAPIErrorSource(
            parameter=source_parameter,
            pointer=source_pointer,
            header=source_header,
        )

    return JSONAPIErrorResponse(
        errors=[
            JSONAPIError(
                status=str(status_code),
                title=title,
                detail=detail,
                source=source,
            )
        ]
    )


def model_to_resource(
    model: Any,
    resource_type: str,
    id_field: str = "id",
    exclude_fields: set[str] | None = None,
) -> JSONAPIResource:
    """Convert a model (SQLAlchemy or Pydantic) to a JSON:API resource object.

    Extracts attributes from the model and creates a properly formatted
    JSON:API resource object. The id field is automatically excluded from
    attributes and converted to a string.

    Args:
        model: The model instance to convert (SQLAlchemy model, Pydantic model,
               or any object with attributes)
        resource_type: The JSON:API type string (e.g., "notes", "users")
        id_field: The attribute name to use as the resource id (default: "id")
        exclude_fields: Set of field names to exclude from attributes

    Returns:
        JSONAPIResource with type, id, and attributes

    Example:
        note = await db.get(Note, note_id)
        resource = model_to_resource(
            model=note,
            resource_type="notes",
            exclude_fields={"internal_score", "raw_data"}
        )
    """
    if exclude_fields is None:
        exclude_fields = set()

    exclude_fields = exclude_fields.copy()
    exclude_fields.add(id_field)

    model_id = getattr(model, id_field)
    id_str = str(model_id)

    if hasattr(model, "model_dump"):
        attrs = model.model_dump()
    elif hasattr(model, "__dict__") and model.__dict__:
        attrs = model.__dict__.copy()
        attrs.pop("_sa_instance_state", None)
    else:
        attrs = {}
        for attr_name in dir(model):
            if attr_name.startswith("_"):
                continue
            if callable(getattr(type(model), attr_name, None)):
                continue
            try:
                attrs[attr_name] = getattr(model, attr_name)
            except AttributeError:
                pass

    attributes = {k: v for k, v in attrs.items() if k not in exclude_fields}

    return JSONAPIResource(
        type=resource_type,
        id=id_str,
        attributes=attributes,
    )
