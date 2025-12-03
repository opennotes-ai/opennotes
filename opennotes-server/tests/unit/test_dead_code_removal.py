"""Tests verifying dead code has been removed from services."""

import importlib
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.fact_checking.embedding_service import EmbeddingService
from src.llm_config.service import LLMService


class TestEmbeddingServiceDeadCodeRemoval:
    """Tests verifying dead code has been removed from EmbeddingService."""

    @pytest.fixture
    def embedding_service(self):
        mock_llm_service = MagicMock(spec=LLMService)
        return EmbeddingService(mock_llm_service)

    def test_get_openai_client_method_does_not_exist(self, embedding_service):
        """Verify _get_openai_client method has been removed.

        This method was superseded by LLMClientManager and should not exist.
        """
        assert not hasattr(embedding_service, "_get_openai_client"), (
            "_get_openai_client method should have been removed from EmbeddingService. "
            "This functionality is now provided by LLMClientManager."
        )

    def test_api_key_source_cache_attribute_does_not_exist(self, embedding_service):
        """Verify api_key_source_cache attribute has been removed.

        This attribute was only used by the now-removed _get_openai_client method.
        """
        assert not hasattr(embedding_service, "api_key_source_cache"), (
            "api_key_source_cache attribute should have been removed from EmbeddingService. "
            "It was only used by the now-removed _get_openai_client method."
        )

    def test_embedding_cache_still_exists(self, embedding_service):
        """Verify that the legitimate embedding_cache still exists."""
        assert hasattr(embedding_service, "embedding_cache"), (
            "embedding_cache attribute should still exist on EmbeddingService"
        )


class TestProfileTrackingMiddlewareRemoval:
    """Tests verifying ProfileTrackingMiddleware dead code has been removed.

    The ProfileTrackingMiddleware was defined but never registered in main.py.
    See task-797.01 for details.
    """

    def test_profile_tracking_module_does_not_exist(self):
        """Verify profile_tracking.py module has been removed.

        The entire module was dead code - ProfileTrackingMiddleware was defined
        but never registered in main.py.
        """
        middleware_file = importlib.import_module("src.middleware").__file__
        assert middleware_file is not None
        middleware_dir = Path(middleware_file).parent
        profile_tracking_path = middleware_dir / "profile_tracking.py"

        assert not profile_tracking_path.exists(), (
            f"profile_tracking.py should have been removed. "
            f"ProfileTrackingMiddleware was never registered in main.py and was dead code. "
            f"Path: {profile_tracking_path}"
        )

    def test_profile_tracking_middleware_not_importable(self):
        """Verify ProfileTrackingMiddleware cannot be imported."""
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module("src.middleware.profile_tracking")
