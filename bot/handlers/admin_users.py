"""
Admin mini-app: user management, subscription assignment, broadcast.

Callbacks:
  adm:users        — paginated user list
  adm:subs         — active subscribers
  adm:stats        — bot statistics
  adm:user:view:ID — user detail
  adm:usub:*       — assign/revoke sub for user
  adm:user:del:*   — delete user
  adm:broadcast    — broadcast message to all users
  adm:bc:send      — confirm & send broadcast
"""

import asyncio
import html
import logging
import math
import time
from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import database as db
from ..keyboards import (
    admin_assign_dur_keyboard,
    admin_assign_tier_keyboard,
    admin_menu_keyboard,
    admin_user_del_confirm_keyboard,
    admin_user_detail_keyboard,
    admin_users_keyboard,
    broadcast_confirm_keyboard,
)
from ..security import is_admin
from ..states import AdminUserFlow, BroadcastFlow
from ..subscription_manager import (
    Duration,
    Tier,
    TIER_LABELS,
    DURATION_LABELS,
    subscription_manager,
)
from ..ui import clear_state, safe_edit_text

logger = logging.getLogger(__name__)

router = Router()
PAGE_SIZE = 10


def _ensure_admin(callback: CallbackQuery) -> bool:
    uid = callback.from_user.id if callback.from_user else 0
    return is_admin(uid)


# ---------------------------------------------------------------------------
# Bot stats
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "adm:stats")
async def adm_stats(callback: CallbackQuery) -> None:
    if not _ensure_admin(callback):
        await callback.answer("Admin only", show_alert=True)
        return

    stats = await db.get_bot_stats()
    text = (
        "<b>Bot Statistics</b>\n\n"
        f"User: <b>{stats['total_users']}</b>\n"
        f"Subscriber: <b>{stats['active_subs']}</b>\n"
        f"Transaksi paid: <b>{stats['total_paid']}</b>\n"
        f"Aktif hari ini: <b>{stats['active_today']}</b>"
    )
    await safe_edit_text(callback.message, text, reply_markup=admin_menu_keyboard())
    await callback.answer()


# ---------------------------------------------------------------------------
# User list (paginated)
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "adm:users")
async def adm_users(callback: CallbackQuery) -> None:
    if not _ensure_admin(callback):
        await callback.answer("Admin only", show_alert=True)
        return
    await _show_user_page(callback, 0)


@router.callback_query(F.data.startswith("adm:users:p:"))
async def adm_users_page(callback: CallbackQuery) -> None:
    if not _ensure_admin(callback):
        await callback.answer("Admin only", show_alert=True)
        return
    try:
        page = int(callback.data.rsplit(":", 1)[1])
    except (ValueError, IndexError):
        page = 0
    await _show_user_page(callback, page)


async def _show_user_page(callback: CallbackQuery, page: int) -> None:
    total = await db.count_users()
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = max(0, min(page, total_pages - 1))

    users = await db.list_users(limit=PAGE_SIZE, offset=page * PAGE_SIZE)
    now = time.time()

    lines = [f"<b>Semua User</b> · {total}\n"]
    for u in users:
        uname = f"@{u['username']}" if u["username"] else "-"
        tier_row = await db.get_subscription(u["user_id"])
        tier_str = "free"
        if tier_row and tier_row["tier"] != "free":
            if tier_row["expires"] > now or tier_row["expires"] == 0:
                tier_str = tier_row["tier"]
        tier_icon = {"basic": "⭐", "premium": "💎"}.get(tier_str, "🆓")
        lines.append(
            f"{tier_icon} <code>{u['user_id']}</code> — {html.escape(u['first_name'] or '-')} ({uname})"
        )

    lines.append(f"\nKlik ID untuk detail.")
    await safe_edit_text(
        callback.message,
        "\n".join(lines),
        reply_markup=admin_users_keyboard(page, total_pages),
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Search user by ID
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "adm:user:search")
async def adm_user_search(callback: CallbackQuery, state: FSMContext) -> None:
    if not _ensure_admin(callback):
        await callback.answer("Admin only", show_alert=True)
        return
    await state.set_state(AdminUserFlow.waiting_user_id)
    await safe_edit_text(
        callback.message,
        "Kirim <b>User ID</b> yang ingin dilihat:",
    )
    await callback.answer()


