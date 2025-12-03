"""Tests for src/notes/loaders.py - composable SQLAlchemy loader options."""

import pytest
from sqlalchemy.orm import Load

from src.llm_config.models import CommunityServer  # noqa: F401
from src.notes.message_archive_models import MessageArchive  # noqa: F401
from src.notes.models import Note, Rating, Request  # noqa: F401
from src.users.profile_models import UserProfile  # noqa: F401


@pytest.fixture(autouse=True)
def setup_database():
    """Override autouse database fixture - unit tests don't need database."""
    return


@pytest.fixture(autouse=True)
def mock_external_services():
    """Override autouse mock fixture - unit tests don't need external services."""
    return


class TestLoadersModule:
    """Test the loaders module exports and structure."""

    def test_module_exports_expected_functions(self):
        """Verify the loaders module exports all expected loader functions."""
        from src.notes import loaders

        assert hasattr(loaders, "ratings")
        assert hasattr(loaders, "request")
        assert hasattr(loaders, "full")
        assert hasattr(loaders, "admin")
        assert hasattr(loaders, "author")

        assert callable(loaders.ratings)
        assert callable(loaders.request)
        assert callable(loaders.full)
        assert callable(loaders.admin)
        assert callable(loaders.author)


class TestRatingsLoader:
    """Test the ratings() loader function."""

    def test_ratings_returns_tuple(self):
        """ratings() should return a tuple."""
        from src.notes.loaders import ratings

        result = ratings()
        assert isinstance(result, tuple)

    def test_ratings_returns_single_option(self):
        """ratings() should return exactly one loader option."""
        from src.notes.loaders import ratings

        result = ratings()
        assert len(result) == 1

    def test_ratings_option_is_load_instance(self):
        """ratings() should return a SQLAlchemy Load instance."""
        from src.notes.loaders import ratings

        result = ratings()
        assert isinstance(result[0], Load)


class TestRequestLoader:
    """Test the request() loader function."""

    def test_request_returns_tuple(self):
        """request() should return a tuple."""
        from src.notes.loaders import request

        result = request()
        assert isinstance(result, tuple)

    def test_request_returns_single_option(self):
        """request() should return exactly one loader option (chained selectinload)."""
        from src.notes.loaders import request

        result = request()
        assert len(result) == 1

    def test_request_option_is_load_instance(self):
        """request() should return a SQLAlchemy Load instance."""
        from src.notes.loaders import request

        result = request()
        assert isinstance(result[0], Load)


class TestFullLoader:
    """Test the full() loader function."""

    def test_full_returns_tuple(self):
        """full() should return a tuple."""
        from src.notes.loaders import full

        result = full()
        assert isinstance(result, tuple)

    def test_full_composes_ratings_and_request(self):
        """full() should compose ratings() and request() loaders."""
        from src.notes.loaders import full, ratings, request

        full_result = full()
        ratings_result = ratings()
        request_result = request()

        expected_length = len(ratings_result) + len(request_result)
        assert len(full_result) == expected_length

    def test_full_all_options_are_load_instances(self):
        """full() should return all Load instances."""
        from src.notes.loaders import full

        result = full()
        for option in result:
            assert isinstance(option, Load)


class TestAdminLoader:
    """Test the admin() loader function."""

    def test_admin_returns_tuple(self):
        """admin() should return a tuple."""
        from src.notes.loaders import admin

        result = admin()
        assert isinstance(result, tuple)

    def test_admin_extends_full(self):
        """admin() should include all of full() plus additional options."""
        from src.notes.loaders import admin, full

        admin_result = admin()
        full_result = full()

        assert len(admin_result) > len(full_result)

    def test_admin_adds_one_option_to_full(self):
        """admin() should add exactly one option beyond full()."""
        from src.notes.loaders import admin, full

        admin_result = admin()
        full_result = full()

        assert len(admin_result) == len(full_result) + 1

    def test_admin_all_options_are_load_instances(self):
        """admin() should return all Load instances."""
        from src.notes.loaders import admin

        result = admin()
        for option in result:
            assert isinstance(option, Load)


class TestAuthorLoader:
    """Test the author() loader function."""

    def test_author_returns_tuple(self):
        """author() should return a tuple."""
        from src.notes.loaders import author

        result = author()
        assert isinstance(result, tuple)

    def test_author_returns_single_option(self):
        """author() should return exactly one loader option."""
        from src.notes.loaders import author

        result = author()
        assert len(result) == 1

    def test_author_option_is_load_instance(self):
        """author() should return a SQLAlchemy Load instance."""
        from src.notes.loaders import author

        result = author()
        assert isinstance(result[0], Load)


class TestLoaderUnpackingWithSelect:
    """Test that loaders can be unpacked into select().options()."""

    def test_ratings_can_be_unpacked(self):
        """ratings() tuple can be unpacked with * into options()."""
        from sqlalchemy import select

        from src.notes.loaders import ratings

        stmt = select(Note).options(*ratings())
        assert stmt is not None

    def test_request_can_be_unpacked(self):
        """request() tuple can be unpacked with * into options()."""
        from sqlalchemy import select

        from src.notes.loaders import request

        stmt = select(Note).options(*request())
        assert stmt is not None

    def test_full_can_be_unpacked(self):
        """full() tuple can be unpacked with * into options()."""
        from sqlalchemy import select

        from src.notes.loaders import full

        stmt = select(Note).options(*full())
        assert stmt is not None

    def test_admin_can_be_unpacked(self):
        """admin() tuple can be unpacked with * into options()."""
        from sqlalchemy import select

        from src.notes.loaders import admin

        stmt = select(Note).options(*admin())
        assert stmt is not None

    def test_author_can_be_unpacked(self):
        """author() tuple can be unpacked with * into options()."""
        from sqlalchemy import select

        from src.notes.loaders import author

        stmt = select(Note).options(*author())
        assert stmt is not None

    def test_loaders_can_be_combined(self):
        """Multiple loaders can be combined via tuple unpacking."""
        from sqlalchemy import select

        from src.notes.loaders import author, full

        stmt = select(Note).options(*full(), *author())
        assert stmt is not None
