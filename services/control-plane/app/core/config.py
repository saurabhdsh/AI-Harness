"""Application settings loaded from environment."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "TCS AI Harness Control Plane"
    app_env: str = "development"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"

    database_url: str = "postgresql+asyncpg://harness:harness@localhost:5432/harness"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "change-me-in-production-harness-jwt-secret"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 12

    auth_demo: bool = True
    demo_admin_email: str = "admin@harness.local"
    demo_admin_password: str = "harness-admin"

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    langgraph_agent_url: str = "http://langgraph-agent:8080"
    http_timeout_seconds: float = 90.0

    # When true, create_all on startup if alembic not applied (demo only)
    auto_create_tables: bool = True

    # Smart onboarding — local project path allowlist (colon-separated) + upload dir
    project_allowlist: str = ""
    upload_dir: str = "data/uploads"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
