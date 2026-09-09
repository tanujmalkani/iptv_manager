from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "IPTV Manager"
    environment: str = "development"
    database_url: str = "sqlite:///./data/iptv_manager.db"
    log_level: str = "INFO"
    discovery_timeout_seconds: float = 10.0
    discovery_max_response_bytes: int = 10 * 1024 * 1024
    discovery_max_depth: int = 5
    quick_test_timeout_seconds: float = 10.0
    ffmpeg_binary: str = "ffmpeg"

    model_config = SettingsConfigDict(env_file=".env", env_prefix="IPTV_", extra="ignore")

    @property
    def database_path(self) -> Path | None:
        if not self.database_url.startswith("sqlite:///"):
            return None
        return Path(self.database_url.removeprefix("sqlite:///" )).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
