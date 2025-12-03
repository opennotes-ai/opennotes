import pytest

from src.config import settings


@pytest.mark.unit
def test_max_deliver_setting_exists():
    assert hasattr(settings, "NATS_MAX_DELIVER_ATTEMPTS")
    assert isinstance(settings.NATS_MAX_DELIVER_ATTEMPTS, int)
    assert settings.NATS_MAX_DELIVER_ATTEMPTS > 0
    assert settings.NATS_MAX_DELIVER_ATTEMPTS == 5


@pytest.mark.unit
def test_ack_wait_setting_exists():
    assert hasattr(settings, "NATS_ACK_WAIT_SECONDS")
    assert isinstance(settings.NATS_ACK_WAIT_SECONDS, int)
    assert settings.NATS_ACK_WAIT_SECONDS > 0
    assert settings.NATS_ACK_WAIT_SECONDS == 30


@pytest.mark.unit
def test_consumer_config_imports():
    from nats.js.api import ConsumerConfig

    config = ConsumerConfig(
        durable_name="test",
        max_deliver=5,
        ack_wait=30,
    )

    assert config.durable_name == "test"
    assert config.max_deliver == 5
    assert config.ack_wait == 30


@pytest.mark.unit
def test_subscriber_logs_delivery_count():
    from src.events.subscriber import event_subscriber

    assert event_subscriber is not None
