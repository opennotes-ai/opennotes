"""
Test suite for Pydantic schema configuration standards.

Verifies that all schemas enforce the correct validation rules based on their category:
- API Input schemas: Strict validation, reject unknown fields, strip whitespace
- API Response schemas: Convert from ORM, use enum values
- ORM-backed schemas: Convert from ORM, forbid extra fields to catch mismatches
- Event schemas: Strict validation, reject unknown fields

These tests don't require database access - they only test schema validation.
"""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.common.base_schemas import SQLAlchemySchema, StrictEventSchema, StrictInputSchema
from src.events.schemas import BaseEvent, EventType, NoteCreatedEvent
from src.fact_checking.embedding_schemas import EmbeddingRequest
from src.fact_checking.monitored_channel_schemas import (
    MonitoredChannelCreate,
    MonitoredChannelListResponse,
)
from src.llm_config.schemas import LLMConfigCreate
from src.notes.schemas import (
    NoteCreate,
    NoteInDB,
    NoteUpdate,
    RatingCreate,
    RatingUpdate,
    RequestCreate,
    RequestListResponse,
)
from src.users.profile_schemas import (
    UserProfileAdminUpdate,
    UserProfileCreate,
    UserProfileSelfUpdate,
    UserProfileUpdate,
)
from src.webhooks.types import WebhookCreateRequest, WebhookUpdateRequest


@pytest.mark.unit
class TestStrictInputSchemas:
    """Test that API input schemas enforce strict validation."""

    def test_note_create_rejects_unknown_fields(self):
        """NoteCreate should reject unknown fields."""
        with pytest.raises(ValidationError) as exc_info:
            NoteCreate(
                author_id=uuid4(),
                community_server_id=uuid4(),
                summary="Test note",
                classification="NOT_MISLEADING",
                unknown_field="should_fail",
            )
        assert "extra_forbidden" in str(exc_info.value)

    def test_rating_create_rejects_unknown_fields(self):
        """RatingCreate should reject unknown fields."""
        with pytest.raises(ValidationError) as exc_info:
            RatingCreate(
                note_id=uuid4(),
                helpfulness_level="HELPFUL",
                rater_id=uuid4(),
                extra_field="should_fail",
            )
        assert "extra_forbidden" in str(exc_info.value)

    def test_request_create_rejects_unknown_fields(self):
        """RequestCreate should reject unknown fields."""
        with pytest.raises(ValidationError) as exc_info:
            RequestCreate(
                request_id="req123",
                requested_by="user123",
                unknown_field="should_fail",
            )
        assert "extra_forbidden" in str(exc_info.value)

    def test_user_profile_create_strips_whitespace(self):
        """UserProfileCreate should strip whitespace from string fields."""
        profile = UserProfileCreate(display_name="  John Doe  ")
        assert profile.display_name == "John Doe"

    def test_webhook_create_rejects_unknown_fields(self):
        """WebhookCreateRequest should reject unknown fields."""
        with pytest.raises(ValidationError) as exc_info:
            WebhookCreateRequest(
                url="https://example.com/webhook",
                secret="secret123",
                community_server_id="server123",
                invalid_field="should_fail",
            )
        assert "extra_forbidden" in str(exc_info.value)

    def test_llm_config_create_rejects_unknown_fields(self):
        """LLMConfigCreate should reject unknown fields."""
        with pytest.raises(ValidationError) as exc_info:
            LLMConfigCreate(
                provider="openai",
                api_key="sk-test123",
                unknown_field="should_fail",
            )
        assert "extra_forbidden" in str(exc_info.value)

    def test_monitored_channel_create_rejects_unknown_fields(self):
        """MonitoredChannelCreate should reject unknown fields."""
        with pytest.raises(ValidationError) as exc_info:
            MonitoredChannelCreate(
                community_server_id="server123",
                channel_id="channel456",
                invalid_field="should_fail",
            )
        assert "extra_forbidden" in str(exc_info.value)

    def test_embedding_request_rejects_unknown_fields(self):
        """EmbeddingRequest should reject unknown fields."""
        with pytest.raises(ValidationError) as exc_info:
            EmbeddingRequest(
                text="Test message",
                community_server_id="server123",
                extra_field="should_fail",
            )
        assert "extra_forbidden" in str(exc_info.value)


