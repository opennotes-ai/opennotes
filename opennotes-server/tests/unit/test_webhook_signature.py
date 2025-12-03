import time

from src.webhooks.signature import (
    MAX_WEBHOOK_AGE_SECONDS,
    add_signature_to_webhook,
    extract_and_verify_webhook,
    generate_webhook_signature,
    verify_webhook_signature,
)


def test_generate_webhook_signature() -> None:
    payload = {"user_id": "123", "action": "created"}
    secret = "test_secret"

    sig = generate_webhook_signature(payload, secret)

    assert sig.timestamp > 0
    assert len(sig.signature) == 64
    assert sig.signature.isalnum()


def test_generate_signature_deterministic() -> None:
    payload = {"user_id": "123", "action": "created"}
    secret = "test_secret"
    timestamp = 1234567890

    sig1 = generate_webhook_signature(payload, secret, timestamp)
    sig2 = generate_webhook_signature(payload, secret, timestamp)

    assert sig1.signature == sig2.signature
    assert sig1.timestamp == sig2.timestamp


def test_generate_signature_different_for_different_payload() -> None:
    secret = "test_secret"
    timestamp = 1234567890

    payload1 = {"user_id": "123"}
    payload2 = {"user_id": "456"}

    sig1 = generate_webhook_signature(payload1, secret, timestamp)
    sig2 = generate_webhook_signature(payload2, secret, timestamp)

    assert sig1.signature != sig2.signature


def test_generate_signature_different_for_different_secret() -> None:
    payload = {"user_id": "123"}
    timestamp = 1234567890

    sig1 = generate_webhook_signature(payload, "secret1", timestamp)
    sig2 = generate_webhook_signature(payload, "secret2", timestamp)

    assert sig1.signature != sig2.signature


def test_verify_valid_signature() -> None:
    payload = {"user_id": "123", "action": "created"}
    secret = "test_secret"
    timestamp = int(time.time())

    sig = generate_webhook_signature(payload, secret, timestamp)

    result = verify_webhook_signature(payload, secret, timestamp, sig.signature)

    assert result is True


def test_verify_invalid_signature() -> None:
    payload = {"user_id": "123"}
    secret = "test_secret"
    timestamp = int(time.time())

    invalid_signature = "a" * 64

    result = verify_webhook_signature(payload, secret, timestamp, invalid_signature)

    assert result is False


def test_verify_expired_signature() -> None:
    payload = {"user_id": "123"}
    secret = "test_secret"
    old_timestamp = int(time.time()) - MAX_WEBHOOK_AGE_SECONDS - 10

    sig = generate_webhook_signature(payload, secret, old_timestamp)

    result = verify_webhook_signature(payload, secret, old_timestamp, sig.signature)

    assert result is False


def test_verify_future_signature() -> None:
    payload = {"user_id": "123"}
    secret = "test_secret"
    future_timestamp = int(time.time()) + MAX_WEBHOOK_AGE_SECONDS + 10

    sig = generate_webhook_signature(payload, secret, future_timestamp)

    result = verify_webhook_signature(payload, secret, future_timestamp, sig.signature)

    assert result is False


def test_verify_signature_at_boundary() -> None:
    payload = {"user_id": "123"}
    secret = "test_secret"
    boundary_timestamp = int(time.time()) - MAX_WEBHOOK_AGE_SECONDS

    sig = generate_webhook_signature(payload, secret, boundary_timestamp)

    result = verify_webhook_signature(payload, secret, boundary_timestamp, sig.signature)

    assert result is True


def test_add_signature_to_webhook() -> None:
    payload = {"user_id": "123", "action": "created"}
    secret = "test_secret"

    signed = add_signature_to_webhook(payload, secret)

    assert "_webhook_timestamp" in signed
    assert "_webhook_signature" in signed
    assert signed["user_id"] == "123"
    assert signed["action"] == "created"
    assert len(signed["_webhook_signature"]) == 64


def test_extract_and_verify_valid_webhook() -> None:
    payload = {"user_id": "123", "action": "created"}
    secret = "test_secret"

    signed = add_signature_to_webhook(payload, secret)

    extracted, is_valid = extract_and_verify_webhook(signed, secret)

    assert is_valid is True
    assert extracted == payload
    assert "_webhook_timestamp" not in extracted
    assert "_webhook_signature" not in extracted


def test_extract_and_verify_invalid_signature() -> None:
    payload = {"user_id": "123"}
    secret = "test_secret"

    signed = add_signature_to_webhook(payload, secret)
    signed["_webhook_signature"] = "invalid_signature_" + "a" * 44

    _extracted, is_valid = extract_and_verify_webhook(signed, "test_secret")

    assert is_valid is False


def test_extract_and_verify_missing_timestamp() -> None:
    payload_with_sig = {"user_id": "123", "_webhook_signature": "a" * 64}

    extracted, is_valid = extract_and_verify_webhook(payload_with_sig, "test_secret")

    assert is_valid is False
    assert extracted == {}


def test_extract_and_verify_missing_signature() -> None:
    payload_with_timestamp = {"user_id": "123", "_webhook_timestamp": int(time.time())}

    extracted, is_valid = extract_and_verify_webhook(payload_with_timestamp, "test_secret")

    assert is_valid is False
    assert extracted == {}


def test_extract_and_verify_wrong_secret() -> None:
    payload = {"user_id": "123"}
    secret = "correct_secret"

    signed = add_signature_to_webhook(payload, secret)

    _extracted, is_valid = extract_and_verify_webhook(signed, "wrong_secret")

    assert is_valid is False


def test_signature_survives_json_round_trip() -> None:
    import json

    payload = {"user_id": "123", "nested": {"key": "value"}}
    secret = "test_secret"

    signed = add_signature_to_webhook(payload, secret)

    serialized = json.dumps(signed)
    deserialized = json.loads(serialized)

    extracted, is_valid = extract_and_verify_webhook(deserialized, secret)

    assert is_valid is True
    assert extracted == payload


def test_signature_detects_payload_tampering() -> None:
    payload = {"user_id": "123", "role": "user"}
    secret = "test_secret"

    signed = add_signature_to_webhook(payload, secret)

    signed["role"] = "admin"

    _extracted, is_valid = extract_and_verify_webhook(signed, secret)

    assert is_valid is False
