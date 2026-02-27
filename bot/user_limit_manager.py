"""
Daily usage limit manager backed by SQLite.

Uses date-keyed rows (WIB timezone) so limits auto-reset at midnight WIB.
Supports extra quota (topup) — when daily limit is exhausted, extra quota is used.
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
        extra = await db.get_extra_quota(user_id)

        return {
            "is_admin": is_admin_user,
            "images_used": usage["images"],
            "images_limit": image_limit,
            "images_remaining": max(0, image_limit - usage["images"]),
            "videos_used": usage["videos"],
            "videos_limit": video_limit,
            "videos_remaining": max(0, video_limit - usage["videos"]),
            "extra_images": extra["images"],
            "extra_videos": extra["videos"],
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

        # Check daily limit first, then extra quota as fallback
        img_ok = (status["images_used"] + image_units <= status["images_limit"]) or \
                 (status["extra_images"] >= image_units)
        vid_ok = (status["videos_used"] + video_units <= status["videos_limit"]) or \
                 (status["extra_videos"] >= video_units)

        return (img_ok and vid_ok), status

    async def consume(
        self,
        user_id: int,
        image_units: int = 0,
        video_units: int = 0,
        is_admin_user: bool = False,
    ) -> Dict[str, int | bool]:
        if not is_admin_user:
            usage = await db.get_usage(user_id)
            image_limit, video_limit = await self._get_limits(user_id)

            # For images: use daily limit first, overflow to extra quota
            img_daily_remaining = max(0, image_limit - usage["images"])
            if image_units <= img_daily_remaining:
                await db.add_usage(user_id, images=image_units, videos=0)
            else:
                # Use all daily remaining + deduct rest from extra
                daily_use = min(image_units, img_daily_remaining)
                extra_use = image_units - daily_use
                if daily_use > 0:
                    await db.add_usage(user_id, images=daily_use, videos=0)
                if extra_use > 0:
                    await db.deduct_extra_quota(user_id, images=extra_use)

            # For videos: same logic
            vid_daily_remaining = max(0, video_limit - usage["videos"])
            if video_units <= vid_daily_remaining:
                await db.add_usage(user_id, images=0, videos=video_units)
            else:
                daily_use = min(video_units, vid_daily_remaining)
                extra_use = video_units - daily_use
                if daily_use > 0:
                    await db.add_usage(user_id, images=0, videos=daily_use)
                if extra_use > 0:
                    await db.deduct_extra_quota(user_id, videos=extra_use)

        return await self.get_status(user_id, is_admin_user=is_admin_user)


user_limit_manager = UserLimitManager()
