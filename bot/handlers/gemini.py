"""Gemini Account management handler for the Telegram bot."""

import logging

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

logger = logging.getLogger(__name__)

router = Router()

# Store Gemini accounts in persistent volume (same as DB)
_gemini_file = Path(os.environ.get("SSO_FILE", "key.txt")).parent / "gemini_accounts.json"
gemini_mgr = LocalGeminiManager(_gemini_file)


async def _build_menu_keyboard():
    """Build the gemini menu keyboard with server status data."""
    data = gemini_mgr.get_server_keyboard_data()
    return gemini_menu_keyboard(server_data=data if data else None)


async def _refresh_health_and_build_menu():
    """Fetch health from gateway, update manager status, build keyboard."""
    try:
        health = await gateway_client.gemini_health()
        accounts = health.get("accounts", [])
        gemini_mgr.update_status(accounts)
    except Exception as exc:
        logger.warning("Health check failed: %s", exc)
    return await _build_menu_keyboard()


@router.callback_query(F.data == "menu:gemini")
async def open_gemini_menu(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id if callback.from_user else 0
    if not is_admin(user_id):
        await callback.answer("Akses ditolak", show_alert=True)
        return

    kb = await _build_menu_keyboard()
    await safe_edit_text(
        callback.message,
        "💎 <b>Gemini Server Manager</b>\n"
        "Kelola server Gemini Business untuk image generation.\n"
        "Tekan 🩺 Health Check untuk cek status server.",
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(F.data == "gem:list")
async def list_gemini_accounts(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id if callback.from_user else 0
    if not is_admin(user_id):
        await callback.answer("Akses ditolak", show_alert=True)
        return

    # Fetch health to show status
    kb = await _refresh_health_and_build_menu()
    summary = gemini_mgr.get_masked_summary()
    if not summary:
        text = "💎 <b>Gemini Servers</b>\nBelum ada server."
    else:
        text = "💎 <b>Gemini Servers</b>\n\n" + "\n".join(summary)

    await safe_edit_text(callback.message, text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "gem:health")
async def gemini_health_check(callback: CallbackQuery) -> None:
    """Run health check against all servers."""
    user_id = callback.from_user.id if callback.from_user else 0
    if not is_admin(user_id):
        await callback.answer("Akses ditolak", show_alert=True)
        return

    await callback.answer("🩺 Checking health...", show_alert=False)

    try:
        health = await gateway_client.gemini_health()
        accounts = health.get("accounts", [])
        gemini_mgr.update_status(accounts)

        lines = ["🩺 <b>Server Health Check</b>\n"]
        from ..gemini_manager import STATUS_ICONS
        for i, acc in enumerate(accounts):
            status = acc.get("status", "unknown")
            icon = STATUS_ICONS.get(status, "❓")
            error = acc.get("error", "")
            line = f"{icon} <b>Server {i + 1}</b>: {status}"
            if error:
                line += f" — <i>{error[:60]}</i>"
            lines.append(line)

        if not accounts:
            lines.append("Tidak ada server terdaftar di gateway.")

        kb = await _build_menu_keyboard()
        await safe_edit_text(callback.message, "\n".join(lines), reply_markup=kb)
    except Exception as exc:
        kb = await _build_menu_keyboard()
        await safe_edit_text(
            callback.message,
            f"❌ Health check gagal: {exc}",
            reply_markup=kb,
        )


@router.callback_query(F.data.startswith("gem:info:"))
async def gemini_server_info(callback: CallbackQuery) -> None:
    """Show detailed info for a single server."""
    user_id = callback.from_user.id if callback.from_user else 0
    if not is_admin(user_id):
        await callback.answer("Akses ditolak", show_alert=True)
        return

    try:
        idx = int(callback.data.split(":")[-1])
    except (ValueError, IndexError):
        await callback.answer("Invalid index", show_alert=True)
        return

    accounts = gemini_mgr.list_accounts()
    if idx < 0 or idx >= len(accounts):
        await callback.answer("Server tidak ditemukan", show_alert=True)
        return

    acc = accounts[idx]
    from ..gemini_manager import STATUS_ICONS
    status = gemini_mgr.get_status(idx)
    icon = STATUS_ICONS.get(status, "❓")

    ses = acc.get("secure_c_ses", "")
    if len(ses) > 20:
        masked_ses = ses[:10] + "..." + ses[-6:]
    else:
        masked_ses = ses[:3] + "***"

    oses = acc.get("host_c_oses", "")
    if len(oses) > 20:
        masked_oses = oses[:10] + "..." + oses[-6:]
    else:
        masked_oses = oses[:3] + "***" if oses else "(kosong)"

    email = acc.get("email", "")
    email_line = f"📧 email: <code>{email}</code>" if email else "📧 email: <i>belum diset (auto-login disabled)</i>"
    expires = acc.get("expires_at", "")
    expires_line = f"⏰ expires: <code>{expires}</code>" if expires else ""

    text = (
        f"{icon} <b>Server {idx + 1}</b> — {status}\n\n"
        f"🔑 secure_c_ses: <code>{masked_ses}</code>\n"
        f"🔑 host_c_oses: <code>{masked_oses}</code>\n"
        f"📝 csesidx: <code>{acc.get('csesidx', '?')}</code>\n"
        f"⚙️ config_id: <code>{acc.get('config_id', '?')}</code>\n"
        f"{email_line}"
    )
    if expires_line:
        text += f"\n{expires_line}"

    # Build per-server action keyboard
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    rows = []
    if email:
        rows.append([InlineKeyboardButton(text="🔄 Auto-Login Refresh", callback_data=f"gem:autologin:{idx}")])
    else:
        rows.append([InlineKeyboardButton(text="📧 Set Email (enable auto-login)", callback_data=f"gem:setemail:{idx}")])
    rows.append([InlineKeyboardButton(text="🗑 Remove", callback_data=f"gem:rm:{idx}")])
    rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data="gem:list")])
    info_kb = InlineKeyboardMarkup(inline_keyboard=rows)

    await safe_edit_text(callback.message, text, reply_markup=info_kb)
    await callback.answer()


