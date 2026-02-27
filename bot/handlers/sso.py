from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ..client import gateway_client
from ..config import settings
from ..keyboards import admin_menu_keyboard, sso_add_input_keyboard, sso_menu_keyboard
from ..security import is_admin
from ..sso_manager import LocalSSOManager
from ..states import SSOFlow
from ..ui import clear_state, safe_edit_text

router = Router()
local_sso_manager = LocalSSOManager(settings.SSO_FILE)


@router.callback_query(F.data == "menu:sso")
async def open_sso_menu(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id if callback.from_user else 0
    if not is_admin(user_id):
        await callback.answer("Akses SSO manager ditolak", show_alert=True)
        return

    await callback.message.edit_text(
        "🔐 <b>SSO Manager</b>\nKelola key SSO lokal untuk gateway.",
        reply_markup=sso_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "sso:list")
async def list_sso_keys(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id if callback.from_user else 0
    if not is_admin(user_id):
        await callback.answer("Akses SSO manager ditolak", show_alert=True)
        return

    summary = local_sso_manager.get_masked_summary()
    if not summary:
        text = "Belum ada key di file key.txt"
    else:
        text = "📋 <b>SSO Key Summary</b>\n" + "\n".join(summary)

    await safe_edit_text(callback.message, text, reply_markup=sso_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "sso:add")
async def add_sso_start(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id if callback.from_user else 0
    if not is_admin(user_id):
        await callback.answer("Akses SSO manager ditolak", show_alert=True)
        return

    await state.update_data(sso_return_menu="sso")
    await state.set_state(SSOFlow.waiting_new_key)
    await safe_edit_text(
        callback.message,
        "Kirim 1 value sso baru (tanpa prefix).",
        reply_markup=sso_add_input_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "sso:add:cancel")
async def add_sso_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id if callback.from_user else 0
    if not is_admin(user_id):
        await callback.answer("Akses SSO manager ditolak", show_alert=True)
        return

    data = await state.get_data()
    return_menu = data.get("sso_return_menu", "sso")
    await clear_state(state)

    if return_menu == "admin":
        await safe_edit_text(
            callback.message,
            "🛠 <b>Admin Panel</b>\nPilih aksi admin:",
            reply_markup=admin_menu_keyboard(),
        )
    else:
        await safe_edit_text(
            callback.message,
            "🔐 <b>SSO Manager</b>\nKelola key SSO lokal untuk gateway.",
            reply_markup=sso_menu_keyboard(),
        )
    await callback.answer("Dibatalkan")


@router.message(SSOFlow.waiting_new_key)
async def add_sso_finish(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id if message.from_user else 0
    if not is_admin(user_id):
        await clear_state(state)
        await message.answer("Akses SSO manager ditolak")
        return

    data = await state.get_data()
    return_menu = data.get("sso_return_menu", "sso")
    value = (message.text or "").strip()
    result = local_sso_manager.add_key(value)
    await clear_state(state)

    if return_menu == "admin":
        menu_text = "🛠 <b>Admin Panel</b>\nPilih aksi admin:"
        menu_keyboard = admin_menu_keyboard()
    else:
        menu_text = "🔐 <b>SSO Manager</b>\nKelola key SSO lokal untuk gateway."
        menu_keyboard = sso_menu_keyboard()

    if result["status"] == "error":
        await message.answer(f"❌ {result['message']}")
        await message.answer(menu_text, reply_markup=menu_keyboard)
        return

    if result["status"] == "exists":
        before_count = int(result.get("before_count", 0) or 0)
        after_count = int(result.get("after_count", before_count) or before_count)
        await message.answer(
            f"⚠️ {result['message']}\n"
            f"Total key: {before_count} -> {after_count}"
        )
        await message.answer(menu_text, reply_markup=menu_keyboard)
        return

    try:
        reload_result = await gateway_client.reload_sso()
        before_count = int(result.get("before_count", 0) or 0)
        after_count = int(result.get("after_count", before_count) or before_count)
        await message.answer(
            f"✅ {result['message']}\n"
            f"Total key: {before_count} -> {after_count}\n"
            f"🔄 Reload gateway: {reload_result}"
        )
    except Exception as exc:
        before_count = int(result.get("before_count", 0) or 0)
        after_count = int(result.get("after_count", before_count) or before_count)
        await message.answer(
            f"✅ {result['message']}\n"
            f"Total key: {before_count} -> {after_count}\n"
            f"⚠️ Reload gateway gagal: {exc}"
        )
    await message.answer(menu_text, reply_markup=menu_keyboard)


@router.callback_query(F.data == "sso:reload")
async def sso_reload(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id if callback.from_user else 0
    if not is_admin(user_id):
        await callback.answer("Akses SSO manager ditolak", show_alert=True)
        return

    try:
        payload = await gateway_client.reload_sso()
        await safe_edit_text(callback.message, f"✅ Reload SSO selesai: {payload}", reply_markup=sso_menu_keyboard())
    except Exception as exc:
        await safe_edit_text(callback.message, f"❌ Reload SSO gagal: {exc}", reply_markup=sso_menu_keyboard())

    await callback.answer()


@router.callback_query(F.data == "sso:remove_last")
async def sso_remove_last(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id if callback.from_user else 0
    if not is_admin(user_id):
        await callback.answer("Akses SSO manager ditolak", show_alert=True)
        return

    result = local_sso_manager.remove_last_key()
    if result["status"] != "ok":
        await safe_edit_text(callback.message, f"❌ {result['message']}", reply_markup=sso_menu_keyboard())
        await callback.answer()
        return

    try:
        payload = await gateway_client.reload_sso()
        await safe_edit_text(callback.message, f"✅ {result['message']}\n🔄 Reload SSO: {payload}", reply_markup=sso_menu_keyboard())
    except Exception as exc:
        await safe_edit_text(callback.message, f"✅ {result['message']}\n⚠️ Reload gateway gagal: {exc}", reply_markup=sso_menu_keyboard())

    await callback.answer()
