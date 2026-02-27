"""
Daily usage limit manager backed by SQLite.

Uses date-keyed rows (WIB timezone) so limits auto-reset at midnight WIB.
"""

from typing import Dict

from . import database as db
from .config import settings


def _get_subscription_manager():
    """Lazy import to avoid circular dependency."""
    from .subscription_manager import subscription_manager
    return subscription_manager


class UserLimitManager:

    async def _get_limits(self, user_id: int) -> tuple[int, int]:
        """Return (image_limit, video_limit) based on subscription tier."""
        try:
            sm = _get_subscription_manager()
            tier_limits = await sm.get_limits(user_id)
            return tier_limits.images_per_day, tier_limits.videos_per_day
        except Exception:
            return settings.USER_DAILY_IMAGE_LIMIT, settings.USER_DAILY_VIDEO_LIMIT

    async def get_status(self, user_id: int, is_admin_user: bool = False) -> Dict[str, int | bool]:
        usage = await db.get_usage(user_id)
        image_limit, video_limit = await self._get_limits(user_id)

        return {
            "is_admin": is_admin_user,
            "images_used": usage["images"],
            "images_limit": image_limit,
            "images_remaining": max(0, image_limit - usage["images"]),
            "videos_used": usage["videos"],
            "videos_limit": video_limit,
            "videos_remaining": max(0, video_limit - usage["videos"]),
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
        if not is_admin_user:
            await db.add_usage(user_id, images=max(0, image_units), videos=max(0, video_units))

        return await self.get_status(user_id, is_admin_user=is_admin_user)


user_limit_manager = UserLimitManager()
