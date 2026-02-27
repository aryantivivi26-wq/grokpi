"""Subscription management handlers for the Telegram bot."""

import html
from datetime import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ..keyboards import (
    grant_duration_keyboard,
    grant_tier_keyboard,
    main_menu_keyboard,
    subscription_admin_keyboard,
    subscription_menu_keyboard,
)
from ..security import is_admin
from ..states import SubsAdminFlow
from ..subscription_manager import (
    Duration,
    Tier,
    TIER_LABELS,
    TIER_LIMITS,
    UNLIMITED,
    DURATION_LABELS,
    subscription_manager,
)
from ..ui import clear_state, get_backend, safe_edit_text

router = Router()


# ---------------------------------------------------------------------------
# User-facing: subscription info
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "menu:subs")
async def open_subs_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await clear_state(state)
    user_id = callback.from_user.id if callback.from_user else 0
    kb = subscription_admin_keyboard() if is_admin(user_id) else subscription_menu_keyboard()
    info = await subscription_manager.get_info_text(user_id)
    await safe_edit_text(callback.message, info, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "subs:info")
async def show_sub_info(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id if callback.from_user else 0
    kb = subscription_admin_keyboard() if is_admin(user_id) else subscription_menu_keyboard()
    info = await subscription_manager.get_info_text(user_id)
    await safe_edit_text(callback.message, info, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "subs:tiers")
async def show_tier_comparison(callback: CallbackQuery) -> None:
    lines = ["📊 <b>Perbandingan Tier</b>\n"]
    for tier in Tier:
        lim = TIER_LIMITS[tier]
        img_txt = "Unlimited ♾️" if lim.is_unlimited_images else f"{lim.images_per_day}/hari"
        vid_txt = "Unlimited ♾️" if lim.is_unlimited_videos else f"{lim.videos_per_day}/hari"
        lines.append(f"<b>{TIER_LABELS[tier]}</b>")
        lines.append(f"  • Image: {img_txt}")
        lines.append(f"  • Video: {vid_txt}")
        lines.append(f"  • Max gambar/request: {lim.max_images_per_request}")
        lines.append(f"  • Batch prompt: {lim.max_batch_prompts}")
        lines.append("")

    user_id = callback.from_user.id if callback.from_user else 0
    kb = subscription_admin_keyboard() if is_admin(user_id) else subscription_menu_keyboard()
    await safe_edit_text(callback.message, "\n".join(lines), reply_markup=kb)
    await callback.answer()


# ---------------------------------------------------------------------------
# Admin: grant subscription
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "subs:grant")
async def grant_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id if callback.from_user else 0):
        await callback.answer("Admin only", show_alert=True)
        return
    await state.set_state(SubsAdminFlow.waiting_user_id)
    await state.update_data(subs_action="grant")
    await safe_edit_text(
        callback.message,
        "🆔 Kirim <b>User ID</b> (angka) yang ingin diberi subscription:",
    )
    await callback.answer()


@router.callback_query(F.data == "subs:revoke")
async def revoke_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id if callback.from_user else 0):
        await callback.answer("Admin only", show_alert=True)
        return
    await state.set_state(SubsAdminFlow.waiting_user_id)
    await state.update_data(subs_action="revoke")
    await safe_edit_text(
        callback.message,
        "🆔 Kirim <b>User ID</b> (angka) yang ingin di-revoke subscription-nya:",
    )
    await callback.answer()


