"""
Subscription tier management for the Telegram bot.

Tiers:
  free    – default, limited daily usage
  basic   – higher limits, batch prompt up to 3
  premium – unlimited, batch prompt up to 10

Duration: daily / weekly / monthly (stored as expiry timestamp).
Admin can grant/revoke subscriptions.

Storage: SQLite via bot.database
"""

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List

from . import database as db


# ---------------------------------------------------------------------------
# Tier definitions
# ---------------------------------------------------------------------------

class Tier(str, Enum):
    FREE = "free"
    BASIC = "basic"
    PREMIUM = "premium"


class Duration(str, Enum):
    DAILY = "daily"      # 1 day
    WEEKLY = "weekly"    # 7 days
    MONTHLY = "monthly"  # 30 days


DURATION_SECONDS = {
    Duration.DAILY: 86_400,
    Duration.WEEKLY: 86_400 * 7,
    Duration.MONTHLY: 86_400 * 30,
}

TIER_LABELS = {
    Tier.FREE: "🆓 Free",
    Tier.BASIC: "⭐ Basic",
    Tier.PREMIUM: "💎 Premium",
}

DURATION_LABELS = {
    Duration.DAILY: "Harian (1 hari)",
    Duration.WEEKLY: "Mingguan (7 hari)",
    Duration.MONTHLY: "Bulanan (30 hari)",
}


# ---------------------------------------------------------------------------
# Tier limits
# ---------------------------------------------------------------------------

UNLIMITED = 999_999_999  # sentinel for "unlimited"


@dataclass
class TierLimits:
    images_per_day: int
    videos_per_day: int
    max_images_per_request: int   # max n value allowed
    max_batch_prompts: int        # how many prompts in one batch

    @property
    def is_unlimited_images(self) -> bool:
        return self.images_per_day >= UNLIMITED

    @property
    def is_unlimited_videos(self) -> bool:
        return self.videos_per_day >= UNLIMITED


TIER_LIMITS: Dict[Tier, TierLimits] = {
    Tier.FREE: TierLimits(
        images_per_day=20,
        videos_per_day=10,
        max_images_per_request=2,
        max_batch_prompts=1,
    ),
    Tier.BASIC: TierLimits(
        images_per_day=500,
        videos_per_day=200,
        max_images_per_request=4,
        max_batch_prompts=3,
    ),
    Tier.PREMIUM: TierLimits(
        images_per_day=UNLIMITED,
        videos_per_day=UNLIMITED,
        max_images_per_request=4,
        max_batch_prompts=10,
    ),
}


# ---------------------------------------------------------------------------
# Subscription dataclass (for return values)
# ---------------------------------------------------------------------------

@dataclass
class Subscription:
    tier: str
    expires: float
    granted_by: int
    granted_at: float


# ---------------------------------------------------------------------------
# Subscription Manager (SQLite-backed)
# ---------------------------------------------------------------------------

class SubscriptionManager:

    async def get_subscription(self, user_id: int) -> Subscription:
        row = await db.get_subscription(user_id)
        if row is None:
            return Subscription(tier=Tier.FREE.value, expires=0, granted_by=0, granted_at=0)
        # check expiry
        if row["expires"] > 0 and time.time() > row["expires"]:
            await db.delete_subscription(user_id)
            return Subscription(tier=Tier.FREE.value, expires=0, granted_by=0, granted_at=0)
        return Subscription(**row)

    async def get_tier(self, user_id: int) -> Tier:
        sub = await self.get_subscription(user_id)
        try:
            return Tier(sub.tier)
        except ValueError:
            return Tier.FREE

    async def get_limits(self, user_id: int) -> TierLimits:
        tier = await self.get_tier(user_id)
        return TIER_LIMITS[tier]

    async def grant(
        self,
        user_id: int,
        tier: Tier,
        duration: Duration,
        granted_by: int = 0,
    ) -> Subscription:
        now = time.time()

        # extend if same tier and still active
        existing = await db.get_subscription(user_id)
        base_time = now
        if existing and existing["expires"] > now and existing["tier"] == tier.value:
            base_time = existing["expires"]

        expires = base_time + DURATION_SECONDS[duration]
        await db.upsert_subscription(
            user_id=user_id,
            tier=tier.value,
            expires=expires,
            granted_by=granted_by,
            granted_at=now,
        )
        return Subscription(tier=tier.value, expires=expires, granted_by=granted_by, granted_at=now)

    async def revoke(self, user_id: int) -> bool:
        return await db.delete_subscription(user_id)

    async def list_active(self) -> List[Dict[str, Any]]:
        return await db.list_active_subscriptions()

    async def get_info_text(self, user_id: int) -> str:
        sub = await self.get_subscription(user_id)
        tier = Tier(sub.tier) if sub.tier in [t.value for t in Tier] else Tier.FREE
        limits = TIER_LIMITS[tier]

        lines = [
            "💎 <b>Subscription Info</b>",
            f"• Tier: <b>{TIER_LABELS[tier]}</b>",
        ]

        if sub.expires > 0:
            import datetime
            exp_dt = datetime.datetime.fromtimestamp(sub.expires)
            remaining = sub.expires - time.time()
            if remaining > 0:
                days = int(remaining // 86400)
                hours = int((remaining % 86400) // 3600)
                lines.append(f"• Expires: <b>{exp_dt:%Y-%m-%d %H:%M}</b>")
                lines.append(f"• Sisa: <b>{days}d {hours}h</b>")
            else:
                lines.append("• Status: <b>Expired</b>")
        else:
            if tier == Tier.FREE:
                lines.append("• Status: <b>Aktif (default)</b>")

        lines.append("")
        lines.append("<b>📊 Limit Harian:</b>")
        img_txt = "Unlimited ♾️" if limits.is_unlimited_images else f"{limits.images_per_day}/hari"
        vid_txt = "Unlimited ♾️" if limits.is_unlimited_videos else f"{limits.videos_per_day}/hari"
        lines.append(f"• Image: <b>{img_txt}</b>")
        lines.append(f"• Video: <b>{vid_txt}</b>")
        lines.append(f"• Max gambar/request: <b>{limits.max_images_per_request}</b>")
        lines.append(f"• Max batch prompt: <b>{limits.max_batch_prompts}</b>")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

subscription_manager = SubscriptionManager()
