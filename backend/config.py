from pydantic_settings import BaseSettings
import os

class Settings(BaseSettings):
    SECRET_KEY: str = "your-secret-key-change-in-production-abc123def456"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours
    DATA_FILE: str = os.path.join(os.path.dirname(__file__), "..", "data", "data.json")
    
    class Config:
        env_file = ".env"

settings = Settings()
