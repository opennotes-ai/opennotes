"""
Unit tests for EncryptedJSONB TypeDecorator.

Tests the encryption/decryption logic without requiring database connectivity.
"""

import pytest
from cryptography.fernet import Fernet, InvalidToken

from src.database import EncryptedJSONB

pytestmark = pytest.mark.unit


@pytest.fixture
def encryption_key():
    """Generate a test encryption key."""
    return Fernet.generate_key().decode()


@pytest.fixture
def encrypted_type(encryption_key, monkeypatch):
    """Create an EncryptedJSONB instance with a test key."""
    monkeypatch.setenv("CREDENTIALS_ENCRYPTION_KEY", encryption_key)

    from src.config import settings

    monkeypatch.setattr(settings, "CREDENTIALS_ENCRYPTION_KEY", encryption_key)

    return EncryptedJSONB()


def test_process_bind_param_encrypts_data(encrypted_type):
    """Test that process_bind_param encrypts data correctly."""
    original_data = {
        "email": "test@example.com",
        "hashed_password": "bcrypt_hash",
        "sensitive_token": "secret123",
    }

    encrypted_result = encrypted_type.process_bind_param(original_data, None)

    assert encrypted_result is not None
    assert isinstance(encrypted_result, dict)
    assert "encrypted" in encrypted_result

    encrypted_str = encrypted_result["encrypted"]
    assert "test@example.com" not in encrypted_str
    assert "bcrypt_hash" not in encrypted_str
    assert "secret123" not in encrypted_str


def test_process_bind_param_none_value(encrypted_type):
    """Test that None values are handled correctly on bind."""
    result = encrypted_type.process_bind_param(None, None)
    assert result is None


def test_process_result_value_decrypts_data(encrypted_type):
    """Test that process_result_value decrypts data correctly."""
    original_data = {
        "user_id": "12345",
        "access_token": "token_abc",
        "nested": {"key": "value", "number": 42},
    }

    encrypted_data = encrypted_type.process_bind_param(original_data, None)
    decrypted_data = encrypted_type.process_result_value(encrypted_data, None)

    assert decrypted_data == original_data
    assert decrypted_data["user_id"] == "12345"
    assert decrypted_data["access_token"] == "token_abc"
    assert decrypted_data["nested"]["key"] == "value"
    assert decrypted_data["nested"]["number"] == 42


def test_process_result_value_none(encrypted_type):
    """Test that None values are handled correctly on result."""
    result = encrypted_type.process_result_value(None, None)
    assert result is None


def test_process_result_value_unencrypted_data(encrypted_type):
    """Test backward compatibility with unencrypted data."""
    unencrypted_data = {"legacy": "data", "not": "encrypted"}

    result = encrypted_type.process_result_value(unencrypted_data, None)

    assert result == unencrypted_data


def test_round_trip_encryption_decryption(encrypted_type):
    """Test full round-trip encryption and decryption."""
    test_cases = [
        {"simple": "value"},
        {"nested": {"deep": {"structure": "value"}}},
        {"list": [1, 2, 3], "bool": True, "null": None},
        {"unicode": "emoji 🎉 and special chars àéîøü"},
        {},
    ]

    for original in test_cases:
        encrypted = encrypted_type.process_bind_param(original, None)
        decrypted = encrypted_type.process_result_value(encrypted, None)
        assert decrypted == original, f"Round-trip failed for {original}"


def test_encrypted_data_is_deterministic_with_sorting(encrypted_type):
    """Test that encryption produces consistent output for same data."""
    data = {"b": 2, "a": 1, "c": 3}

    encrypted1 = encrypted_type.process_bind_param(data, None)
    encrypted2 = encrypted_type.process_bind_param(data, None)

    assert "encrypted" in encrypted1
    assert "encrypted" in encrypted2


def test_different_keys_produce_different_ciphertext(monkeypatch):
    """Test that different encryption keys produce different ciphertext."""
    from src.config import get_settings

    original_data = {"test": "data"}

    key1 = Fernet.generate_key().decode()
    key2 = Fernet.generate_key().decode()

    monkeypatch.setenv("CREDENTIALS_ENCRYPTION_KEY", key1)
    get_settings.cache_clear()
    type1 = EncryptedJSONB()

    monkeypatch.setenv("CREDENTIALS_ENCRYPTION_KEY", key2)
    get_settings.cache_clear()
    type2 = EncryptedJSONB()

    encrypted1 = type1.process_bind_param(original_data, None)
    encrypted2 = type2.process_bind_param(original_data, None)

    assert encrypted1["encrypted"] != encrypted2["encrypted"]


def test_decrypt_fails_with_wrong_key(monkeypatch):
    """Test that decryption fails gracefully with wrong key."""
    from src.config import get_settings

    original_data = {"secret": "data"}

    key1 = Fernet.generate_key().decode()
    monkeypatch.setenv("CREDENTIALS_ENCRYPTION_KEY", key1)
    get_settings.cache_clear()
    type1 = EncryptedJSONB()

    encrypted = type1.process_bind_param(original_data, None)

    key2 = Fernet.generate_key().decode()
    monkeypatch.setenv("CREDENTIALS_ENCRYPTION_KEY", key2)
    get_settings.cache_clear()
    type2 = EncryptedJSONB()

    with pytest.raises(InvalidToken):
        type2.process_result_value(encrypted, None)
