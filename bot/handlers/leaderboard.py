"""
Leaderboard handler — show top users this month.
"""

import datetime

from aiogram import F, Router
from aiogram.types import CallbackQuery

from .. import database as db
from ..keyboards import main_menu_keyboard
from ..ui import safe_edit_text

router = Router()

WIB = datetime.timezone(datetime.timedelta(hours=7))

MEDALS = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


@router.callback_query(F.data == "menu:leaderboard")
async def show_leaderboard(callback: CallbackQuery) -> None:
    now = datetime.datetime.now(WIB)
    month_label = now.strftime("%B %Y")

    top = await db.get_leaderboard(limit=10)
    user_id = callback.from_user.id

    if not top:
        await safe_edit_text(
            callback.message,
            f"🏆 <b>Leaderboard — {month_label}</b>\n\nBelum ada data bulan ini.",
            reply_markup=_lb_keyboard(),
        )
        await callback.answer()
        return

    lines = [f"🏆 <b>Leaderboard — {month_label}</b>\n"]
    lines.append("Top generator bulan ini:\n")

    for i, entry in enumerate(top):
        medal = MEDALS[i] if i < len(MEDALS) else f"{i+1}."
        name = entry.get("first_name") or entry.get("username") or str(entry["user_id"])
        total_img = entry.get("total_images", 0)
        total_vid = entry.get("total_videos", 0)
        total = entry.get("total", 0)
        is_me = " ← kamu" if entry["user_id"] == user_id else ""
        lines.append(
            f"{medal} <b>{name}</b>{is_me}\n"
            f"     🖼 {total_img} img • 🎬 {total_vid} vid • Total: {total}"
        )

    # Find user's own rank
    user_rank = None
    for i, entry in enumerate(top):
        if entry["user_id"] == user_id:
            user_rank = i + 1
            break

    if user_rank:
        lines.append(f"\n📊 Kamu di peringkat <b>#{user_rank}</b>!")
    else:
        # Get user's own usage
        usage = await db.get_usage(user_id)
        total_own = usage["images"] + usage["videos"]
        if total_own > 0:
            lines.append(f"\n📊 Kamu belum masuk top 10. (Total hari ini: {total_own})")
        else:
            lines.append("\n📊 Mulai generate untuk masuk leaderboard!")

    await safe_edit_text(
        callback.message,
        "\n".join(lines),
        reply_markup=_lb_keyboard(),
    )
    await callback.answer()


def _lb_keyboard():
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Refresh", callback_data="menu:leaderboard")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="menu:home")],
    ])