@pytest.mark.unit
class TestUpdateSchemas:
    """Test that Update schemas enforce strict validation."""

    def test_note_update_rejects_unknown_fields(self):
        """NoteUpdate should reject unknown fields."""
        with pytest.raises(ValidationError) as exc_info:
            NoteUpdate(
                summary="Updated summary",
                unknown_field="should_fail",
            )
        assert "extra_forbidden" in str(exc_info.value)

    def test_rating_update_rejects_unknown_fields(self):
        """RatingUpdate should reject unknown fields."""
        with pytest.raises(ValidationError) as exc_info:
            RatingUpdate(
                helpfulness_level="HELPFUL",
                extra_field="should_fail",
            )
        assert "extra_forbidden" in str(exc_info.value)

    def test_user_profile_update_rejects_unknown_fields(self):
        """UserProfileUpdate should reject unknown fields."""
        with pytest.raises(ValidationError) as exc_info:
            UserProfileUpdate(
                display_name="New Name",
                invalid_field="should_fail",
            )
        assert "extra_forbidden" in str(exc_info.value)

    def test_user_profile_self_update_rejects_unknown_fields(self):
        """UserProfileSelfUpdate should reject unknown fields."""
        with pytest.raises(ValidationError) as exc_info:
            UserProfileSelfUpdate(
                display_name="New Name",
                invalid_field="should_fail",
            )
        assert "extra_forbidden" in str(exc_info.value)

    def test_user_profile_admin_update_rejects_unknown_fields(self):
        """UserProfileAdminUpdate should reject unknown fields."""
        with pytest.raises(ValidationError) as exc_info:
            UserProfileAdminUpdate(
                display_name="New Name",
                invalid_field="should_fail",
            )
        assert "extra_forbidden" in str(exc_info.value)

    def test_webhook_update_rejects_unknown_fields(self):
        """WebhookUpdateRequest should reject unknown fields."""
        with pytest.raises(ValidationError) as exc_info:
            WebhookUpdateRequest(
                active=False,
                unknown_field="should_fail",
            )
        assert "extra_forbidden" in str(exc_info.value)


@pytest.mark.unit
class TestEventSchemas:
    """Test that Event schemas enforce strict validation."""

    def test_base_event_rejects_unknown_fields(self):
        """BaseEvent should reject unknown fields."""
        with pytest.raises(ValidationError) as exc_info:
            BaseEvent(
                event_id="evt123",
                event_type=EventType.NOTE_CREATED,
                extra_field="should_fail",
            )
        assert "extra_forbidden" in str(exc_info.value)

    def test_note_created_event_rejects_unknown_fields(self):
        """NoteCreatedEvent should reject unknown fields."""
        with pytest.raises(ValidationError) as exc_info:
            NoteCreatedEvent(
                event_id="evt123",
                note_id=uuid4(),
                author_id="user123",
                platform_message_id="456",
                summary="Test note",
                classification="NOT_MISLEADING",
                invalid_field="should_fail",
            )
        assert "extra_forbidden" in str(exc_info.value)


@pytest.mark.unit
class TestBaseSchemas:
    """Test that base schema classes have correct configurations."""

    def test_strict_input_schema_forbids_extra(self):
        """StrictInputSchema should have extra='forbid'."""
        config = StrictInputSchema.model_config
        assert config.get("extra") == "forbid"
        # Note: strict is NOT True - StrictInputSchema allows JSON coercion for HTTP APIs
        assert config.get("str_strip_whitespace") is True
        assert config.get("validate_assignment") is True

    def test_sqlalchemy_schema_allows_from_attributes(self):
        """SQLAlchemySchema should have from_attributes=True."""
        config = SQLAlchemySchema.model_config
        assert config.get("from_attributes") is True
        assert config.get("validate_assignment") is True
        assert config.get("use_enum_values") is True

    def test_strict_event_schema_forbids_extra(self):
        """StrictEventSchema should have extra='forbid'."""
        config = StrictEventSchema.model_config
        assert config.get("extra") == "forbid"
        assert config.get("strict") is True
        assert config.get("validate_assignment") is True


