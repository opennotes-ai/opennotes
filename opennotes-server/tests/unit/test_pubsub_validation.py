import hashlib
import hmac
import json
import time

import pytest

from src.cache.adapters.redis import MAX_MESSAGE_AGE_SECONDS, PubSubMessage


def test_pubsub_message_validation() -> None:
    valid_message = {
        "type": "user.created",
        "payload": {"user_id": "123", "username": "alice"},
        "timestamp": int(time.time()),
    }

    message = PubSubMessage.model_validate(valid_message)

    assert message.type == "user.created"
    assert message.payload == {"user_id": "123", "username": "alice"}
    assert message.signature is None


def test_pubsub_message_with_signature() -> None:
    valid_message = {
        "type": "user.created",
        "payload": {"user_id": "123"},
        "timestamp": int(time.time()),
        "signature": "a" * 64,
    }

    message = PubSubMessage.model_validate(valid_message)

    assert message.signature == "a" * 64


def test_pubsub_message_missing_required_field() -> None:
    from pydantic import ValidationError

    invalid_message = {
        "payload": {"user_id": "123"},
        "timestamp": int(time.time()),
    }

    with pytest.raises(ValidationError):
        PubSubMessage.model_validate(invalid_message)


def test_pubsub_message_invalid_type_length() -> None:
    from pydantic import ValidationError

    invalid_message = {
        "type": "",
        "payload": {"user_id": "123"},
        "timestamp": int(time.time()),
    }

    with pytest.raises(ValidationError):
        PubSubMessage.model_validate(invalid_message)


def test_pubsub_message_negative_timestamp() -> None:
    from pydantic import ValidationError

    invalid_message = {
        "type": "user.created",
        "payload": {"user_id": "123"},
        "timestamp": -1,
    }

    with pytest.raises(ValidationError):
        PubSubMessage.model_validate(invalid_message)


def test_pubsub_message_invalid_signature_length() -> None:
    from pydantic import ValidationError

    invalid_message = {
        "type": "user.created",
        "payload": {"user_id": "123"},
        "timestamp": int(time.time()),
        "signature": "short",
    }

    with pytest.raises(ValidationError):
        PubSubMessage.model_validate(invalid_message)


def test_message_validation_with_hmac() -> None:
    from src.cache.adapters.redis import RedisCacheAdapter

    adapter = RedisCacheAdapter()

    secret = "test_secret"
    payload = {"user_id": "123"}
    message_type = "user.created"
    timestamp = int(time.time())

    payload_str = json.dumps(payload, sort_keys=True)
    message_to_sign = f"{message_type}:{payload_str}:{timestamp}"
    signature = hmac.new(
        secret.encode(),
        message_to_sign.encode(),
        hashlib.sha256,
    ).hexdigest()

    message_data = {
        "type": message_type,
        "payload": payload,
        "timestamp": timestamp,
        "signature": signature,
    }

    raw_data = json.dumps(message_data)
    result = adapter._validate_message(raw_data, hmac_secret=secret)

    assert result is True


def test_message_validation_with_invalid_hmac() -> None:
    from src.cache.adapters.redis import RedisCacheAdapter

    adapter = RedisCacheAdapter()

    message_data = {
        "type": "user.created",
        "payload": {"user_id": "123"},
        "timestamp": int(time.time()),
        "signature": "invalid_signature_" + "a" * 50,
    }

    raw_data = json.dumps(message_data)
    result = adapter._validate_message(raw_data, hmac_secret="test_secret")

    assert result is False


def test_message_validation_expired_timestamp() -> None:
    from src.cache.adapters.redis import RedisCacheAdapter

    adapter = RedisCacheAdapter()

    old_timestamp = int(time.time()) - MAX_MESSAGE_AGE_SECONDS - 10

    message_data = {
        "type": "user.created",
        "payload": {"user_id": "123"},
        "timestamp": old_timestamp,
    }

    raw_data = json.dumps(message_data)
    result = adapter._validate_message(raw_data)

    assert result is False


def test_message_validation_future_timestamp() -> None:
    from src.cache.adapters.redis import RedisCacheAdapter

    adapter = RedisCacheAdapter()

    future_timestamp = int(time.time()) + MAX_MESSAGE_AGE_SECONDS + 10

    message_data = {
        "type": "user.created",
        "payload": {"user_id": "123"},
        "timestamp": future_timestamp,
    }

    raw_data = json.dumps(message_data)
    result = adapter._validate_message(raw_data)

    assert result is False


def test_message_validation_at_boundary() -> None:
    from src.cache.adapters.redis import RedisCacheAdapter

    adapter = RedisCacheAdapter()

    boundary_timestamp = int(time.time()) - MAX_MESSAGE_AGE_SECONDS

    message_data = {
        "type": "user.created",
        "payload": {"user_id": "123"},
        "timestamp": boundary_timestamp,
    }

    raw_data = json.dumps(message_data)
    result = adapter._validate_message(raw_data)

    assert result is True


def test_message_validation_invalid_json() -> None:
    from src.cache.adapters.redis import RedisCacheAdapter

    adapter = RedisCacheAdapter()

    invalid_json = "not valid json"
    result = adapter._validate_message(invalid_json)

    assert result is False
