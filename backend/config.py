from functools import lru_cache
import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
    )

    secret_key: str = "dev-secret-change-in-production"
    gemini_api_key: str = ""
    access_token_expire_minutes: int = 120
    cors_origins: str = "*"
    algorithm: str = "HS256"
    allow_local_fallback: bool = True
    force_local_rag: bool = False

    def resolved_gemini_key(self) -> str:
        return (
            self.gemini_api_key
            or os.getenv("GEMINI_API_KEY", "")
            or os.getenv("GOOGLE_API_KEY", "")
            or os.getenv("GOOGLE_GENERATIVE_AI_API_KEY", "")
        ).strip()

    @property
    def origins(self) -> list[str]:
        raw = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        return raw or ["*"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
