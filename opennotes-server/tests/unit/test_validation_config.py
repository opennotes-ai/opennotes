import pytest
from pydantic import BaseModel, Field, ValidationError

from src.validation import ProductionValidationConfig, ensure_validation_enabled


class TestModel(BaseModel):
    name: str = Field(..., min_length=1)
    age: int = Field(..., ge=0, le=150)
    email: str


def test_validation_config_settings() -> None:
    config = ProductionValidationConfig.get_model_config()

    assert config["validate_assignment"] is True
    assert config["validate_default"] is True
    assert config["validate_return"] is True
    assert config["extra"] == "forbid"


def test_validate_model_safe_with_valid_data() -> None:
    valid_data = {"name": "Alice", "age": 30, "email": "alice@example.com"}

    result = ProductionValidationConfig.validate_model_safe(TestModel, valid_data)

    assert isinstance(result, TestModel)
    assert result.name == "Alice"
    assert result.age == 30


def test_validate_model_safe_with_invalid_data() -> None:
    invalid_data = {"name": "", "age": -5, "email": "alice@example.com"}

    with pytest.raises(ValidationError):
        ProductionValidationConfig.validate_model_safe(TestModel, invalid_data)


def test_validate_model_safe_with_missing_field() -> None:
    incomplete_data = {"name": "Alice", "age": 30}

    with pytest.raises(ValidationError):
        ProductionValidationConfig.validate_model_safe(TestModel, incomplete_data)


def test_validate_model_safe_with_extra_field() -> None:
    class StrictModel(BaseModel):
        model_config = ProductionValidationConfig.get_model_config()
        name: str

    data_with_extra = {"name": "Alice", "extra_field": "should_fail"}

    with pytest.raises(ValidationError):
        ProductionValidationConfig.validate_model_safe(StrictModel, data_with_extra)


def test_ensure_validation_enabled_runs_without_error() -> None:
    try:
        ensure_validation_enabled()
    except Exception as e:
        pytest.fail(f"ensure_validation_enabled() should not raise: {e}")


def test_pydantic_validation_enabled_by_default() -> None:
    """Verify that Pydantic validates by default without any config."""

    class DefaultModel(BaseModel):
        value: int = Field(..., ge=0)

    with pytest.raises(ValidationError):
        DefaultModel(value=-1)

    valid = DefaultModel(value=5)
    assert valid.value == 5


def test_model_construct_bypasses_validation() -> None:
    """
    Demonstrate that model_construct() bypasses validation.
    This is why we provide validate_model_safe() instead.
    """

    class StrictModel(BaseModel):
        value: int = Field(..., ge=0)

    bypassed = StrictModel.model_construct(value=-999)
    assert bypassed.value == -999


def test_validate_model_safe_prevents_bypass() -> None:
    """
    Verify that validate_model_safe() always validates,
    unlike model_construct().
    """

    class StrictModel(BaseModel):
        value: int = Field(..., ge=0)

    invalid_data = {"value": -999}

    with pytest.raises(ValidationError):
        ProductionValidationConfig.validate_model_safe(StrictModel, invalid_data)