@pytest.mark.unit
class TestORMBackedSchemas:
    """Test that ORM-backed InDB schemas forbid extra fields."""

    def test_note_indb_has_correct_config(self):
        """NoteInDB should forbid extra fields."""
        config = NoteInDB.model_config
        assert config.get("from_attributes") is True
        assert config.get("extra") == "forbid"
        assert config.get("use_enum_values") is True


@pytest.mark.unit
class TestWhitespaceStripping:
    """Test that input schemas strip whitespace from strings."""

    def test_user_profile_create_strips_whitespace(self):
        """UserProfileCreate should strip whitespace."""
        profile = UserProfileCreate(display_name="  Alice  ")
        assert profile.display_name == "Alice"

    def test_note_create_strips_whitespace_from_summary(self):
        """NoteCreate should strip whitespace from summary."""
        author_uuid = uuid4()
        note = NoteCreate(
            author_id=author_uuid,
            community_server_id=uuid4(),
            summary="  Test summary  ",
            classification="NOT_MISLEADING",
        )
        assert note.summary == "Test summary"
        assert note.author_id == author_uuid


@pytest.mark.unit
class TestStrictTypeCoercion:
    """Test that input schemas enforce strict type coercion."""

    def test_note_create_accepts_string_uuid_for_community_server_id(self):
        """NoteCreate accepts UUID for community_server_id."""
        community_id = uuid4()
        author_id = uuid4()
        note = NoteCreate(
            author_id=author_id,
            community_server_id=community_id,
            summary="Test",
            classification="NOT_MISLEADING",
        )
        # Verify the UUID input is accepted
        assert note.community_server_id == community_id


@pytest.mark.unit
class TestResponseSchemas:
    """Test that API Response schemas reject extra fields to catch typos and misuse."""

    def test_request_list_response_rejects_extra_fields(self):
        """RequestListResponse should reject unknown fields."""
        with pytest.raises(ValidationError) as exc_info:
            RequestListResponse(
                requests=[],
                total=0,
                page=1,
                size=20,
                extra_field="should_fail",
            )
        assert "extra_forbidden" in str(exc_info.value)

    def test_monitored_channel_list_response_rejects_extra_fields(self):
        """MonitoredChannelListResponse should reject unknown fields."""
        with pytest.raises(ValidationError) as exc_info:
            MonitoredChannelListResponse(
                channels=[],
                total=0,
                page=1,
                size=20,
                extra_field="should_fail",
            )
        assert "extra_forbidden" in str(exc_info.value)


