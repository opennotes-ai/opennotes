from uuid import uuid4

from src.llm_config.models import CommunityServer


class TestFlashpointDetectionDefault:
    def test_flashpoint_detection_python_default_is_true(self):
        col = CommunityServer.__table__.c.flashpoint_detection_enabled
        assert col.default.arg is True

    def test_flashpoint_detection_server_default_is_true(self):
        col = CommunityServer.__table__.c.flashpoint_detection_enabled
        assert col.server_default.arg == "true"

    def test_flashpoint_detection_can_be_explicitly_disabled(self):
        server = CommunityServer(
            id=uuid4(),
            platform="discord",
            platform_community_server_id="123456789",
            name="Test Server",
            flashpoint_detection_enabled=False,
        )
        assert server.flashpoint_detection_enabled is False
