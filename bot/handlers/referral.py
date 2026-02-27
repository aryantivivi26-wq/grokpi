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
        "🔗 <b>Referral Program</b>\n\n"
        "Ajak teman pakai bot ini dan dapatkan <b>bonus kuota</b>!\n\n"
        f"📎 <b>Link Referral Kamu:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        f"👥 <b>Teman yang bergabung:</b> {ref_count}\n"
        f"🎁 <b>Bonus diterima:</b> +{ref_count * REFERRAL_BONUS_IMAGES} images\n\n"
        f"📦 <b>Extra Kuota Kamu:</b>\n"
        f"├ Image: <b>{extra['images']}</b>\n"
        f"└ Video: <b>{extra['videos']}</b>\n\n"
        "💡 Setiap teman yang join lewat link kamu, "
        f"kalian berdua dapat <b>+{REFERRAL_BONUS_IMAGES} image</b> gratis!"
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
        f"🎉 <b>Referral Bonus!</b>\n"
        f"Kamu diundang oleh <b>{referrer_name}</b>.\n"
        f"Kalian berdua mendapat <b>+{REFERRAL_BONUS_IMAGES} extra image</b>!"
    )
