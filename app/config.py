"""Vantage Risk — Application configuration via pydantic-settings."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite+aiosqlite:///./vantage_risk.db"
    SECRET_KEY: str = "change-this-to-a-secure-random-string-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    RISK_FREE_RATE: float = 0.03

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
