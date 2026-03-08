from __future__ import annotations

import uuid

import click
import huuid
import pytest

from opennotes_cli.formatting import format_id, resolve_id


class TestResolveId:
    def test_accepts_standard_uuid(self):
        uid = "019536b8-bdb2-7c81-8975-77f5c3dbdff8"
        assert resolve_id(uid) == uid

    def test_accepts_uppercase_uuid(self):
        uid = "019536B8-BDB2-7C81-8975-77F5C3DBDFF8"
        result = resolve_id(uid)
        assert result == uid.lower()

    def test_accepts_huuid(self):
        uid = uuid.UUID("019536b8-bdb2-7c81-8975-77f5c3dbdff8")
        h = huuid.uuid2human(uid)
        result = resolve_id(h)
        assert result == str(uid)

    def test_roundtrip_uuid_to_huuid_to_uuid(self):
        uid = uuid.uuid4()
        h = huuid.uuid2human(uid)
        resolved = resolve_id(h)
        assert resolved == str(uid)

    def test_rejects_invalid_input(self):
        with pytest.raises(click.BadParameter, match="Invalid ID"):
            resolve_id("not-a-valid-id")

    def test_rejects_empty_string(self):
        with pytest.raises(click.BadParameter):
            resolve_id("")

    def test_accepts_uuid_without_dashes(self):
        uid = "019536b8bdb27c81897577f5c3dbdff8"
        result = resolve_id(uid)
        assert result == "019536b8-bdb2-7c81-8975-77f5c3dbdff8"


class TestFormatId:
    def test_returns_huuid_when_enabled(self):
        uid = "019536b8-bdb2-7c81-8975-77f5c3dbdff8"
        result = format_id(uid, use_huuid=True)
        expected = huuid.uuid2human(uuid.UUID(uid))
        assert result == expected

    def test_returns_raw_uuid_when_disabled(self):
        uid = "019536b8-bdb2-7c81-8975-77f5c3dbdff8"
        result = format_id(uid, use_huuid=False)
        assert result == uid

    def test_none_returns_na(self):
        result = format_id(None, use_huuid=True)
        assert result == "N/A"

    def test_none_returns_na_when_huuid_disabled(self):
        result = format_id(None, use_huuid=False)
        assert result == "N/A"

    def test_passthrough_for_non_uuid(self):
        result = format_id("N/A", use_huuid=True)
        assert result == "N/A"

    def test_passthrough_for_empty_string(self):
        result = format_id("", use_huuid=True)
        assert result == ""

    def test_huuid_is_roundtrippable(self):
        uid = str(uuid.uuid4())
        h = format_id(uid, use_huuid=True)
        resolved = resolve_id(h)
        assert resolved == uid

    def test_multiple_uuids_produce_distinct_huuids(self):
        u1 = str(uuid.uuid4())
        u2 = str(uuid.uuid4())
        h1 = format_id(u1, use_huuid=True)
        h2 = format_id(u2, use_huuid=True)
        assert h1 != h2


class TestCliUuidFlag:
    def test_cli_context_defaults_to_huuid(self):
        from opennotes_cli.cli import CliContext

        class FakeAuth:
            def get_server_url(self):
                return "http://localhost"

        import httpx

        ctx = CliContext(
            auth=FakeAuth(),
            json_output=False,
            verbose=False,
            env_name="local",
            client=httpx.Client(),
        )
        assert ctx.use_huuid is True

    def test_cli_context_respects_raw_uuid_flag(self):
        from opennotes_cli.cli import CliContext

        class FakeAuth:
            def get_server_url(self):
                return "http://localhost"

        import httpx

        ctx = CliContext(
            auth=FakeAuth(),
            json_output=False,
            verbose=False,
            env_name="local",
            client=httpx.Client(),
            use_huuid=False,
        )
        assert ctx.use_huuid is False
