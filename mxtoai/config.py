import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    DB_USER: str
    DB_PASSWORD: str
    DB_HOST: str
    DB_PORT: str
    DB_NAME: str

    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


# List of email addresses for which we skip sending email replies
# Useful for testing and development environments
SKIP_EMAIL_DELIVERY = [
    "test@example.com",
]
# Ensure attachments directory exists with absolute path
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ATTACHMENTS_DIR = os.path.abspath(os.path.join(parent_dir, "attachments"))
os.makedirs(ATTACHMENTS_DIR, exist_ok=True)

# Attachment limits (in megabytes)
MAX_ATTACHMENT_SIZE_MB = 15
MAX_TOTAL_ATTACHMENTS_SIZE_MB = 50
MAX_ATTACHMENTS_COUNT = 5
