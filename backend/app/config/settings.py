"""Application settings loaded from environment variables."""

from enum import StrEnum
from functools import lru_cache

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ApplyMode(StrEnum):
    """Job application submission mode."""

    AUTONOMOUS = "autonomous"
    REVIEW = "review"
    BATCH = "batch"


class Environment(StrEnum):
    """Application environment."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class LLMSettings(BaseSettings):
    """LLM provider configuration."""

    model_config = SettingsConfigDict(env_prefix="LLM__")

    portkey_api_key: SecretStr = SecretStr("")
    openai_api_key: SecretStr = SecretStr("")
    groq_api_key: SecretStr = SecretStr("")
    gemini_api_key: SecretStr = SecretStr("")
    openrouter_api_key: SecretStr = SecretStr("")
    github_token: SecretStr = SecretStr("")
    preferred_provider: str = "openai"
    fallback_providers: list[str] = ["groq", "openrouter"]
    default_model: str = "gpt-4o"
    temperature: float = 0.7
    max_tokens: int = 4096

    @field_validator("temperature")
    @classmethod
    def validate_temperature(cls, v: float) -> float:
        """Clamp temperature to valid range."""
        return max(0.0, min(2.0, v))

    @field_validator("max_tokens")
    @classmethod
    def validate_max_tokens(cls, v: int) -> int:
        """Ensure max_tokens is positive."""
        return max(1, v)


class BrowserSettings(BaseSettings):
    """Browser automation configuration."""

    model_config = SettingsConfigDict(env_prefix="BROWSER__")

    headless: bool = True
    max_parallel: int = 3
    user_data_dir: str = "./data/sessions/chrome_profile"
    keep_alive: bool = True
    max_steps: int = 50
    max_failures: int = 3
    step_timeout: int = 120
    use_vision: str = "auto"

    @field_validator("max_parallel")
    @classmethod
    def validate_max_parallel(cls, v: int) -> int:
        """Clamp parallelism to 1-5 range."""
        return max(1, min(5, v))


class FeatureFlagsSettings(BaseSettings):
    """Runtime feature flags for incremental rollouts."""

    model_config = SettingsConfigDict(env_prefix="FEATURE__")

    tenant_enforcement: bool = False
    workflow_v2_enabled: bool = False
    audit_log_enabled: bool = True
    scheduler_enabled: bool = False
    watchdog_enabled: bool = True
    manual_checkpoint_mode: bool = True
    allow_legacy_unscoped_writes: bool = False
    strict_tenant_startup_validation: bool = True


class AuthSettings(BaseSettings):
    """Authentication and principal resolution configuration."""

    model_config = SettingsConfigDict(env_prefix="AUTH__")

    token_secret: SecretStr = SecretStr("dev-insecure-change-me")
    token_ttl_seconds: int = 3600
    allow_legacy_header_auth: bool = True


class Settings(BaseSettings):
    """Root application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = "sqlite+aiosqlite:///data/db/autoapply.db"
    redis_url: str = "redis://localhost:6379/0"

    # Application behavior
    apply_mode: ApplyMode = ApplyMode.REVIEW
    min_ats_score: float = 0.75
    environment: Environment = Environment.DEVELOPMENT
    log_level: str = "INFO"

    # Nested settings
    llm: LLMSettings = LLMSettings()
    browser: BrowserSettings = BrowserSettings()
    feature_flags: FeatureFlagsSettings = FeatureFlagsSettings()
    auth: AuthSettings = AuthSettings()

    # Job discovery
    exa_api_key: SecretStr = SecretStr("")

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # Artifact storage
    artifact_storage_provider: str = "local"
    artifact_storage_local_root: str = "./data/artifacts"

    artifact_storage_s3_bucket: str = ""
    artifact_storage_s3_region: str = "us-east-1"
    artifact_storage_s3_endpoint_url: str = ""
    artifact_storage_s3_access_key_id: SecretStr = SecretStr("")
    artifact_storage_s3_secret_access_key: SecretStr = SecretStr("")
    artifact_storage_s3_session_token: SecretStr = SecretStr("")
    artifact_storage_presign_ttl_seconds: int = 900

    # Startup behavior
    auto_create_schema_on_startup: bool = False

    @field_validator("min_ats_score")
    @classmethod
    def validate_min_ats_score(cls, v: float) -> float:
        """Clamp ATS score threshold to 0-1 range."""
        return max(0.0, min(1.0, v))

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Normalize log level to uppercase."""
        return v.upper()

    @property
    def strict_tenant_enforcement(self) -> bool:
        """Effective strict enforcement in runtime (non-dev defaults to strict)."""
        return self.feature_flags.tenant_enforcement or self.environment != Environment.DEVELOPMENT

    @model_validator(mode="after")
    def validate_production_safety(self) -> "Settings":
        """Fail fast on broken high-risk production/staging configs."""
        if self.environment in {Environment.STAGING, Environment.PRODUCTION}:
            if self.auth.token_secret.get_secret_value() in {"", "dev-insecure-change-me"}:
                raise ValueError("AUTH__TOKEN_SECRET must be set to a non-default value in staging/production")
            if self.redis_url.strip() == "":
                raise ValueError("REDIS_URL must be configured in staging/production")
            if self.database_url.strip() == "":
                raise ValueError("DATABASE_URL must be configured in staging/production")
            provider = self.artifact_storage_provider.lower().strip()
            if provider == "s3" and (
                not self.artifact_storage_s3_bucket.strip()
                or not self.artifact_storage_s3_access_key_id.get_secret_value().strip()
                or not self.artifact_storage_s3_secret_access_key.get_secret_value().strip()
            ):
                raise ValueError("S3 artifact storage requires bucket/access key/secret key in staging/production")
        return self

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get cached application settings singleton."""
    return Settings()
