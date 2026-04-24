from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://visites_user:password@localhost/visites_db"
    ENCRYPTION_KEY: str = ""
    SECRET_KEY: str = "canvia-aquesta-clau-secreta"

    SESSION_HOURS: int = 8
    EXIT_TOKEN_HOURS: int = 8
    KIOSK_RESET_SECONDS: int = 60
    KIOSK_CONFIRM_SECONDS: int = 15
    MAX_VISIT_HOURS_WARN: int = 4
    MAX_VISIT_HOURS_ALERT: int = 8

    COMPANY_NAME: str = "La Meva Empresa"
    COMPANY_ADDRESS: str = ""
    COMPANY_EMAIL: str = "dpo@empresa.com"
    BASE_URL: str = "http://localhost:8001"

    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "visites@empresa.com"

    ENV: str = "development"
    DEBUG: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
