"""
Referral system handler.

Features:
  - Generate unique referral link per user
  - Track referrals via /start deep links (ref_USERID)
  - Bonus: +10 extra images for both referrer and referred
  - View referral stats
"""

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from .. import database as db
from ..keyboards import main_menu_keyboard
from ..ui import safe_edit_text

logger = logging.getLogger(__name__)

router = Router()

REFERRAL_BONUS_IMAGES = 10  # bonus images for each side


# ---------------------------------------------------------------------------
# Show referral menu
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "menu:referral")
async def show_referral_menu(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id if callback.from_user else 0
    user = await db.get_user(user_id)
    ref_code = user.get("referral_code", f"ref_{user_id}") if user else f"ref_{user_id}"

    # Get bot username from callback
    bot_info = await callback.bot.get_me()
    bot_username = bot_info.username or "bot"

    ref_link = f"https://t.me/{bot_username}?start={ref_code}"
    ref_count = await db.count_referrals(user_id)
    extra = await db.get_extra_quota(user_id)

    text = (
        "<b>🔗 Referral</b>\n"
        "─────────────────\n\n"
        f"Link:\n<code>{ref_link}</code>\n\n"
        f"Teman bergabung: <b>{ref_count}</b>\n"
        f"Bonus diterima: <b>+{ref_count * REFERRAL_BONUS_IMAGES}</b> img\n\n"
        f"Extra: <b>{extra['images']}</b> img · <b>{extra['videos']}</b> vid\n\n"
        f"<i>Tiap teman yang join, kalian berdua dapat +{REFERRAL_BONUS_IMAGES} image.</i>"
    )

    from ..keyboards import referral_keyboard
    await safe_edit_text(callback.message, text, reply_markup=referral_keyboard())
    await callback.answer()


# ---------------------------------------------------------------------------
# Process referral on /start (called from common.py)
# ---------------------------------------------------------------------------

async def process_referral(referred_id: int, referrer_id: int) -> str | None:
    """Process a referral when a new user joins via deep link.

    Returns a message string if referral was successful, None otherwise.
    """
    if referred_id == referrer_id:
        return None

    # Check if referrer exists
    referrer = await db.get_user(referrer_id)
    if referrer is None:
        return None

    # Check if already referred
    existing = await db.get_referral_by_referred(referred_id)
    if existing is not None:
        return None

    # Create referral
    ok = await db.create_referral(referrer_id, referred_id)
    if not ok:
        return None

    # Set referred_by on user
    await db.set_referred_by(referred_id, referrer_id)

    # Give bonus to both
    await db.add_extra_quota(referrer_id, images=REFERRAL_BONUS_IMAGES)
    await db.add_extra_quota(referred_id, images=REFERRAL_BONUS_IMAGES)
    await db.mark_referral_bonus(referred_id)

    referrer_name = referrer.get("first_name", str(referrer_id))
    logger.info(
        "[Referral] %s referred %s — bonus +%d images each",
        referrer_id, referred_id, REFERRAL_BONUS_IMAGES,
    )

    return (
        f"<b>Referral Bonus!</b>\n"
        f"Diundang oleh <b>{referrer_name}</b>.\n"
        f"Kalian berdua dapat <b>+{REFERRAL_BONUS_IMAGES} extra image</b>."
    )
