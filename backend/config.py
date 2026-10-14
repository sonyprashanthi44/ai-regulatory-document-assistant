from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    secret_key: str = "dev-secret-change-in-production"
    gemini_api_key: str = ""
    access_token_expire_minutes: int = 60
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    algorithm: str = "HS256"

    class Config:
        env_file = ".env"
        extra = "ignore"

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
