"""Composable SQLAlchemy loader options for Note relationships.

This module provides reusable loader option functions that can be composed
to create different loading strategies for Note queries. Each function returns
a tuple of loader options that can be unpacked into select().options().

Example usage:
    from sqlalchemy import select
    from src.notes.loaders import full, author
    from src.notes.models import Note

    stmt = select(Note).options(*full(), *author())
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.orm import selectinload

from src.notes.models import Note, Rating, Request

if TYPE_CHECKING:
    from sqlalchemy.orm.strategy_options import _AbstractLoad


def ratings() -> tuple[_AbstractLoad, ...]:
    """Load note ratings.

    Returns:
        Tuple containing selectinload option for Note.ratings relationship.
    """
    return (selectinload(Note.ratings),)


def request() -> tuple[_AbstractLoad, ...]:
    """Load note request with message archive.

    Returns:
        Tuple containing chained selectinload option for Note.request
        and Request.message_archive relationships.
    """
    return (selectinload(Note.request).selectinload(Request.message_archive),)


def full() -> tuple[_AbstractLoad, ...]:
    """Standard loading for NoteResponse - composes ratings() + request().

    This is the default loader for most note queries that need to build
    a NoteResponse.

    Returns:
        Tuple containing all options from ratings() and request().
    """
    return (*ratings(), *request())


def admin() -> tuple[_AbstractLoad, ...]:
    """Extended loading including force_published_by_profile.

    Use this loader when admin-level note details are needed,
    including information about who force-published a note.

    Returns:
        Tuple containing all options from full() plus force_published_by_profile.
    """
    return (*full(), selectinload(Note.force_published_by_profile))


def author() -> tuple[_AbstractLoad, ...]:
    """Load note author profile.

    Returns:
        Tuple containing selectinload option for Note.author relationship.
    """
    return (selectinload(Note.author),)


def request_with_archive() -> tuple[_AbstractLoad, ...]:
    """Load Request with message archive (for direct Request queries).

    Use this when querying Request directly (not via Note.request).

    Returns:
        Tuple containing selectinload option for Request.message_archive relationship.
    """
    return (selectinload(Request.message_archive),)


def rating_with_note() -> tuple[_AbstractLoad, ...]:
    """Load Rating with associated note.

    Use this when querying Rating directly and need the note context.

    Returns:
        Tuple containing selectinload option for Rating.note relationship.
    """
    return (selectinload(Rating.note),)
