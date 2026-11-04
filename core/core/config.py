from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    APP_NAME: str = "Intraq API"
    APP_ENV: str = "development"
    DEBUG: bool = False
    SECRET_KEY: str = Field(min_length=32)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    ALGORITHM: str = "HS256"
    DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6379/0"
    R2_ACCOUNT_ID: str
    R2_ACCESS_KEY_ID: str
    R2_SECRET_ACCESS_KEY: str
    R2_BUCKET_NAME: str
    EXTERNAL_AUTOMATION_URL: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=True, extra="ignore")

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
