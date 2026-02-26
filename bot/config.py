from pathlib import Path
from typing import List

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


ROOT_DIR = Path(__file__).resolve().parents[1]


class BotSettings(BaseSettings):
    TELEGRAM_BOT_TOKEN: str = Field(
        default="",
        validation_alias=AliasChoices("TELEGRAM_BOT_TOKEN", "BOT_TOKEN", "TG_BOT_TOKEN"),
    )
    BOT_ADMIN_IDS: str = Field(
        default="",
        validation_alias=AliasChoices("BOT_ADMIN_IDS", "ADMIN_ID", "ADMIN_IDS", "TELEGRAM_ADMIN_IDS"),
    )

    GATEWAY_BASE_URL: str = "http://127.0.0.1:9563"
    GATEWAY_API_KEY: str = Field(default="")
    API_KEY: str = Field(default="")
    REQUEST_TIMEOUT_SECONDS: int = 240
    USER_DAILY_IMAGE_LIMIT: int = 5
    USER_DAILY_VIDEO_LIMIT: int = 1

    SSO_FILE: Path = ROOT_DIR / "key.txt"
    LIMITS_STATE_FILE: Path = ROOT_DIR / "user_limits_state.json"

    class Config:
        env_file = str(ROOT_DIR / ".env")
        env_file_encoding = "utf-8"
        extra = "ignore"

    @property
    def admin_ids(self) -> List[int]:
        normalized = self.BOT_ADMIN_IDS.replace(";", ",").replace(" ", ",")
        values = []
        for chunk in normalized.split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            try:
                values.append(int(chunk))
            except ValueError:
                continue
        return values

    @property
    def gateway_api_key(self) -> str:
        return (self.GATEWAY_API_KEY or self.API_KEY).strip()


settings = BotSettings()
