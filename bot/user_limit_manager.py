import asyncio
import json
import time
from pathlib import Path
from typing import Dict

from .config import settings


class UserLimitManager:
    RESET_INTERVAL = 86400

    def __init__(self, state_file: Path):
        self._state_file = state_file
        self._lock = asyncio.Lock()
        self._usage: Dict[str, Dict[str, int]] = {}
        self._last_reset: float = 0
        self._loaded = False

    def _load_state(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self._state_file.exists():
            return
        try:
            data = json.loads(self._state_file.read_text(encoding="utf-8"))
            self._last_reset = float(data.get("last_reset", 0) or 0)
            users = data.get("users", {})
            if isinstance(users, dict):
                for user_id, usage in users.items():
                    self._usage[str(user_id)] = {
                        "images": int((usage or {}).get("images", 0) or 0),
                        "videos": int((usage or {}).get("videos", 0) or 0),
                    }
        except Exception:
            self._usage = {}
            self._last_reset = 0

    def _save_state(self) -> None:
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "last_reset": self._last_reset,
            "users": self._usage,
        }
        self._state_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _reset_if_needed(self) -> None:
        now = time.time()
        if self._last_reset == 0:
            self._last_reset = now
            return
        if now - self._last_reset >= self.RESET_INTERVAL:
            self._usage = {}
            self._last_reset = now
            self._save_state()

    def _get_usage(self, user_id: int) -> Dict[str, int]:
        key = str(user_id)
        if key not in self._usage:
            self._usage[key] = {"images": 0, "videos": 0}
        return self._usage[key]

    async def get_status(self, user_id: int, is_admin_user: bool = False) -> Dict[str, int | bool]:
        async with self._lock:
            self._load_state()
            self._reset_if_needed()
            usage = self._get_usage(user_id)
            image_limit = settings.USER_DAILY_IMAGE_LIMIT
            video_limit = settings.USER_DAILY_VIDEO_LIMIT

            return {
                "is_admin": is_admin_user,
                "images_used": usage["images"],
                "images_limit": image_limit,
                "images_remaining": max(0, image_limit - usage["images"]),
                "videos_used": usage["videos"],
                "videos_limit": video_limit,
                "videos_remaining": max(0, video_limit - usage["videos"]),
                "next_reset_timestamp": int(self._last_reset + self.RESET_INTERVAL) if self._last_reset else 0,
            }

    async def can_consume(
        self,
        user_id: int,
        image_units: int = 0,
        video_units: int = 0,
        is_admin_user: bool = False,
    ) -> tuple[bool, Dict[str, int | bool]]:
        status = await self.get_status(user_id, is_admin_user=is_admin_user)
        if is_admin_user:
            return True, status

        allowed = (
            status["images_used"] + image_units <= status["images_limit"]
            and status["videos_used"] + video_units <= status["videos_limit"]
        )
        return bool(allowed), status

    async def consume(
        self,
        user_id: int,
        image_units: int = 0,
        video_units: int = 0,
        is_admin_user: bool = False,
    ) -> Dict[str, int | bool]:
        async with self._lock:
            self._load_state()
            self._reset_if_needed()
            usage = self._get_usage(user_id)
            if not is_admin_user:
                usage["images"] = max(0, usage["images"] + max(0, image_units))
                usage["videos"] = max(0, usage["videos"] + max(0, video_units))
                self._save_state()

            image_limit = settings.USER_DAILY_IMAGE_LIMIT
            video_limit = settings.USER_DAILY_VIDEO_LIMIT
            return {
                "is_admin": is_admin_user,
                "images_used": usage["images"],
                "images_limit": image_limit,
                "images_remaining": max(0, image_limit - usage["images"]),
                "videos_used": usage["videos"],
                "videos_limit": video_limit,
                "videos_remaining": max(0, video_limit - usage["videos"]),
                "next_reset_timestamp": int(self._last_reset + self.RESET_INTERVAL) if self._last_reset else 0,
            }


user_limit_manager = UserLimitManager(settings.LIMITS_STATE_FILE)