@router.callback_query(F.data.startswith("gem:rm:"))
async def gemini_remove_server(callback: CallbackQuery) -> None:
    """Remove a specific server by index."""
    user_id = callback.from_user.id if callback.from_user else 0
    if not is_admin(user_id):
        await callback.answer("Akses ditolak", show_alert=True)
        return

    try:
        idx = int(callback.data.split(":")[-1])
    except (ValueError, IndexError):
        await callback.answer("Invalid index", show_alert=True)
        return

    result = gemini_mgr.remove_account(idx)
    if result["status"] != "ok":
        kb = await _build_menu_keyboard()
        await safe_edit_text(
            callback.message,
            f"❌ {result['message']}",
            reply_markup=kb,
        )
        await callback.answer()
        return

    # Auto-reload gateway
    try:
        accounts_json = gemini_mgr.get_config_json()
        payload = await gateway_client.reload_gemini(accounts_json)
        kb = await _build_menu_keyboard()
        await safe_edit_text(
            callback.message,
            f"✅ {result['message']}\n🔄 Reload: {payload}",
            reply_markup=kb,
        )
    except Exception as exc:
        kb = await _build_menu_keyboard()
        await safe_edit_text(
            callback.message,
            f"✅ {result['message']}\n⚠️ Reload gagal: {exc}",
            reply_markup=kb,
        )
    await callback.answer()


# ---- Add Account Flow (4 steps: secure_c_ses -> host_c_oses -> csesidx -> config_id) ----

