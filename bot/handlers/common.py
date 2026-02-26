from aiogram import F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from datetime import datetime

from ..keyboards import main_menu_keyboard
from ..security import is_admin
from ..ui import safe_edit_text
from ..user_limit_manager import user_limit_manager

router = Router()

HOME_TEXT = "🏠 <b>Main Menu</b>\nPilih fitur yang ingin digunakan:"


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(HOME_TEXT, reply_markup=main_menu_keyboard())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    text = (
        "ℹ️ <b>Help</b>\n"
        "• /start - buka menu utama\n"
        "• /help - bantuan\n"
        "• /cancel - batalkan flow aktif"
    )
    await message.answer(text)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("✅ Flow dibatalkan.")
    await message.answer(HOME_TEXT, reply_markup=main_menu_keyboard())


@router.callback_query(F.data == "menu:home")
async def to_home(callback: CallbackQuery) -> None:
    await safe_edit_text(
        callback.message,
        HOME_TEXT,
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "menu:limit")
async def show_my_limit(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id if callback.from_user else 0
    admin_user = is_admin(user_id)
    status = await user_limit_manager.get_status(user_id, is_admin_user=admin_user)

    if admin_user:
        text = (
            "📈 <b>My Limit</b>\n"
            "Role: <b>Admin</b>\n"
            "Status: <b>Unlimited</b>"
        )
    else:
        reset_ts = int(status.get("next_reset_timestamp", 0) or 0)
        reset_text = "-"
        if reset_ts > 0:
            reset_text = datetime.fromtimestamp(reset_ts).strftime("%Y-%m-%d %H:%M:%S")

        text = (
            "📈 <b>My Limit</b>\n"
            f"• Image: <b>{status['images_used']}/{status['images_limit']}</b> "
            f"(sisa {status['images_remaining']})\n"
            f"• Video: <b>{status['videos_used']}/{status['videos_limit']}</b> "
            f"(sisa {status['videos_remaining']})\n"
            f"• Reset: <b>{reset_text}</b>"
        )

    await safe_edit_text(callback.message, text, reply_markup=main_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "menu:clean")
async def clean_chat(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(HOME_TEXT, reply_markup=main_menu_keyboard())
    await callback.answer("Menu dibersihkan")


@router.callback_query(F.data == "noop")
async def noop_callback(callback: CallbackQuery) -> None:
    await callback.answer()


@router.message(StateFilter(None))
async def fallback_message(message: Message) -> None:
    await message.answer(
        "Perintah tidak dikenali. Gunakan /start untuk membuka menu atau /help untuk bantuan."
    )
