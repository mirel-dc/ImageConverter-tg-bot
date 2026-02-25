from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Bot settings
    bot_token: str = Field(..., alias="BOT_TOKEN")
    allowed_users: str | list[int] = Field(default_factory=list, alias="ALLOWED_USERS")

    # Limits
    max_download_mb: int = 20
    max_upload_mb: int = 50
    convert_timeout_seconds: int = 240

    # UX / Progress
    progress_update_seconds: int = 5

    # Converter defaults
    default_quality: int = 100
    default_dpi: int = 150
    default_pdf_mode: str = "combine"
    default_ico_sizes: list[int] = [16, 32, 48, 64, 128, 256]

    @property
    def max_download_bytes(self) -> int:
        return self.max_download_mb * 1024 * 1024

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @field_validator("allowed_users", mode="before")
    @classmethod
    def parse_allowed_users(cls, v: str | list[int]) -> list[int]:
        if isinstance(v, str):
            if not v.strip():
                return []
            return [int(x.strip()) for x in v.split(",") if x.strip().isdigit()]
        return v


settings = Settings()