@router.message(AdminUserFlow.waiting_user_id)
async def adm_user_search_input(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    try:
        target_uid = int(text)
    except ValueError:
        await message.answer("User ID harus angka. Coba lagi:")
        return

    await clear_state(state)
    user = await db.get_user(target_uid)
    if not user:
        await message.answer(
            f"User <code>{target_uid}</code> tidak ditemukan.",
            reply_markup=admin_menu_keyboard(),
        )
        return

    text = await _build_user_detail(user)
    await message.answer(text, reply_markup=admin_user_detail_keyboard(target_uid))


# ---------------------------------------------------------------------------
# User detail view
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("adm:user:view:"))
async def adm_user_view(callback: CallbackQuery) -> None:
    if not _ensure_admin(callback):
        await callback.answer("Admin only", show_alert=True)
        return

    try:
        uid = int(callback.data.rsplit(":", 1)[1])
    except (ValueError, IndexError):
        await callback.answer("Invalid ID", show_alert=True)
        return

    user = await db.get_user(uid)
    if not user:
        await callback.answer("User tidak ditemukan", show_alert=True)
        return

    text = await _build_user_detail(user)
    await safe_edit_text(callback.message, text, reply_markup=admin_user_detail_keyboard(uid))
    await callback.answer()


async def _build_user_detail(user: dict) -> str:
    uid = user["user_id"]
    uname = f"@{user['username']}" if user["username"] else "-"
    first_seen = datetime.fromtimestamp(user["first_seen"]).strftime("%d/%m/%Y %H:%M") if user["first_seen"] else "-"
    last_seen = datetime.fromtimestamp(user["last_seen"]).strftime("%d/%m/%Y %H:%M") if user["last_seen"] else "-"

    sub = await subscription_manager.get_subscription(uid)
    tier = Tier(sub.tier) if sub.tier in [t.value for t in Tier] else Tier.FREE
    tier_label = TIER_LABELS[tier]

    lines = [
        f"<b>User Detail</b>\n",
        f"ID: <code>{uid}</code>",
        f"Nama: <b>{html.escape(user['first_name'] or '-')}</b>",
        f"Username: {uname}",
        f"First seen: {first_seen}",
        f"Last seen: {last_seen}\n",
        f"<b>Subscription</b>",
        f"Tier: {tier_label}",
    ]

    if tier != Tier.FREE and sub.expires > 0:
        remaining = sub.expires - time.time()
        if remaining > 0:
            days = int(remaining // 86400)
            hours = int((remaining % 86400) // 3600)
            exp_dt = datetime.fromtimestamp(sub.expires)
            lines.append(f"Exp: {exp_dt:%d/%m/%Y %H:%M}")
            lines.append(f"Sisa: {days}h {hours}j")
        else:
            lines.append("Status: <b>Expired</b>")
    else:
        lines.append("Status: Free")

    # Usage today
    usage = await db.get_usage(uid)
    lines.append(f"\n<b>Usage Hari Ini</b>")
    lines.append(f"Image: {usage['images']} · Video: {usage['videos']}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Active subscribers list
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "adm:subs")
async def adm_subscribers(callback: CallbackQuery) -> None:
    if not _ensure_admin(callback):
        await callback.answer("Admin only", show_alert=True)
        return

    subs = await subscription_manager.list_active()
    if not subs:
        await safe_edit_text(
            callback.message,
            "<b>Subscriber Aktif</b>\n\nTidak ada.",
            reply_markup=admin_menu_keyboard(),
        )
        await callback.answer()
        return

    lines = [f"<b>Subscriber Aktif</b> · {len(subs)}\n"]
    for s in subs:
        tier_label = TIER_LABELS.get(Tier(s["tier"]), s["tier"])
        exp = datetime.fromtimestamp(s["expires"]).strftime("%d/%m %H:%M") if s["expires"] else "∞"
        user = await db.get_user(s["user_id"])
        name = html.escape(user["first_name"]) if user and user["first_name"] else str(s["user_id"])
        lines.append(f"• <code>{s['user_id']}</code> {name} — {tier_label} (exp: {exp})")

    await safe_edit_text(callback.message, "\n".join(lines), reply_markup=admin_menu_keyboard())
    await callback.answer()


# ---------------------------------------------------------------------------
# Assign subscription to user (from detail view)
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("adm:usub:grant:"))
async def adm_assign_start(callback: CallbackQuery) -> None:
    if not _ensure_admin(callback):
        await callback.answer("Admin only", show_alert=True)
        return
    try:
        uid = int(callback.data.rsplit(":", 1)[1])
    except (ValueError, IndexError):
        await callback.answer("Invalid", show_alert=True)
        return

    await safe_edit_text(
        callback.message,
        f"Pilih tier untuk user <code>{uid}</code>:",
        reply_markup=admin_assign_tier_keyboard(uid),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:usub:t:"))
async def adm_assign_tier(callback: CallbackQuery) -> None:
    if not _ensure_admin(callback):
        await callback.answer("Admin only", show_alert=True)
        return
    # adm:usub:t:UID:TIER
    parts = callback.data.split(":")
    if len(parts) != 5:
        await callback.answer("Invalid", show_alert=True)
        return
    uid, tier_str = int(parts[3]), parts[4]

    await safe_edit_text(
        callback.message,
        f"Pilih durasi <b>{tier_str.upper()}</b> untuk user <code>{uid}</code>:",
        reply_markup=admin_assign_dur_keyboard(uid, tier_str),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:usub:d:"))
async def adm_assign_duration(callback: CallbackQuery) -> None:
    if not _ensure_admin(callback):
        await callback.answer("Admin only", show_alert=True)
        return
    # adm:usub:d:UID:TIER:DURATION
    parts = callback.data.split(":")
    if len(parts) != 6:
        await callback.answer("Invalid", show_alert=True)
        return
    uid, tier_str, dur_str = int(parts[3]), parts[4], parts[5]
    admin_id = callback.from_user.id if callback.from_user else 0

    try:
        tier = Tier(tier_str)
        duration = Duration(dur_str)
    except ValueError:
        await callback.answer("Invalid tier/duration", show_alert=True)
        return

    sub = await subscription_manager.grant(
        user_id=uid,
        tier=tier,
        duration=duration,
        granted_by=admin_id,
    )

    exp_text = datetime.fromtimestamp(sub.expires).strftime("%d/%m/%Y %H:%M")
    text = (
        f"<b>Subscription Granted</b>\n\n"
        f"User: <code>{uid}</code>\n"
        f"Tier: <b>{TIER_LABELS[tier]}</b>\n"
        f"Durasi: <b>{DURATION_LABELS[duration]}</b>\n"
        f"Exp: <b>{exp_text}</b>"
    )
    await safe_edit_text(callback.message, text, reply_markup=admin_user_detail_keyboard(uid))
    await callback.answer()


# ---------------------------------------------------------------------------
# Revoke subscription from detail view
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("adm:usub:revoke:"))
async def adm_revoke_sub(callback: CallbackQuery) -> None:
    if not _ensure_admin(callback):
        await callback.answer("Admin only", show_alert=True)
        return
    try:
        uid = int(callback.data.rsplit(":", 1)[1])
    except (ValueError, IndexError):
        await callback.answer("Invalid", show_alert=True)
        return

    revoked = await subscription_manager.revoke(uid)
    if revoked:
        await callback.answer("Subscription di-revoke", show_alert=True)
    else:
        await callback.answer("Tidak ada subscription aktif", show_alert=True)

    # Refresh detail
    user = await db.get_user(uid)
    if user:
        text = await _build_user_detail(user)
        await safe_edit_text(callback.message, text, reply_markup=admin_user_detail_keyboard(uid))


# ---------------------------------------------------------------------------
# Delete user
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("adm:user:del:"))
async def adm_user_del_confirm(callback: CallbackQuery) -> None:
    if not _ensure_admin(callback):
        await callback.answer("Admin only", show_alert=True)
        return
    # Filter out "delok" callbacks
    if "delok" in callback.data:
        return
    try:
        uid = int(callback.data.rsplit(":", 1)[1])
    except (ValueError, IndexError):
        await callback.answer("Invalid", show_alert=True)
        return

    await safe_edit_text(
        callback.message,
        f"Yakin hapus user <code>{uid}</code>?\n\nSemua data akan dihapus permanen.",
        reply_markup=admin_user_del_confirm_keyboard(uid),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:user:delok:"))
async def adm_user_del_ok(callback: CallbackQuery) -> None:
    if not _ensure_admin(callback):
        await callback.answer("Admin only", show_alert=True)
        return
    try:
        uid = int(callback.data.rsplit(":", 1)[1])
    except (ValueError, IndexError):
        await callback.answer("Invalid", show_alert=True)
        return

    await db.delete_user(uid)
    await safe_edit_text(
        callback.message,
        f"User <code>{uid}</code> dihapus.",
        reply_markup=admin_menu_keyboard(),
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Broadcast
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "adm:broadcast")
async def adm_broadcast_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _ensure_admin(callback):
        await callback.answer("Admin only", show_alert=True)
        return

    total = await db.count_users()
    await state.set_state(BroadcastFlow.waiting_message)
    await safe_edit_text(
        callback.message,
        f"<b>Broadcast</b>\n\n"
        f"Target: <b>{total}</b> user.\n"
        f"Tulis pesan (HTML supported):\n\n"
        f"/cancel untuk batal.",
    )
    await callback.answer()


@router.message(BroadcastFlow.waiting_message)
async def adm_broadcast_preview(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("Pesan tidak boleh kosong. Coba lagi:")
        return

    await state.update_data(bc_text=text)
    total = await db.count_users()
    await message.answer(
        f"<b>Preview</b>\n\n"
        f"─────────────────\n"
        f"{text}\n"
        f"─────────────────\n\n"
        f"Kirim ke <b>{total}</b> user?",
        reply_markup=broadcast_confirm_keyboard(),
    )


@router.callback_query(F.data == "adm:bc:send")
async def adm_broadcast_send(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not _ensure_admin(callback):
        await callback.answer("Admin only", show_alert=True)
        return

    data = await state.get_data()
    bc_text = data.get("bc_text", "")
    await clear_state(state)

    if not bc_text:
        await callback.answer("Pesan kosong, batalkan", show_alert=True)
        return

    await safe_edit_text(callback.message, "Mengirim broadcast…")
    await callback.answer()

    user_ids = await db.get_all_user_ids()
    success = 0
    failed = 0

    for uid in user_ids:
        try:
            await bot.send_message(
                chat_id=uid,
                text=f"📢 <b>Broadcast</b>\n\n{bc_text}",
            )
            success += 1
        except Exception:
            failed += 1

        # Rate limiting: Telegram allows ~30 msg/sec
        if (success + failed) % 25 == 0:
            await asyncio.sleep(1)

    await safe_edit_text(
        callback.message,
        f"<b>Broadcast Selesai</b>\n\n"
        f"Terkirim: <b>{success}</b>\n"
        f"Gagal: <b>{failed}</b>\n"
        f"Total: <b>{len(user_ids)}</b>",
        reply_markup=admin_menu_keyboard(),
    )
