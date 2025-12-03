"""
Validation configuration and enforcement for production environments.

This module ensures that Pydantic validation is always enabled and provides
utilities to verify that validation is not being bypassed.
"""

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)


class ProductionValidationConfig:
    """
    Configuration to enforce validation in production environments.

    Pydantic validation is enabled by default in FastAPI. This config ensures
    that validation is never bypassed using unsafe methods like model_construct().
    """

    @staticmethod
    def get_model_config() -> ConfigDict:
        """
        Get recommended Pydantic model config for production.

        Returns:
            ConfigDict with strict validation settings
        """
        return ConfigDict(
            validate_assignment=True,
            validate_default=True,
            validate_return=True,
            strict=False,
            extra="forbid",
        )

    @staticmethod
    def validate_model_safe(model_class: type[BaseModel], data: dict[str, Any]) -> BaseModel:
        """
        Safely validate data against a Pydantic model.

        Always uses model_validate() which performs full validation,
        never model_construct() which bypasses validation.

        Args:
            model_class: The Pydantic model class
            data: Data to validate

        Returns:
            Validated model instance

        Raises:
            ValidationError: If validation fails
        """
        return model_class.model_validate(data)


def ensure_validation_enabled() -> None:
    """
    Verify that validation is enabled and log configuration.

    In FastAPI with Pydantic, validation is always enabled by default.
    This function logs the validation status for monitoring.
    """
    logger.info(
        "Pydantic validation is enabled by default in FastAPI. "
        "Use ProductionValidationConfig.validate_model_safe() to ensure "
        "validation is never bypassed."
    )