@router.message(SubsAdminFlow.waiting_user_id)
async def handle_user_id(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    try:
        target_uid = int(text)
    except ValueError:
        await message.answer("❌ User ID harus angka. Coba lagi:")
        return

    data = await state.get_data()
    action = data.get("subs_action", "grant")

    if action == "revoke":
        revoked = await subscription_manager.revoke(target_uid)
        await clear_state(state)
        if revoked:
            await message.answer(f"✅ Subscription user <b>{target_uid}</b> di-revoke (kembali Free).")
        else:
            await message.answer(f"ℹ️ User <b>{target_uid}</b> tidak punya subscription aktif.")
        await message.answer("🏠 <b>Main Menu</b>", reply_markup=main_menu_keyboard(await get_backend(state)))
        return

    # grant flow: choose tier
    await state.update_data(subs_target_uid=target_uid)
    await clear_state(state)
    await state.update_data(subs_target_uid=target_uid)
    await message.answer(
        f"Pilih tier untuk user <b>{target_uid}</b>:",
        reply_markup=grant_tier_keyboard(),
    )


@router.callback_query(F.data.startswith("subs:grant:"))
async def grant_choose_tier(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id if callback.from_user else 0):
        await callback.answer("Admin only", show_alert=True)
        return
    tier_str = callback.data.replace("subs:grant:", "", 1)
    data = await state.get_data()
    target_uid = data.get("subs_target_uid")
    if not target_uid:
        await callback.answer("Session expired, ulangi", show_alert=True)
        return
    await state.update_data(subs_tier=tier_str)
    await safe_edit_text(
        callback.message,
        f"Pilih durasi <b>{tier_str.upper()}</b> untuk user <b>{target_uid}</b>:",
        reply_markup=grant_duration_keyboard(tier_str),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("subs:dur:"))
async def grant_choose_duration(callback: CallbackQuery, state: FSMContext) -> None:
    admin_id = callback.from_user.id if callback.from_user else 0
    if not is_admin(admin_id):
        await callback.answer("Admin only", show_alert=True)
        return

    parts = callback.data.replace("subs:dur:", "", 1).split(":")
    if len(parts) != 2:
        await callback.answer("Invalid data", show_alert=True)
        return
    tier_str, dur_str = parts

    data = await state.get_data()
    target_uid = data.get("subs_target_uid")
    if not target_uid:
        await callback.answer("Session expired, ulangi", show_alert=True)
        return

    try:
        tier = Tier(tier_str)
        duration = Duration(dur_str)
    except ValueError:
        await callback.answer("Invalid tier/duration", show_alert=True)
        return

    sub = await subscription_manager.grant(
        user_id=target_uid,
        tier=tier,
        duration=duration,
        granted_by=admin_id,
    )

    exp_text = datetime.fromtimestamp(sub.expires).strftime("%Y-%m-%d %H:%M")
    text = (
        f"✅ <b>Subscription Granted!</b>\n"
        f"• User: <b>{target_uid}</b>\n"
        f"• Tier: <b>{TIER_LABELS[tier]}</b>\n"
        f"• Duration: <b>{DURATION_LABELS[duration]}</b>\n"
        f"• Expires: <b>{exp_text}</b>"
    )
    await clear_state(state)
    await safe_edit_text(callback.message, text, reply_markup=subscription_admin_keyboard())
    await callback.answer()


# ---------------------------------------------------------------------------
# Admin: list active subscriptions
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "subs:list")
async def list_active_subs(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id if callback.from_user else 0):
        await callback.answer("Admin only", show_alert=True)
        return

    subs = await subscription_manager.list_active()
    if not subs:
        await safe_edit_text(
            callback.message,
            "📃 <b>Active Subscriptions</b>\n\nTidak ada subscription aktif.",
            reply_markup=subscription_admin_keyboard(),
        )
        await callback.answer()
        return

    lines = ["📃 <b>Active Subscriptions</b>\n"]
    for s in subs:
        tier_label = TIER_LABELS.get(Tier(s["tier"]), s["tier"])
        exp = datetime.fromtimestamp(s["expires"]).strftime("%Y-%m-%d %H:%M") if s["expires"] else "∞"
        lines.append(f"• <b>{s['user_id']}</b> — {tier_label} (exp: {exp})")

    await safe_edit_text(
        callback.message,
        "\n".join(lines),
        reply_markup=subscription_admin_keyboard(),
    )
    await callback.answer()
