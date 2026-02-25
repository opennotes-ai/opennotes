from __future__ import annotations

import base64
import json
import math
import os
import warnings
from collections import Counter
from typing import Annotated, Any, Literal, cast

from cryptography.fernet import Fernet
from pydantic import (
    AliasChoices,
    BeforeValidator,
    Field,
    computed_field,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from src.llm_config.model_id import ModelId


def _parse_model_id(v: Any) -> ModelId:
    if isinstance(v, ModelId):
        return v
    if isinstance(v, str):
        return ModelId.from_litellm(v)
    msg = f"Expected str or ModelId, got {type(v)}"
    raise ValueError(msg)


LiteLLMModelId = Annotated[ModelId, NoDecode, BeforeValidator(_parse_model_id)]

# Module-level singleton tracking variables
# These must be outside the Settings class to avoid Pydantic treating them as PrivateAttr
_settings_instance: Settings | None = None
_settings_initialized: bool = False


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    def __new__(cls, **_kwargs: Any) -> Settings:
        global _settings_instance, _settings_initialized  # noqa: PLW0603 - Singleton pattern requires module-level state
        if _settings_instance is None:
            instance = super().__new__(cls)
            _settings_instance = instance
            _settings_initialized = False
        return cast(Settings, _settings_instance)

    def __init__(self, **kwargs: Any) -> None:
        global _settings_initialized  # noqa: PLW0603 - Singleton pattern requires module-level state
        if _settings_initialized:
            return
        super().__init__(**kwargs)
        _settings_initialized = True

    ENVIRONMENT: Literal["development", "staging", "production", "test"] = "development"
    DEBUG: bool = Field(default=False)
    TESTING: bool = Field(default=False)
    skip_startup_checks_raw: str = Field(
        default="",
        validation_alias="SKIP_STARTUP_CHECKS",
        exclude=True,
        description="Raw value for SKIP_STARTUP_CHECKS (use SKIP_STARTUP_CHECKS property for parsed list). "
        "Accepts: comma-separated string, JSON array, or bracket notation with unquoted values.",
    )

    @computed_field
    @property
    def SKIP_STARTUP_CHECKS(self) -> list[str]:  # noqa: N802 - uppercase for backward compatibility
        """Parse SKIP_STARTUP_CHECKS into a list.

        Supports multiple formats:
        - Comma-separated: "database_schema,postgresql"
        - JSON array: '["database_schema", "postgresql"]'
        - Bracket notation (unquoted): "[all]" or "[a, b, c]"
        """
        v = self.skip_startup_checks_raw
        if not v or not v.strip():
            return []
        v = v.strip()
        if v.startswith("[") and v.endswith("]"):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed]
            except json.JSONDecodeError:
                inner = v[1:-1]
                return [item.strip() for item in inner.split(",") if item.strip()]
        return [check.strip() for check in v.split(",") if check.strip()]

    PROJECT_NAME: str = "Open Notes Server"
    VERSION: str = Field(
        default="0.0.1",
        validation_alias=AliasChoices("SERVICE_VERSION", "OTEL_SERVICE_VERSION"),
        description="Service version for tracing (git SHA in production)",
    )
    VCS_REF: str | None = Field(default=None, description="Git commit SHA from build")
    BUILD_DATE: str | None = Field(default=None, description="Build timestamp from CI")
    K_REVISION: str | None = Field(default=None, description="Cloud Run revision name")

    API_V1_PREFIX: str = "/api/v1"
    API_V2_PREFIX: str = "/api/v2"

    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 8000
    INSTANCE_ID: str = Field(
        default="opennotes-server-1",
        description="Unique identifier for this server instance (e.g., opennotes-server-1, opennotes-server-2)",
    )
    SERVER_MODE: Literal["full", "dbos_worker"] = Field(
        default="full",
        description="Server mode: 'full' runs complete API server with all handlers, "
        "'dbos_worker' runs minimal server for DBOS workflow processing only",
    )

    CORS_ORIGINS: str | list[str] = Field(default="http://localhost:3000,http://localhost:5173")

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    LOG_LEVEL_OVERRIDES: str = Field(
        default="",
        description="Comma-separated per-module log level overrides (e.g., 'src.events:DEBUG,src.tasks:DEBUG')",
    )

    DISCORD_PUBLIC_KEY: str = Field(default="")
    DISCORD_BOT_TOKEN: str = Field(default="")
    DISCORD_APPLICATION_ID: str = Field(default="")
    DISCORD_CLIENT_ID: str = Field(default="", description="Discord OAuth2 client ID")
    DISCORD_CLIENT_SECRET: str = Field(default="", description="Discord OAuth2 client secret")
    DISCORD_OAUTH_REDIRECT_URI: str = Field(
        default="http://localhost:3000/auth/discord/callback",
        description="Discord OAuth2 redirect URI",
    )
    DISCORD_API_URL: str = Field(default="https://discord.com/api/v10")
    DISCORD_API_TIMEOUT: float = Field(
        default=30.0, description="Timeout for Discord API requests in seconds"
    )

    REQUEST_TIMEOUT: float = Field(
        default=30.0, description="Request timeout in seconds for API endpoints"
    )
    HEALTH_CHECK_TIMEOUT: int = Field(default=5, description="Health check timeout in seconds")
    CACHE_HIT_RATE_THRESHOLD: float = Field(
        default=0.5, description="Minimum cache hit rate (0.0-1.0) before marking cache as DEGRADED"
    )
    HEALTH_CHECK_COMPONENT_TIMEOUT: float = Field(
        default=3.0, description="Timeout in seconds for individual health check components"
    )
    HEALTH_CHECK_HEARTBEAT_INTERVAL: int = Field(
        default=10, description="Interval in seconds for instance heartbeat updates to Redis"
    )
    HEALTH_CHECK_UNHEALTHY_TIMEOUT: int = Field(
        default=30,
        description="Timeout in seconds to mark instance as unhealthy if no heartbeat received",
    )

    @field_validator("DISCORD_PUBLIC_KEY")
    @classmethod
    def validate_discord_public_key(cls, v: str) -> str:
        if not v:
            return v

        if len(v) != 64:
            raise ValueError(
                f"DISCORD_PUBLIC_KEY must be exactly 64 hex characters (32 bytes). Got {len(v)} characters."
            )

        try:
            public_key_bytes = bytes.fromhex(v)
        except ValueError as e:
            raise ValueError(f"DISCORD_PUBLIC_KEY must be valid hexadecimal: {e}") from e

        if len(public_key_bytes) != 32:
            raise ValueError(
                f"DISCORD_PUBLIC_KEY decoded to {len(public_key_bytes)} bytes, expected 32 bytes"
            )

        return v

    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://opennotes:opennotes@localhost:5432/opennotes"
    )

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v.startswith("postgresql+asyncpg://"):
            raise ValueError(
                "DATABASE_URL must use asyncpg driver: postgresql+asyncpg://user:pass@host:port/db"
            )
        return v

    DB_POOL_SIZE: int = Field(
        default=5, description="Database connection pool size (number of connections to maintain)"
    )
    DB_POOL_MAX_OVERFLOW: int = Field(
        default=10, description="Maximum number of connections that can be created beyond pool_size"
    )
    DB_POOL_TIMEOUT: int = Field(
        default=30, description="Timeout in seconds for getting a connection from the pool"
    )
    DB_POOL_RECYCLE: int = Field(
        default=3600,
        description="Time in seconds after which to recycle connections (prevents stale connections)",
    )

    REDIS_URL: str = Field(default="redis://localhost:6379/0")
    REDIS_MAX_CONNECTIONS: int = Field(default=10)
    REDIS_SOCKET_TIMEOUT: int = Field(default=5)
    REDIS_SOCKET_CONNECT_TIMEOUT: int = Field(default=5)
    REDIS_RETRY_ON_TIMEOUT: bool = Field(default=True)
    REDIS_REQUIRE_TLS: bool = Field(
        default=True,
        description="Require TLS for Redis in production (rediss:// URLs).",
    )
    REDIS_CA_CERT_PATH: str | None = Field(
        default=None,
        description="Path to CA certificate for Redis TLS verification. Required for GCP Memorystore.",
    )

    CACHE_SCORING_TTL: int = Field(
        default=300, description="SHORT (5min): Computed scoring results"
    )
    CACHE_USER_PROFILE_TTL: int = Field(
        default=3600, description="LONG (1hr): User profile data (static)"
    )
    CACHE_DEFAULT_TTL: int = Field(
        default=600, description="MEDIUM (10min): General-purpose caching"
    )

    SESSION_TTL: int = Field(
        default=86400, description="SESSION (24hr): User authentication sessions"
    )
    SESSION_REFRESH_TTL: int = Field(
        default=604800, description="REFRESH (7d): Session refresh tokens"
    )

    NATS_URL: str = Field(default="nats://localhost:4222")
    nats_servers_raw: str | None = Field(
        default=None,
        validation_alias="NATS_SERVERS",
        exclude=True,
        description="Comma-separated list of NATS server URLs for cluster failover. "
        "If not set, falls back to NATS_URL. "
        "Example: nats://10.0.0.1:4222,nats://10.0.0.2:4222,nats://10.0.0.3:4222",
    )

    @computed_field
    @property
    def NATS_SERVERS(self) -> list[str]:  # noqa: N802 - uppercase for config consistency
        """Parse NATS_SERVERS into a list of server URLs.

        If NATS_SERVERS env var is set, parses comma-separated URLs.
        Otherwise, falls back to NATS_URL as a single-element list.
        This enables cluster failover while maintaining backward compatibility.
        """
        if self.nats_servers_raw:
            servers = [s.strip() for s in self.nats_servers_raw.split(",") if s.strip()]
            if servers:
                return servers
        return [self.NATS_URL]

    NATS_MAX_RECONNECT_ATTEMPTS: int = Field(default=10)
    NATS_RECONNECT_WAIT: int = Field(default=2)
    NATS_CONNECT_TIMEOUT: int = Field(
        default=10,
        description="Timeout in seconds for each NATS connection attempt. "
        "Default nats-py timeout is 2s which is insufficient for Cloud Run → GCE VPC.",
    )
    NATS_SUBSCRIBE_TIMEOUT: float = Field(
        default=60.0,
        description="Timeout in seconds for JetStream subscribe operations during startup",
    )
    NATS_USERNAME: str | None = Field(
        default=None,
        description="NATS authentication username. Optional for development, required for production.",
    )
    NATS_PASSWORD: str | None = Field(
        default=None,
        description="NATS authentication password. Optional for development, required for production.",
    )
    NATS_STREAM_NAME: str = Field(default="OPENNOTES")
    NATS_CONSUMER_NAME: str = Field(default="opennotes-server")
    NATS_MAX_DELIVER_ATTEMPTS: int = Field(
        default=5, description="Maximum delivery attempts before message is considered poison"
    )
    NATS_ACK_WAIT_SECONDS: int = Field(
        default=30, description="Timeout in seconds before message redelivery"
    )
    NATS_PUBLISH_MAX_RETRIES: int = Field(
        default=3, description="Maximum retry attempts for transient publish failures"
    )
    NATS_PUBLISH_RETRY_MIN_WAIT: float = Field(
        default=1.0, description="Minimum wait time in seconds between retries"
    )
    NATS_PUBLISH_RETRY_MAX_WAIT: float = Field(
        default=10.0, description="Maximum wait time in seconds between retries"
    )
    NATS_HANDLER_TIMEOUT: int = Field(
        default=30, description="Timeout in seconds for event handler execution"
    )
    NATS_STREAM_MAX_AGE_SECONDS: int = Field(
        default=86400 * 7, description="Maximum age of messages in stream (default: 7 days)"
    )
    NATS_STREAM_MAX_MESSAGES: int = Field(
        default=1_000_000, description="Maximum number of messages stored in stream"
    )
    NATS_STREAM_MAX_BYTES: int = Field(
        default=1_073_741_824, description="Maximum total size of messages in stream (default: 1GB)"
    )
    NATS_STREAM_DUPLICATE_WINDOW_SECONDS: int = Field(
        default=120, description="Duplicate message detection window (default: 2 minutes)"
    )

    TASKIQ_STREAM_NAME: str = Field(
        default="OPENNOTES_TASKS",
        description="NATS JetStream stream name for taskiq background tasks",
    )
    TASKIQ_STREAM_MAX_AGE_SECONDS: int = Field(
        default=604800,
        description="Maximum age in seconds for messages in TaskIQ stream (default: 7 days). "
        "Messages older than this are automatically deleted to prevent stale message accumulation.",
    )
    TASKIQ_RESULT_EXPIRY: int = Field(
        default=3600,
        description="Time in seconds to keep task results in Redis (default: 1 hour)",
    )
    TASKIQ_DEFAULT_RETRY_COUNT: int = Field(
        default=3,
        description="Default number of retries for failed tasks",
    )
    TASKIQ_RETRY_DELAY: int = Field(
        default=5,
        description="Delay in seconds between task retries",
    )

    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = Field(default=5)
    CIRCUIT_BREAKER_TIMEOUT: int = Field(default=60)
    CIRCUIT_BREAKER_EXPECTED_EXCEPTION: str = Field(default="Exception")

    WEBHOOK_RATE_LIMIT_PER_COMMUNITY_SERVER: int = Field(default=100)
    WEBHOOK_RATE_LIMIT_WINDOW: int = Field(default=60)

    INTERACTION_CACHE_TTL: int = Field(
        default=300, description="SHORT (5min): Webhook interaction deduplication"
    )
    INTERACTION_RESPONSE_TIMEOUT: int = Field(default=3)

    QUEUE_MAX_RETRIES: int = Field(default=3)
    QUEUE_RETRY_DELAY: int = Field(default=1)
    QUEUE_RETRY_BACKOFF: float = Field(default=2.0)

    JWT_SECRET_KEY: str = Field(
        ...,
        min_length=32,
        description="Secret key for JWT token signing - REQUIRED in production. "
        "Must be at least 32 characters for security. "
        "Generate with: python -c 'import secrets; print(secrets.token_urlsafe(32))'",
    )
    JWT_ALGORITHM: str = Field(default="HS256", description="JWT signing algorithm")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=30, description="Access token expiration time in minutes"
    )
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(
        default=7, description="Refresh token expiration time in days"
    )
    MAX_TOKEN_AGE_SECONDS: int | None = Field(
        default=None,
        description="Maximum allowed age for tokens in seconds. "
        "Tokens older than this will be rejected even if not expired. "
        "Set to None to disable max age validation. "
        "Useful for detecting token replay attacks.",
    )

    CREDENTIALS_ENCRYPTION_KEY: str = Field(
        ...,
        description="Encryption key for sensitive credential data - REQUIRED in production. "
        "Must be a valid Fernet key (URL-safe base64-encoded 32 bytes). "
        "Generate with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'",
    )

    @field_validator("CREDENTIALS_ENCRYPTION_KEY")
    @classmethod
    def validate_credentials_encryption_key(cls, v: str) -> str:
        if not v:
            return v

        try:
            Fernet(v.encode())
        except Exception as e:
            raise ValueError(
                f"CREDENTIALS_ENCRYPTION_KEY must be a valid Fernet key. "
                f"Generate one with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())' "
                f"Error: {e}"
            ) from e

        return v

    ENCRYPTION_MASTER_KEY: str = Field(
        ...,
        description="Master encryption key for LLM API keys - REQUIRED in production. "
        "Must be URL-safe base64-encoded 32 bytes (256 bits) with high entropy. "
        "Generate with: python -c 'import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())'",
    )

    @field_validator("ENCRYPTION_MASTER_KEY")
    @classmethod
    def validate_encryption_master_key(cls, v: str) -> str:
        if not v:
            return v

        try:
            key_bytes = base64.urlsafe_b64decode(v.encode())
        except Exception as e:
            raise ValueError(
                f"ENCRYPTION_MASTER_KEY must be valid URL-safe base64. "
                f"Generate with: python -c 'import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())' "
                f"Error: {e}"
            ) from e

        if len(key_bytes) != 32:
            raise ValueError(
                f"ENCRYPTION_MASTER_KEY must decode to exactly 32 bytes (256 bits). "
                f"Got {len(key_bytes)} bytes. "
                f"Generate with: python -c 'import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())'"
            )

        return v

    KEY_ROTATION_INTERVAL_DAYS: int = Field(
        default=90,
        description="Interval in days between automatic encryption key rotations. "
        "Keys older than this will be flagged for rotation.",
    )
    KEY_MAX_AGE_DAYS: int = Field(
        default=180,
        description="Maximum allowed encryption key age in days before alerting. "
        "Keys older than this will trigger warning alerts.",
    )
    KEY_ROTATION_ENABLED: bool = Field(
        default=True,
        description="Enable automatic key rotation tracking and alerting.",
    )

    @staticmethod
    def _calculate_shannon_entropy(data: bytes) -> float:
        if not data:
            return 0.0

        byte_counts = Counter(data)
        total_bytes = len(data)

        entropy = 0.0
        for count in byte_counts.values():
            probability = count / total_bytes
            entropy -= probability * math.log2(probability)

        return entropy

    RATE_LIMIT_PER_MINUTE: int = Field(
        default=60, description="Default rate limit per minute per user"
    )
    RATE_LIMIT_ENABLED: bool = Field(default=True, description="Enable rate limiting")

    MAX_REQUEST_SIZE_BYTES: int = Field(
        default=1048576, description="Default maximum request body size in bytes (1MB)"
    )
    MAX_NOTE_SIZE_BYTES: int = Field(
        default=102400, description="Maximum request body size for note creation in bytes (100KB)"
    )
    MAX_WEBHOOK_SIZE_BYTES: int = Field(
        default=5242880, description="Maximum request body size for webhook payloads in bytes (5MB)"
    )

    MIN_RATINGS_NEEDED: int = Field(
        default=5,
        description="Minimum number of ratings before a note can receive CRH/CRNH status. "
        "This value should match the Community Notes scoring algorithm default "
        "(communitynotes/scoring/src/scoring/mf_base_scorer.py::minRatingsNeeded)",
    )
    MIN_RATERS_PER_NOTE: int = Field(
        default=5,
        description="Minimum number of unique raters required per note. "
        "This value should match the Community Notes scoring algorithm default "
        "(communitynotes/scoring/src/scoring/mf_base_scorer.py::minNumRatersPerNote)",
    )

    SCORING_TIER_OVERRIDE: str | None = Field(
        default=None,
        description="Override automatic tier detection. Valid values: "
        "minimal, limited, basic, intermediate, advanced, full. "
        "If None, tier is automatically selected based on note count.",
    )
    SCORER_TIMEOUT_SECONDS: int = Field(
        default=30,
        description="Maximum time in seconds to wait for scorer execution before falling back to simpler tier.",
    )

    BAYESIAN_CONFIDENCE_PARAM: float = Field(
        default=2.0,
        description="Bayesian Average confidence parameter (C). Controls weight of prior mean. "
        "Higher values = more conservative, slower to move from prior. "
        "Used in Tier 0 (0-200 notes) for bootstrap phase scoring.",
    )
    BAYESIAN_PRIOR_MEAN: float = Field(
        default=0.5,
        description="Bayesian Average prior mean (m). Starting score for notes with no ratings. "
        "Neutral value of 0.5 means no initial bias. "
        "After 50+ notes have ratings, this can be updated to system average.",
    )
    BAYESIAN_MIN_RATINGS_FOR_CONFIDENCE: int = Field(
        default=5,
        description="Minimum ratings needed before Bayesian scorer marks confidence as 'standard'. "
        "Below this threshold, confidence is marked as 'provisional'. "
        "Aligns with MIN_RATINGS_NEEDED for consistency.",
    )

    ENABLE_METRICS: bool = Field(default=True, description="Enable metrics middleware")
    ENABLE_TRACING: bool = Field(default=True, description="Enable OpenTelemetry tracing")
    ENABLE_JSON_LOGGING: bool = Field(default=True, description="Enable JSON structured logging")

    OTLP_ENDPOINT: str | None = Field(
        default=None,
        description="OpenTelemetry OTLP endpoint (e.g., http://tempo:4317)",
        validation_alias=AliasChoices("OTEL_EXPORTER_OTLP_ENDPOINT", "OTLP_ENDPOINT"),
    )
    OTLP_INSECURE: bool = Field(
        default=False, description="Use insecure OTLP connection (only for local development)"
    )
    ENABLE_CONSOLE_TRACING: bool = Field(
        default=False, description="Enable console span export for debugging"
    )
    OTEL_LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] | None = Field(
        default=None,
        description="OpenTelemetry SDK log level for debugging export issues. "
        "Valid values: DEBUG, INFO, WARNING, ERROR, or None to use default. "
        "When set to DEBUG, enables verbose logging for exporters and SDK internals.",
    )
    TRACING_SAMPLE_RATE: float = Field(
        default=1.0,
        description="Trace sampling rate (0.0-1.0). 1.0 = 100% of traces sampled (full observability). "
        "Set to lower value (e.g., 0.1) in high-volume production to reduce costs.",
        ge=0.0,
        le=1.0,
        validation_alias=AliasChoices("TRACING_SAMPLE_RATE", "TRACE_SAMPLE_RATE"),
    )

    @field_validator("TRACING_SAMPLE_RATE", mode="before")
    @classmethod
    def warn_deprecated_trace_sample_rate(cls, v: Any) -> Any:
        if os.getenv("TRACE_SAMPLE_RATE") and not os.getenv("TRACING_SAMPLE_RATE"):
            warnings.warn(
                "TRACE_SAMPLE_RATE is deprecated and will be removed in a future version. "
                "Please use TRACING_SAMPLE_RATE instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        return v

    OTLP_HEADERS: str | None = Field(
        default=None,
        description="OTLP exporter headers in 'key=value,key2=value2' format for authentication",
        validation_alias=AliasChoices("OTEL_EXPORTER_OTLP_HEADERS", "OTLP_HEADERS"),
    )

    PYROSCOPE_ENABLED: bool = Field(
        default=False,
        description="Enable continuous profiling via Pyroscope. "
        "Requires PYROSCOPE_SERVER_ADDRESS to be set.",
    )
    PYROSCOPE_SERVER_ADDRESS: str | None = Field(
        default=None,
        description="Pyroscope server address (e.g., 'http://pyroscope:4040' for self-hosted, "
        "'https://profiles-prod-001.grafana.net' for Grafana Cloud). "
        "Required when PYROSCOPE_ENABLED is True.",
    )
    PYROSCOPE_TENANT_ID: str | None = Field(
        default=None,
        description="Tenant ID for multi-tenant Pyroscope backends (e.g., Middleware.io account ID). "
        "Used for backends that require tenant identification instead of basic auth.",
    )
    PYROSCOPE_AUTH_TOKEN: str | None = Field(
        default=None,
        repr=False,
        description="Auth token for Pyroscope backends that use token-based authentication. "
        "Optional for self-hosted Pyroscope without auth.",
    )
    PYROSCOPE_APPLICATION_NAME: str | None = Field(
        default=None,
        description="Application name for Pyroscope profiles. Defaults to PROJECT_NAME if not set.",
    )
    PYROSCOPE_SAMPLE_RATE: int = Field(
        default=100,
        description="Profiling sample rate in Hz. Default is 100 samples per second.",
        ge=1,
        le=1000,
    )
    PYROSCOPE_DETECT_SUBPROCESSES: bool = Field(
        default=False,
        description="Detect and profile subprocesses started by the main process.",
    )
    PYROSCOPE_ONCPU: bool = Field(
        default=True,
        description="Report CPU time only (excludes wall-clock time during I/O waits).",
    )
    PYROSCOPE_GIL_ONLY: bool = Field(
        default=True,
        description="Only include traces for threads holding the Global Interpreter Lock.",
    )
    PYROSCOPE_ENABLE_LOGGING: bool = Field(
        default=False,
        description="Enable Pyroscope SDK logging for debugging.",
    )

    USE_GCP_EXPORTERS: bool = Field(
        default=True,
        description="Use GCP-native exporters on Cloud Run (set False to force OTLP)",
    )

    TRACELOOP_ENABLED: bool = Field(
        default=True,
        description="Enable Traceloop SDK for LLM observability. "
        "Provides automatic instrumentation of LiteLLM, OpenAI, and Anthropic calls "
        "with GenAI semantic conventions (gen_ai.*, llm.*).",
    )
    TRACELOOP_TRACE_CONTENT: bool = Field(
        default=False,
        description="Enable logging of prompts and completions in traces. "
        "Set to False (default) for production to avoid logging sensitive data. "
        "Set to True for development/debugging to see full prompt/completion content.",
    )

    OTEL_SERVICE_NAME: str | None = Field(
        default=None,
        description="Service name for OpenTelemetry. Defaults to PROJECT_NAME if not set.",
    )
    OTEL_SDK_DISABLED: bool = Field(
        default=False,
        description="Disable OpenTelemetry SDK. Useful for tests or environments without collectors.",
    )

    OTEL_BSP_MAX_QUEUE_SIZE: int = Field(
        default=4096,
        description="Maximum queue size for BatchSpanProcessor. "
        "Prevents data loss during traffic spikes. Default: 4096 (2x OTel default).",
        ge=1,
    )
    OTEL_BSP_SCHEDULE_DELAY_MILLIS: int = Field(
        default=2500,
        description="Delay in milliseconds between consecutive exports. "
        "Default: 2500ms (half OTel default for better latency).",
        ge=100,
    )
    OTEL_BSP_MAX_EXPORT_BATCH_SIZE: int = Field(
        default=1024,
        description="Maximum batch size for span exports. "
        "Must be <= max_queue_size. Default: 1024 (matches Cloud Trace capability).",
        ge=1,
    )
    OTEL_BSP_EXPORT_TIMEOUT_MILLIS: int = Field(
        default=30000,
        description="Maximum time in milliseconds for an export operation. Default: 30000.",
        ge=1000,
    )
    OTEL_EXPORTER_COMPRESSION: Literal["none", "gzip"] = Field(
        default="gzip",
        description="OTLP exporter compression. 'gzip' provides 60-80% bandwidth reduction.",
    )
    OTEL_SHUTDOWN_FLUSH_TIMEOUT_MILLIS: int = Field(
        default=30000,
        description="Timeout in milliseconds for force_flush() during shutdown. Default: 30000.",
        ge=1000,
    )

    GCP_PROJECT_ID: str | None = Field(
        default=None,
        description="GCP project ID for Cloud Trace log correlation. "
        "Auto-detected from GOOGLE_CLOUD_PROJECT environment variable in Cloud Run.",
        validation_alias=AliasChoices("GCP_PROJECT_ID", "GOOGLE_CLOUD_PROJECT"),
    )
    VERTEXAI_PROJECT: str | None = Field(
        default=None,
        description="GCP project ID for Vertex AI. Required when using vertex_ai/ model prefix. "
        "Set automatically on Cloud Run via env var.",
    )
    VERTEXAI_LOCATION: str = Field(
        default="us-central1",
        description="GCP region for Vertex AI API calls",
    )

    SMTP_HOST: str = Field(default="localhost", description="SMTP server hostname")
    SMTP_PORT: int = Field(default=587, description="SMTP server port (587 for TLS, 465 for SSL)")
    SMTP_USERNAME: str | None = Field(default=None, description="SMTP authentication username")
    SMTP_PASSWORD: str | None = Field(default=None, description="SMTP authentication password")
    SMTP_FROM_EMAIL: str = Field(
        default="noreply@opennotes.com", description="From email address for outgoing emails"
    )
    SMTP_FROM_NAME: str = Field(default="OpenNotes", description="From name for outgoing emails")
    SMTP_USE_TLS: bool = Field(default=True, description="Use TLS for SMTP connection")
    EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS: int = Field(
        default=24, description="Email verification token expiration time in hours"
    )

    EMBEDDING_MODEL: LiteLLMModelId = Field(
        default="openai/text-embedding-3-small",
        description="Embedding model in provider/model format for LiteLLM compatibility",
    )
    EMBEDDING_DIMENSIONS: int = Field(
        default=1536,
        description="Embedding vector dimensions (must match EMBEDDING_MODEL output size)",
        gt=0,
    )
    EMBEDDING_CACHE_TTL_SECONDS: int = Field(
        default=3600, description="Cache TTL for embeddings in seconds (1 hour default)", gt=0
    )
    EMBEDDING_CLIENT_CACHE_MAX_SIZE: int = Field(
        default=100,
        description="Maximum size of OpenAI client cache for embedding service",
        gt=0,
    )
    EMBEDDING_CLIENT_CACHE_TTL_SECONDS: int = Field(
        default=3600, description="TTL for OpenAI client cache in seconds (1 hour default)", gt=0
    )
    OPENAI_API_KEY: str | None = Field(
        default=None,
        description="Global OpenAI API key for fallback when community servers don't have their own key configured",
    )
    ANTHROPIC_API_KEY: str | None = Field(
        default=None,
        description="Global Anthropic API key for fallback when community servers don't have their own key configured",
    )

    DEFAULT_MINI_MODEL: LiteLLMModelId = Field(
        default="openai/gpt-5-mini",
        description="Default mini/fast model for quick tasks (provider/model format for LiteLLM compatibility)",
    )
    DEFAULT_FULL_MODEL: LiteLLMModelId = Field(
        default="openai/gpt-5.1",
        description="Default full-capability model for complex tasks (provider/model format for LiteLLM compatibility)",
    )

    INTERNAL_SERVICE_SECRET: str = Field(
        default="",
        description="Shared secret for internal service-to-service authentication. "
        "Used to validate that X-Discord-* headers come from trusted internal services (e.g., Discord bot). "
        "Must be at least 32 characters in production. "
        "Generate with: python -c 'import secrets; print(secrets.token_urlsafe(32))'",
    )
    SIMILARITY_SEARCH_DEFAULT_THRESHOLD: float = Field(
        default=0.6,
        description="Default minimum similarity score (0.0-1.0) for embedding similarity search",
        ge=0.0,
        le=1.0,
    )
    PREVIOUSLY_SEEN_AUTOPUBLISH_THRESHOLD: float = Field(
        default=0.9,
        description="Default similarity threshold (0.0-1.0) for auto-publishing previously seen notes. "
        "When a message matches a previously seen message at this threshold, "
        "automatically republish the existing note.",
        ge=0.0,
        le=1.0,
    )
    PREVIOUSLY_SEEN_AUTOREQUEST_THRESHOLD: float = Field(
        default=0.75,
        description="Default similarity threshold (0.0-1.0) for auto-requesting notes on previously seen content. "
        "When a message matches a previously seen message at this threshold (but below autopublish), "
        "automatically trigger a note request.",
        ge=0.0,
        le=1.0,
    )

    VISION_MODEL: LiteLLMModelId = Field(
        default="openai/gpt-5.1",
        description="Vision model in provider/model format for LiteLLM compatibility",
    )
    VISION_PROMPT: str = Field(
        default="Describe this image concisely for fact-checking purposes. Focus on text, claims, or notable content. Be brief.",
        description="Prompt for image description generation",
    )
    VISION_CACHE_TTL_SECONDS: int = Field(
        default=86400,
        description="Cache TTL for vision descriptions in seconds (24 hours default)",
        gt=0,
    )
    VISION_MAX_TOKENS: int = Field(
        default=2000,
        description="Maximum tokens for vision descriptions (needs headroom for reasoning models)",
        gt=0,
    )
    VISION_DETAIL_LEVEL: str = Field(
        default="auto",
        description="Default vision detail level: 'low', 'high', or 'auto'",
    )

    # Relevance Check Settings (for vibe check hybrid search)
    RELEVANCE_CHECK_ENABLED: bool = Field(
        default=True,
        description="Enable LLM-based relevance filtering for hybrid search results",
    )
    RELEVANCE_CHECK_MODEL: LiteLLMModelId = Field(
        default="openai/gpt-5-mini",
        description="LLM model in provider/model format for relevance checking (should be fast and cheap)",
    )
    RELEVANCE_CHECK_MAX_TOKENS: int = Field(
        default=2000,
        description="Maximum tokens for relevance check responses (needs headroom for reasoning models)",
        gt=0,
    )
    RELEVANCE_CHECK_TIMEOUT: float = Field(
        default=30.0,
        description="Timeout in seconds for relevance check LLM calls",
        gt=0,
    )
    RELEVANCE_CHECK_USE_OPTIMIZED_PROMPT: bool = Field(
        default=True,
        description="Use DSPy-optimized prompts for relevance checking (task-966)",
    )

    # AI Note Writing Settings
    AI_NOTE_WRITING_ENABLED: bool = Field(
        default=True,
        description="Enable automatic AI-generated community notes for fact-check matches",
    )
    AI_NOTE_WRITER_MODEL: LiteLLMModelId = Field(
        default="openai/gpt-5.1",
        description="AI note generation model in provider/model format for LiteLLM compatibility",
    )
    AI_NOTE_WRITER_SYSTEM_PROMPT: str = Field(
        default="You are a helpful assistant that writes concise, informative community notes. "
        "Your goal is to provide context and fact-check information in a neutral, factual tone. "
        "Keep notes clear, accurate, and easy to understand.",
        description="System prompt for AI note generation",
    )

    BULK_CONTENT_SCAN_REPROMPT_DAYS: int = Field(
        default=90,
        ge=1,
        le=365,
        description="Days after which to re-prompt for bulk content scan. "
        "If a community server has no completed scan within this window, "
        "the system will suggest running a bulk scan. Valid range: 1-365 days.",
    )

    BULK_SCAN_RATE_LIMIT_PER_HOUR: int = Field(
        default=5,
        description="Maximum number of bulk content scans per hour per user. "
        "Bulk scans are computationally expensive, so this limit prevents abuse.",
    )

    FLASHPOINT_CONTEXT_CACHE_TTL: int = Field(
        default=1800,
        description="TTL in seconds for cross-batch flashpoint context cache (30 minutes default). "
        "Controls how long previous batch messages are available as context for flashpoint detection.",
        ge=60,
    )
    FLASHPOINT_CONTEXT_CACHE_MAX_MESSAGES: int = Field(
        default=20,
        description="Maximum number of messages per channel stored in the cross-batch flashpoint context cache. "
        "Older messages are evicted when this limit is exceeded.",
        ge=1,
        le=100,
    )

    DBOS_APP_NAME: str = Field(
        default="opennotes-server",
        description="Application name for DBOS (lowercase, alphanumeric, dashes, underscores only)",
    )
    DBOS_CONDUCTOR_KEY: str | None = Field(
        default=None,
        description="DBOS Conductor API key for workflow observability and management",
        repr=False,
    )
    TOKEN_POOL_CAPACITY: int = Field(
        default=12,
        description="Default token pool capacity for DBOS workflow concurrency control",
    )

    @model_validator(mode="after")
    def validate_encryption_key_entropy(self) -> Settings:
        if self.TESTING or not self.ENCRYPTION_MASTER_KEY:
            return self

        try:
            key_bytes = base64.urlsafe_b64decode(self.ENCRYPTION_MASTER_KEY.encode())
        except Exception:
            return self

        if len(key_bytes) != 32:
            return self

        entropy = self._calculate_shannon_entropy(key_bytes)
        min_entropy = 4.5
        if entropy < min_entropy:
            raise ValueError(
                f"ENCRYPTION_MASTER_KEY has insufficient entropy ({entropy:.2f} bits/byte, minimum {min_entropy}). "
                f"The key appears non-random. "
                f"Generate a cryptographically secure key with: "
                f"python -c 'import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())'"
            )

        unique_bytes = len(set(key_bytes))
        if unique_bytes < 16:
            raise ValueError(
                f"ENCRYPTION_MASTER_KEY has too few unique bytes ({unique_bytes}/32). "
                f"The key appears to have a pattern or low diversity. "
                f"Generate a cryptographically secure key with: "
                f"python -c 'import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())'"
            )

        return self

    @model_validator(mode="after")
    def validate_production_settings(self) -> Settings:
        if self.ENVIRONMENT == "production":
            if not self.JWT_SECRET_KEY or len(self.JWT_SECRET_KEY) < 32:
                raise ValueError(
                    "JWT_SECRET_KEY must be set and at least 32 characters in production. "
                    "Generate a secure key with: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
                )

            if self.JWT_SECRET_KEY in {
                "dev-secret-key-change-in-production",
                "change-me",
                "secret",
                "your-secret-key",
            }:
                raise ValueError(
                    "JWT_SECRET_KEY appears to be a placeholder value. "
                    "You must use a cryptographically secure random key in production."
                )

            if not self.CREDENTIALS_ENCRYPTION_KEY:
                raise ValueError(
                    "CREDENTIALS_ENCRYPTION_KEY must be set in production. "
                    "Generate a secure key with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
                )

            if not self.ENCRYPTION_MASTER_KEY:
                raise ValueError(
                    "ENCRYPTION_MASTER_KEY must be set in production. "
                    "Generate a secure key with: python -c 'import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())'"
                )

            if self.DEBUG:
                raise ValueError(
                    "DEBUG must be False in production environment. "
                    "Debug mode exposes sensitive information including stack traces, "
                    "OpenAPI documentation, and database query logging."
                )

            if not self.INTERNAL_SERVICE_SECRET or len(self.INTERNAL_SERVICE_SECRET) < 32:
                raise ValueError(
                    "INTERNAL_SERVICE_SECRET must be set and at least 32 characters in production. "
                    "This secret is required to prevent authentication bypass via X-Discord-* header spoofing. "
                    "Generate a secure key with: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
                )

        return self

    @model_validator(mode="after")
    def validate_vertex_ai_config(self) -> Settings:
        if self.TESTING:
            return self
        model_fields = [
            self.DEFAULT_MINI_MODEL,
            self.DEFAULT_FULL_MODEL,
            self.VISION_MODEL,
            self.RELEVANCE_CHECK_MODEL,
            self.AI_NOTE_WRITER_MODEL,
        ]
        has_vertex_ai = any(m.provider == "vertex_ai" for m in model_fields)
        if has_vertex_ai and not self.VERTEXAI_PROJECT:
            raise ValueError(
                "VERTEXAI_PROJECT must be set when using vertex_ai/ model prefix. "
                "Set VERTEXAI_PROJECT to your GCP project ID."
            )
        return self

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"


def get_settings() -> Settings:
    """
    Get the application settings instance.

    Returns a singleton Settings instance. The singleton pattern is enforced
    at the class level via __new__(), ensuring only one instance exists
    regardless of how many times Settings() is called.

    This allows environment variables (e.g., from testcontainers) to be set
    before the first access, after which the same instance is always returned.

    Returns:
        Settings: The singleton settings instance
    """
    return cast(Settings, Settings())


def _clear_settings_cache() -> None:
    """
    Clear the cached settings instance.

    This resets the singleton to allow tests to create a fresh Settings instance
    on next access, picking up any environment variable changes. Primarily used by tests.

    Note: This breaks the singleton contract and should only be used in test fixtures.
    """
    global _settings_instance, _settings_initialized  # noqa: PLW0603 - Singleton reset requires module-level state
    _settings_instance = None
    _settings_initialized = False


get_settings.cache_clear = _clear_settings_cache  # pyright: ignore[reportFunctionMemberAccess]


def __getattr__(name: str) -> Any:
    """
    Module-level __getattr__ for lazy attribute access (PEP 562).

    Enables lazy initialization of 'settings' - it won't be created until
    first accessed, allowing testcontainers and other fixtures to set
    environment variables before Settings validation runs.

    Args:
        name: Attribute name being accessed

    Returns:
        The requested module attribute

    Raises:
        AttributeError: If the attribute doesn't exist
    """
    if name == "settings":
        return get_settings()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
