"""
In-memory rate limiter with tier-based cooldowns.

Cooldowns (seconds between generation requests):
  Free    = 30s
  Basic   = 15s
  Premium = 5s
  Admin   = 0s (no cooldown)
"""

import time
from typing import Dict, Optional, Tuple

from .subscription_manager import Tier


# Cooldown in seconds per tier
COOLDOWNS: Dict[Tier, int] = {
    Tier.FREE: 30,
    Tier.BASIC: 15,
    Tier.PREMIUM: 5,
}

# {user_id: last_generation_timestamp}
_last_request: Dict[int, float] = {}


def check_cooldown(user_id: int, tier: Tier, is_admin: bool = False) -> Tuple[bool, int]:
    """Check if user can make a request.

    Returns:
        (allowed, remaining_seconds)
        If allowed=True, remaining_seconds=0.
        If allowed=False, remaining_seconds = seconds until cooldown expires.
    """
    if is_admin:
        return True, 0

    cooldown = COOLDOWNS.get(tier, 30)
    if cooldown <= 0:
        return True, 0

    now = time.time()
    last = _last_request.get(user_id, 0)
    elapsed = now - last

    if elapsed >= cooldown:
        return True, 0

    remaining = int(cooldown - elapsed) + 1
    return False, remaining


def record_request(user_id: int) -> None:
    """Record that the user just made a generation request."""
    _last_request[user_id] = time.time()


def get_cooldown_text(tier: Tier) -> str:
    """Return human-readable cooldown info for the tier."""
    cd = COOLDOWNS.get(tier, 30)
    return f"{cd} detik"