@router.callback_query(F.data == "gem:add")
async def add_gemini_start(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id if callback.from_user else 0
    if not is_admin(user_id):
        await callback.answer("Akses ditolak", show_alert=True)
        return

    await state.set_state(GeminiFlow.waiting_secure_c_ses)
    await safe_edit_text(
        callback.message,
        "🔑 <b>Step 1/4</b>\n"
        "Kirim value <b>__Secure-C_SES</b>:",
        reply_markup=gemini_input_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "gem:add:cancel")
async def add_gemini_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await clear_state(state)
    kb = await _build_menu_keyboard()
    await safe_edit_text(
        callback.message,
        "💎 <b>Gemini Server Manager</b>\n"
        "Kelola server Gemini Business untuk image generation.",
        reply_markup=kb,
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
        "🔑 <b>Step 2/4</b>\n"
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
        "🔑 <b>Step 3/4</b>\n"
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
        "🔑 <b>Step 3/4</b>\n"
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
    await state.update_data(csesidx=csesidx)
    await state.set_state(GeminiFlow.waiting_config_id)
    await message.answer(
        "🔑 <b>Step 4/4</b>\n"
        "Kirim <b>config_id</b> (UUID dari Gemini Business workspace):\n\n"
        "Tekan Skip untuk auto-generate.",
        reply_markup=gemini_skip_keyboard(),
    )


@router.callback_query(F.data == "gem:skip", GeminiFlow.waiting_config_id)
async def skip_config_id(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()

    # Move to email step
    await state.update_data(config_id="")
    await state.set_state(GeminiFlow.waiting_email)
    await safe_edit_text(
        callback.message,
        "📧 <b>Step 5/5 — Auto-Login Email</b>\n"
        "Kirim <b>email</b> Google account ini untuk auto-refresh cookies.\n\n"
        "⚠️ Email harus terdaftar di generator.email domain.\n"
        "Tekan Skip jika tidak mau auto-refresh.",
        reply_markup=gemini_skip_keyboard(),
    )
    await callback.answer()


@router.message(GeminiFlow.waiting_config_id)
async def add_gemini_step4(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id if message.from_user else 0
    if not is_admin(user_id):
        await clear_state(state)
        return

    config_id = (message.text or "").strip()
    await state.update_data(config_id=config_id)
    await state.set_state(GeminiFlow.waiting_email)
    await message.answer(
        "📧 <b>Step 5/5 — Auto-Login Email</b>\n"
        "Kirim <b>email</b> Google account ini untuk auto-refresh cookies.\n\n"
        "⚠️ Email harus terdaftar di generator.email domain.\n"
        "Tekan Skip jika tidak mau auto-refresh.",
        reply_markup=gemini_skip_keyboard(),
    )


@router.callback_query(F.data == "gem:skip", GeminiFlow.waiting_email)
async def skip_email(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()

    # If this is from set-email flow, just cancel back
    if data.get("set_email_index") is not None:
        await clear_state(state)
        kb = await _build_menu_keyboard()
        await safe_edit_text(
            callback.message,
            "💎 <b>Gemini Server Manager</b>",
            reply_markup=kb,
        )
        await callback.answer("Dibatalkan")
        return

    # From add-account flow — save without email
    await clear_state(state)
    result = gemini_mgr.add_account(
        secure_c_ses=data.get("secure_c_ses", ""),
        host_c_oses=data.get("host_c_oses", ""),
        csesidx=data.get("csesidx", ""),
        config_id=data.get("config_id", ""),
        email="",
    )
    await _finish_add(callback.message, result)
    await callback.answer()


@router.message(GeminiFlow.waiting_email)
async def handle_email_input(message: Message, state: FSMContext) -> None:
    """Unified email input handler — works for both add-flow and set-email flow."""
    user_id = message.from_user.id if message.from_user else 0
    if not is_admin(user_id):
        await clear_state(state)
        return

    email = (message.text or "").strip()
    data = await state.get_data()

    # Check if this is a "set email on existing server" flow
    set_email_index = data.get("set_email_index")
    if set_email_index is not None:
        await clear_state(state)
        result = gemini_mgr.update_account_email(set_email_index, email)
        kb = await _build_menu_keyboard()
        if result["status"] == "ok":
            await message.answer(f"✅ {result['message']}")
        else:
            await message.answer(f"❌ {result['message']}")
        await message.answer(
            "💎 <b>Gemini Server Manager</b>",
            reply_markup=kb,
        )
        return

    # Otherwise from add-account flow (step 5)
    await clear_state(state)
    result = gemini_mgr.add_account(
        secure_c_ses=data.get("secure_c_ses", ""),
        host_c_oses=data.get("host_c_oses", ""),
        csesidx=data.get("csesidx", ""),
        config_id=data.get("config_id", ""),
        email=email,
    )
    await _finish_add(message, result)


async def _finish_add(target: Message, result: dict) -> None:
    """Common finalizer for add-account flow."""
    kb = await _build_menu_keyboard()

    if result["status"] == "error":
        await target.answer(f"❌ {result['message']}")
        await target.answer(
            "💎 <b>Gemini Server Manager</b>",
            reply_markup=kb,
        )
        return

    if result["status"] == "exists":
        await target.answer(f"⚠️ {result['message']}")
        await target.answer(
            "💎 <b>Gemini Server Manager</b>",
            reply_markup=kb,
        )
        return

    # Auto-reload gateway
    try:
        accounts_json = gemini_mgr.get_config_json()
        reload_result = await gateway_client.reload_gemini(accounts_json)
        before = result.get("before_count", 0)
        after = result.get("after_count", 0)
        await target.answer(
            f"✅ {result['message']}\n"
            f"Total: {before} → {after}\n"
            f"🔄 Gateway reload: {reload_result}"
        )
    except Exception as exc:
        before = result.get("before_count", 0)
        after = result.get("after_count", 0)
        await target.answer(
            f"✅ {result['message']}\n"
            f"Total: {before} → {after}\n"
            f"⚠️ Gateway reload gagal: {exc}"
        )

    kb = await _build_menu_keyboard()
    await target.answer(
        "💎 <b>Gemini Server Manager</b>",
        reply_markup=kb,
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
        kb = await _build_menu_keyboard()
        await safe_edit_text(
            callback.message,
            f"✅ Reload Gemini selesai: {payload}",
            reply_markup=kb,
        )
    except Exception as exc:
        kb = await _build_menu_keyboard()
        await safe_edit_text(
            callback.message,
            f"❌ Reload Gemini gagal: {exc}",
            reply_markup=kb,
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
        kb = await _build_menu_keyboard()
        await safe_edit_text(
            callback.message,
            f"❌ {result['message']}",
            reply_markup=kb,
        )
        await callback.answer()
        return

    try:
        accounts_json = gemini_mgr.get_config_json()
        payload = await gateway_client.reload_gemini(accounts_json)
        kb = await _build_menu_keyboard()
        await safe_edit_text(
            callback.message,
            f"✅ {result['message']}\n🔄 Reload: {payload}",
            reply_markup=kb,
        )
    except Exception as exc:
        kb = await _build_menu_keyboard()
        await safe_edit_text(
            callback.message,
            f"✅ {result['message']}\n⚠️ Reload gagal: {exc}",
            reply_markup=kb,
        )
    await callback.answer()


# ---- Auto-Login & Email Config ----

@router.callback_query(F.data.startswith("gem:autologin:"))
async def gemini_autologin_trigger(callback: CallbackQuery) -> None:
    """Trigger auto-login for a specific server."""
    user_id = callback.from_user.id if callback.from_user else 0
    if not is_admin(user_id):
        await callback.answer("Akses ditolak", show_alert=True)
        return

    try:
        idx = int(callback.data.split(":")[-1])
    except (ValueError, IndexError):
        await callback.answer("Invalid index", show_alert=True)
        return

    acc = gemini_mgr.get_account(idx)
    if not acc:
        await callback.answer("Server tidak ditemukan", show_alert=True)
        return

    email = acc.get("email", "")
    if not email:
        await callback.answer("Email belum diset! Set email dulu.", show_alert=True)
        return

    await callback.answer("🔄 Starting auto-login... (bisa 1-3 menit)", show_alert=True)

    kb = await _build_menu_keyboard()
    await safe_edit_text(
        callback.message,
        f"🔄 <b>Auto-Login Server {idx + 1}</b>\n\n"
        f"📧 Email: {email}\n"
        f"⏳ Sedang login via headless Chrome...\n"
        f"Proses ini bisa memakan waktu 1-3 menit.",
        reply_markup=kb,
    )

    try:
        result = await gateway_client.gemini_autologin(
            account_index=idx,
            email=email,
            mail_provider=acc.get("mail_provider", "generatoremail"),
        )

        if result.get("success"):
            # Update local cookies file too
            config = result.get("config", {})
            gemini_mgr.update_account_cookies(idx, config)

            # Reload gateway with updated config
            accounts_json = gemini_mgr.get_config_json()
            await gateway_client.reload_gemini(accounts_json)

            kb = await _refresh_health_and_build_menu()
            await safe_edit_text(
                callback.message,
                f"✅ <b>Auto-Login Server {idx + 1} Berhasil!</b>\n\n"
                f"📧 Email: {email}\n"
                f"🔑 Cookies baru sudah di-update.\n"
                f"⏰ Expires: {config.get('expires_at', '?')}\n"
                f"🔄 Gateway reloaded.",
                reply_markup=kb,
            )
        else:
            error = result.get("error", "Unknown error")
            kb = await _build_menu_keyboard()
            await safe_edit_text(
                callback.message,
                f"❌ <b>Auto-Login Server {idx + 1} Gagal</b>\n\n"
                f"📧 Email: {email}\n"
                f"Error: {error[:200]}",
                reply_markup=kb,
            )
    except Exception as exc:
        kb = await _build_menu_keyboard()
        await safe_edit_text(
            callback.message,
            f"❌ Auto-Login error: {exc}",
            reply_markup=kb,
        )


@router.callback_query(F.data.startswith("gem:setemail:"))
async def gemini_set_email_start(callback: CallbackQuery, state: FSMContext) -> None:
    """Start email config for a specific server."""
    user_id = callback.from_user.id if callback.from_user else 0
    if not is_admin(user_id):
        await callback.answer("Akses ditolak", show_alert=True)
        return

    try:
        idx = int(callback.data.split(":")[-1])
    except (ValueError, IndexError):
        await callback.answer("Invalid index", show_alert=True)
        return

    await state.set_state(GeminiFlow.waiting_email)
    await state.update_data(set_email_index=idx)
    await safe_edit_text(
        callback.message,
        f"📧 <b>Set Email untuk Server {idx + 1}</b>\n\n"
        f"Kirim email Google account untuk auto-login.\n"
        f"Email harus bisa menerima verification code di generator.email.",
        reply_markup=gemini_input_keyboard(),
    )
    await callback.answer()
