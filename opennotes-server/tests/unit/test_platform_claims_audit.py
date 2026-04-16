from __future__ import annotations

from src.auth.platform_claims import PlatformIdentity


def test_extract_identity_audit_fields_with_identity():
    from src.auth.permissions import extract_identity_audit_fields

    identity = PlatformIdentity(
        platform="discourse",
        scope="forum.example.com",
        sub="42",
        community_id="comm-123",
        can_administer_community=False,
    )
    fields = extract_identity_audit_fields(identity, source="jwt")
    assert fields == {
        "platform_identity_sub": "42",
        "platform_identity_scope": "forum.example.com",
        "platform_identity_community_id": "comm-123",
        "platform_identity_platform": "discourse",
        "platform_identity_source": "jwt",
    }


def test_extract_identity_audit_fields_none():
    from src.auth.permissions import extract_identity_audit_fields

    assert extract_identity_audit_fields(None) == {}


def test_extract_identity_audit_fields_no_source():
    from src.auth.permissions import extract_identity_audit_fields

    identity = PlatformIdentity(
        platform="discord",
        scope="guild:123",
        sub="456",
        community_id="comm-789",
        can_administer_community=True,
    )
    fields = extract_identity_audit_fields(identity)
    assert "platform_identity_source" not in fields
    assert fields["platform_identity_sub"] == "456"


def test_extract_identity_audit_fields_adapter_headers_source():
    from src.auth.permissions import extract_identity_audit_fields

    identity = PlatformIdentity(
        platform="discourse",
        scope="forum.opennotes.io",
        sub="99",
        community_id="comm-999",
        can_administer_community=True,
    )
    fields = extract_identity_audit_fields(identity, source="adapter_headers")
    assert fields["platform_identity_source"] == "adapter_headers"
    assert fields["platform_identity_platform"] == "discourse"
    assert fields["platform_identity_sub"] == "99"
    assert fields["platform_identity_scope"] == "forum.opennotes.io"
    assert fields["platform_identity_community_id"] == "comm-999"