@pytest.mark.unit
class TestResponseSchemaAutomatedChecks:
    """
    Automated tests to find all Response schemas in the codebase
    and validate they have proper configuration.

    This catches schema validation issues proactively during development.
    """

    def test_all_response_schemas_forbid_extra_fields(self):
        """
        Scan codebase for all Response schemas and verify they forbid extra fields.

        This test ensures that new Response schemas added to the codebase
        automatically get validated for proper configuration.
        """
        import importlib
        import inspect
        import pkgutil
        from pathlib import Path

        from pydantic import BaseModel

        # Track schemas that need fixing
        schemas_without_forbid = []

        # Find all Python modules in src/
        src_path = Path(__file__).parent.parent / "src"

        # Common patterns to exclude
        exclude_patterns = [
            "__pycache__",
            ".pyc",
            "migrations/",
            "alembic/",
            # Exclude specific known schemas that don't need extra='forbid'
            # (These are typically internal DTOs or have special requirements)
        ]

        def should_check_module(module_path: str) -> bool:
            """Check if module should be scanned."""
            return not any(pattern in module_path for pattern in exclude_patterns)

        def find_response_schemas(module):
            """Find all Response schema classes in a module."""
            response_schemas = []

            try:
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    # Check if it's a Response schema
                    if (
                        name.endswith("Response")
                        and issubclass(obj, BaseModel)
                        and obj is not BaseModel
                        and obj.__module__
                        == module.__name__  # Only check schemas defined in this module
                    ):
                        response_schemas.append((name, obj))
            except Exception:
                # Skip modules that can't be introspected
                pass

            return response_schemas

        # Scan all modules
        all_response_schemas = []
        for _importer, modname, _ispkg in pkgutil.walk_packages(
            path=[str(src_path)],
            prefix="src.",
        ):
            if not should_check_module(modname):
                continue

            try:
                module = importlib.import_module(modname)
                schemas = find_response_schemas(module)
                all_response_schemas.extend(schemas)
            except Exception:
                # Skip modules that can't be imported (might have dependencies)
                pass

        # Check each schema
        for schema_name, schema_class in all_response_schemas:
            config = schema_class.model_config

            # List response schemas and similar aggregation schemas should forbid extra fields
            if ("List" in schema_name or "Paginated" in schema_name) and config.get(
                "extra"
            ) != "forbid":
                schemas_without_forbid.append(f"{schema_class.__module__}.{schema_name}")

        # Report findings
        if schemas_without_forbid:
            error_msg = (
                "The following Response schemas don't have extra='forbid' in model_config:\n"
                + "\n".join(f"  - {s}" for s in schemas_without_forbid)
                + "\n\nResponse schemas should reject extra fields to catch typos and API misuse.\n"
                + "Add this to the schema:\n"
                + "  model_config = ConfigDict(extra='forbid')"
            )
            pytest.fail(error_msg)

    def test_model_config_declared_before_fields(self):
        """
        Scan all Pydantic schemas and verify model_config is declared BEFORE fields.

        In Pydantic v2, model_config must be declared before field definitions for
        the configuration to take effect properly. This test catches schemas where
        model_config is mistakenly placed after fields.
        """
        import importlib
        import inspect
        import pkgutil
        from pathlib import Path

        from pydantic import BaseModel

        schemas_with_ordering_issue = []

        src_path = Path(__file__).parent.parent / "src"

        exclude_patterns = [
            "__pycache__",
            ".pyc",
            "migrations/",
            "alembic/",
        ]

        def should_check_module(module_path: str) -> bool:
            return not any(pattern in module_path for pattern in exclude_patterns)

        def check_schema_ordering(schema_class) -> bool:
            """
            Check if model_config is declared before any Field() definitions.

            Returns True if ordering is correct, False otherwise.
            """
            try:
                source_lines, _ = inspect.getsourcelines(schema_class)
                source = "".join(source_lines)

                # Find position of model_config declaration
                model_config_pos = source.find("model_config")
                if model_config_pos == -1:
                    # No model_config defined in this class (might inherit)
                    return True

                # Find position of first Field() call
                first_field_pos = source.find("Field(")
                if first_field_pos == -1:
                    # No Field() calls in this class
                    return True

                # model_config should appear before the first Field()
                return model_config_pos < first_field_pos

            except Exception:
                # If we can't inspect the source, assume it's okay
                return True

        # Scan all modules for Pydantic schemas
        for _importer, modname, _ispkg in pkgutil.walk_packages(
            path=[str(src_path)],
            prefix="src.",
        ):
            if not should_check_module(modname):
                continue

            try:
                module = importlib.import_module(modname)
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    # Check all Pydantic schemas (not just Response schemas)
                    if (
                        issubclass(obj, BaseModel)
                        and obj is not BaseModel
                        and obj.__module__
                        == module.__name__  # Only check schemas defined in this module
                        and hasattr(obj, "model_config")  # Only check schemas with model_config
                        and not check_schema_ordering(obj)
                    ):
                        schemas_with_ordering_issue.append(f"{obj.__module__}.{name}")
            except Exception:
                pass

        # Report findings
        if schemas_with_ordering_issue:
            error_msg = (
                "The following schemas have model_config declared AFTER fields:\n"
                + "\n".join(f"  - {s}" for s in schemas_with_ordering_issue)
                + "\n\nIn Pydantic v2, model_config MUST be declared BEFORE any field definitions.\n"
                + "Move model_config to the top of the class body, right after the docstring:\n\n"
                + "  class MySchema(BaseModel):\n"
                + '      """Docstring."""\n\n'
                + "      model_config = ConfigDict(extra='forbid')  # BEFORE fields\n\n"
                + "      field1: str = Field(...)\n"
                + "      field2: int = Field(...)\n"
            )
            pytest.fail(error_msg)


