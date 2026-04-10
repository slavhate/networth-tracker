from pydantic_settings import BaseSettings
import os
import secrets
import logging

logger = logging.getLogger(__name__)

def _default_secret_key() -> str:
    key = secrets.token_hex(32)
    logger.warning(
        "SECRET_KEY not set — using auto-generated key. "
        "Tokens will not survive restarts. "
        "Set SECRET_KEY env var for persistent sessions."
    )
    return key

class Settings(BaseSettings):
    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours
    DATA_FILE: str = os.path.join(os.path.dirname(__file__), "..", "data", "data.json")
    CREATE_DEMO_DATA: bool = False

    class Config:
        env_file = ".env"

settings = Settings()

if not settings.SECRET_KEY:
    settings.SECRET_KEY = _default_secret_key()
