"""Gemini Account management handler for the Telegram bot."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ..client import gateway_client
from ..gemini_manager import LocalGeminiManager
from ..keyboards import admin_menu_keyboard, gemini_input_keyboard, gemini_menu_keyboard, gemini_skip_keyboard
from ..security import is_admin
from ..states import GeminiFlow
from ..ui import clear_state, safe_edit_text

from pathlib import Path
import os

router = Router()

# Store Gemini accounts in persistent volume (same as DB)
_gemini_file = Path(os.environ.get("SSO_FILE", "key.txt")).parent / "gemini_accounts.json"
gemini_mgr = LocalGeminiManager(_gemini_file)


@router.callback_query(F.data == "menu:gemini")
async def open_gemini_menu(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id if callback.from_user else 0
    if not is_admin(user_id):
        await callback.answer("Akses ditolak", show_alert=True)
        return

    await safe_edit_text(
        callback.message,
        "💎 <b>Gemini Account Manager</b>\n"
        "Kelola akun Gemini Business untuk image generation.",
        reply_markup=gemini_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "gem:list")
async def list_gemini_accounts(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id if callback.from_user else 0
    if not is_admin(user_id):
        await callback.answer("Akses ditolak", show_alert=True)
        return

    summary = gemini_mgr.get_masked_summary()
    if not summary:
        text = "Belum ada akun Gemini."
    else:
        text = "📋 <b>Gemini Accounts</b>\n" + "\n".join(summary)

    await safe_edit_text(callback.message, text, reply_markup=gemini_menu_keyboard())
    await callback.answer()


# ---- Add Account Flow (3 steps: secure_c_ses -> host_c_oses -> csesidx) ----

@router.callback_query(F.data == "gem:add")
async def add_gemini_start(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id if callback.from_user else 0
    if not is_admin(user_id):
        await callback.answer("Akses ditolak", show_alert=True)
        return

    await state.set_state(GeminiFlow.waiting_secure_c_ses)
    await safe_edit_text(
        callback.message,
        "🔑 <b>Step 1/3</b>\n"
        "Kirim value <b>__Secure-C_SES</b>:",
        reply_markup=gemini_input_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "gem:add:cancel")
async def add_gemini_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await clear_state(state)
    await safe_edit_text(
        callback.message,
        "💎 <b>Gemini Account Manager</b>\n"
        "Kelola akun Gemini Business untuk image generation.",
        reply_markup=gemini_menu_keyboard(),
    )
    await callback.answer("Dibatalkan")


@router.message(GeminiFlow.waiting_secure_c_ses)
async def add_gemini_step1(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id if message.from_user else 0
    if not is_admin(user_id):
        await clear_state(state)
        return

    value = (message.text or "").strip()
    if not value:
        await message.answer("❌ secure_c_ses tidak boleh kosong. Kirim ulang atau cancel.")
        return

    await state.update_data(secure_c_ses=value)
    await state.set_state(GeminiFlow.waiting_host_c_oses)
    await message.answer(
        "🔑 <b>Step 2/3</b>\n"
        "Kirim value <b>__Host-C_OSES</b>:\n\n"
        "Tekan Skip jika tidak ada.",
        reply_markup=gemini_skip_keyboard(),
    )


@router.callback_query(F.data == "gem:skip", GeminiFlow.waiting_host_c_oses)
async def skip_host_c_oses(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(host_c_oses="")
    await state.set_state(GeminiFlow.waiting_csesidx)
    await safe_edit_text(
        callback.message,
        "🔑 <b>Step 3/3</b>\n"
        "Kirim value <b>csesidx</b> (angka):",
        reply_markup=gemini_input_keyboard(),
    )
    await callback.answer()


@router.message(GeminiFlow.waiting_host_c_oses)
async def add_gemini_step2(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id if message.from_user else 0
    if not is_admin(user_id):
        await clear_state(state)
        return

    value = (message.text or "").strip()
    await state.update_data(host_c_oses=value)
    await state.set_state(GeminiFlow.waiting_csesidx)
    await message.answer(
        "🔑 <b>Step 3/3</b>\n"
        "Kirim value <b>csesidx</b> (angka):",
        reply_markup=gemini_input_keyboard(),
    )


@router.message(GeminiFlow.waiting_csesidx)
async def add_gemini_step3(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id if message.from_user else 0
    if not is_admin(user_id):
        await clear_state(state)
        return

    csesidx = (message.text or "").strip()
    data = await state.get_data()
    await clear_state(state)

    result = gemini_mgr.add_account(
        secure_c_ses=data.get("secure_c_ses", ""),
        host_c_oses=data.get("host_c_oses", ""),
        csesidx=csesidx,
    )

    if result["status"] == "error":
        await message.answer(f"❌ {result['message']}")
        await message.answer(
            "💎 <b>Gemini Account Manager</b>",
            reply_markup=gemini_menu_keyboard(),
        )
        return

    if result["status"] == "exists":
        await message.answer(f"⚠️ {result['message']}")
        await message.answer(
            "💎 <b>Gemini Account Manager</b>",
            reply_markup=gemini_menu_keyboard(),
        )
        return

    # Auto-reload gateway
    try:
        accounts_json = gemini_mgr.get_config_json()
        reload_result = await gateway_client.reload_gemini(accounts_json)
        before = result.get("before_count", 0)
        after = result.get("after_count", 0)
        await message.answer(
            f"✅ {result['message']}\n"
            f"Total: {before} → {after}\n"
            f"🔄 Gateway reload: {reload_result}"
        )
    except Exception as exc:
        before = result.get("before_count", 0)
        after = result.get("after_count", 0)
        await message.answer(
            f"✅ {result['message']}\n"
            f"Total: {before} → {after}\n"
            f"⚠️ Gateway reload gagal: {exc}"
        )

    await message.answer(
        "💎 <b>Gemini Account Manager</b>",
        reply_markup=gemini_menu_keyboard(),
    )


# ---- Reload & Remove ----

@router.callback_query(F.data == "gem:reload")
async def gemini_reload(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id if callback.from_user else 0
    if not is_admin(user_id):
        await callback.answer("Akses ditolak", show_alert=True)
        return

    try:
        accounts_json = gemini_mgr.get_config_json()
        payload = await gateway_client.reload_gemini(accounts_json)
        await safe_edit_text(
            callback.message,
            f"✅ Reload Gemini selesai: {payload}",
            reply_markup=gemini_menu_keyboard(),
        )
    except Exception as exc:
        await safe_edit_text(
            callback.message,
            f"❌ Reload Gemini gagal: {exc}",
            reply_markup=gemini_menu_keyboard(),
        )
    await callback.answer()


@router.callback_query(F.data == "gem:remove_last")
async def gemini_remove_last(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id if callback.from_user else 0
    if not is_admin(user_id):
        await callback.answer("Akses ditolak", show_alert=True)
        return

    result = gemini_mgr.remove_last_account()
    if result["status"] != "ok":
        await safe_edit_text(
            callback.message,
            f"❌ {result['message']}",
            reply_markup=gemini_menu_keyboard(),
        )
        await callback.answer()
        return

    try:
        accounts_json = gemini_mgr.get_config_json()
        payload = await gateway_client.reload_gemini(accounts_json)
        await safe_edit_text(
            callback.message,
            f"✅ {result['message']}\n🔄 Reload: {payload}",
            reply_markup=gemini_menu_keyboard(),
        )
    except Exception as exc:
        await safe_edit_text(
            callback.message,
            f"✅ {result['message']}\n⚠️ Reload gagal: {exc}",
            reply_markup=gemini_menu_keyboard(),
        )
    await callback.answer()