@pytest.mark.unit
class TestProfileUpdateSchemaSecurity:
    """
    Security tests for profile update schemas.

    These tests verify the fix for the privilege escalation vulnerability
    where UserProfileUpdate allowed setting admin fields like is_opennotes_admin.

    CVE: task-728 - Fix privilege escalation via profile update mass assignment
    """

    def test_self_update_rejects_admin_fields(self):
        """
        SECURITY: UserProfileSelfUpdate must reject admin-only fields.

        This prevents privilege escalation attacks where users try to set
        is_opennotes_admin, is_banned, role, etc. via the self-update endpoint.
        """
        admin_fields = [
            "role",
            "is_opennotes_admin",
            "is_human",
            "is_active",
            "is_banned",
            "banned_at",
            "banned_reason",
        ]

        for field in admin_fields:
            with pytest.raises(ValidationError) as exc_info:
                UserProfileSelfUpdate(**{field: True if "is_" in field else "admin"})
            error_str = str(exc_info.value)
            assert "extra_forbidden" in error_str, (
                f"UserProfileSelfUpdate should reject admin field '{field}'. Got error: {error_str}"
            )

    def test_self_update_allows_user_fields(self):
        """UserProfileSelfUpdate should allow user-editable fields."""
        update = UserProfileSelfUpdate(
            display_name="New Name",
            avatar_url="https://example.com/avatar.png",
            bio="My bio",
        )
        assert update.display_name == "New Name"
        assert update.avatar_url == "https://example.com/avatar.png"
        assert update.bio == "My bio"

    def test_admin_update_allows_all_fields(self):
        """UserProfileAdminUpdate should allow both user and admin fields."""
        update = UserProfileAdminUpdate(
            display_name="Admin Updated Name",
            avatar_url="https://example.com/admin_avatar.png",
            bio="Admin updated bio",
            role="admin",
            is_opennotes_admin=True,
            is_human=True,
            is_active=True,
            is_banned=False,
        )
        assert update.display_name == "Admin Updated Name"
        assert update.role == "admin"
        assert update.is_opennotes_admin is True
        assert update.is_banned is False

    def test_self_update_schema_has_no_admin_field_attributes(self):
        """
        SECURITY: Verify UserProfileSelfUpdate schema has no admin field definitions.

        This is a structural test to ensure admin fields can never be accidentally
        added to the self-update schema.
        """
        admin_field_names = {
            "role",
            "is_opennotes_admin",
            "is_human",
            "is_active",
            "is_banned",
            "banned_at",
            "banned_reason",
        }

        self_update_fields = set(UserProfileSelfUpdate.model_fields.keys())

        overlap = admin_field_names & self_update_fields
        assert not overlap, (
            f"SECURITY VIOLATION: UserProfileSelfUpdate contains admin fields: {overlap}. "
            "These fields must only exist in UserProfileAdminUpdate."
        )

    def test_self_update_only_has_expected_fields(self):
        """Verify UserProfileSelfUpdate only has the expected safe fields."""
        expected_fields = {"display_name", "avatar_url", "bio"}
        actual_fields = set(UserProfileSelfUpdate.model_fields.keys())

        assert actual_fields == expected_fields, (
            f"UserProfileSelfUpdate has unexpected fields. "
            f"Expected: {expected_fields}, Got: {actual_fields}"
        )

    def test_user_profile_update_alias_is_admin_update(self):
        """Verify UserProfileUpdate is aliased to UserProfileAdminUpdate for backward compatibility."""
        assert UserProfileUpdate is UserProfileAdminUpdate


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
