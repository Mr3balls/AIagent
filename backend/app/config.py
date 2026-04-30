from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Tender AI Backend"
    app_version: str = "1.0.0"
    debug: bool = False

    api_prefix: str = "/api/v1"

    postgres_user: str = Field(default="postgres")
    postgres_password: str = Field(default="postgres")
    postgres_db: str = Field(default="tender_ai")
    postgres_host: str = Field(default="db")
    postgres_port: int = Field(default=5432)

    redis_host: str = Field(default="redis")
    redis_port: int = Field(default=6379)

    openai_api_key: str = Field(default="")
    openai_base_url: str = Field(default="https://openrouter.ai/api/v1")
    openai_model: str = Field(default="openai/gpt-4o")
    openai_timeout_seconds: float = Field(default=120.0)
    openai_fallback_models: str = Field(default="")

    max_input_chars: int = Field(default=40000)
    max_sections: int = Field(default=20)
    max_section_chars: int = Field(default=2000)
    max_output_tokens: int = Field(default=2000)

    jwt_secret_key: str = Field(default="change_me_super_secret_key")
    jwt_algorithm: str = Field(default="HS256")
    access_token_expire_minutes: int = Field(default=60 * 24)
    refresh_token_expire_minutes: int = Field(default=43200)

    cors_origins: str = Field(default="*")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @field_validator("jwt_secret_key")
    @classmethod
    def validate_jwt_secret(cls, v: str, info: object) -> str:
        weak_keys = {"", "change_me_super_secret_key"}
        debug = getattr(info, "data", {}).get("debug", True)
        if v in weak_keys and not debug:
            raise ValueError(
                "JWT_SECRET_KEY is not set or uses the default insecure value. "
                "Generate a secure key with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        return v

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:"
            f"{self.postgres_password}@{self.postgres_host}:"
            f"{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def celery_broker_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/0"

    @property
    def celery_result_backend(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/1"

    @property
    def cors_origins_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def fallback_models_list(self) -> list[str]:
        return [m.strip() for m in self.openai_fallback_models.split(",") if m.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
