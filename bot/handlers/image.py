from pathlib import Path
from urllib.parse import unquote, urlparse

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from ..client import gateway_client
from ..keyboards import image_menu_keyboard, main_menu_keyboard
from ..security import is_admin
from ..states import ImageFlow
from ..ui import safe_edit_text
from ..user_limit_manager import user_limit_manager

router = Router()
ROOT_DIR = Path(__file__).resolve().parents[2]
IMAGES_DIR = ROOT_DIR / "data" / "images"


def _resolve_local_image_path(url: str) -> Path | None:
    try:
        parsed = urlparse(url)
        filename = Path(unquote(parsed.path)).name
    except Exception:
        return None
    if not filename:
        return None
    file_path = IMAGES_DIR / filename
    if file_path.exists() and file_path.is_file():
        return file_path
    return None


def _image_settings_text(aspect: str, n: int) -> str:
    return (
        "🖼 <b>Image Generator</b>\n"
        f"• Aspect ratio: <b>{aspect}</b>\n"
        f"• Jumlah gambar: <b>{n}</b>\n\n"
        "Atur parameter, lalu klik <b>Enter Prompt</b>."
    )


async def _ensure_image_defaults(state: FSMContext) -> tuple[str, int]:
    data = await state.get_data()
    aspect = data.get("img_aspect", "1:1")
    n = data.get("img_n", 1)
    await state.update_data(img_aspect=aspect, img_n=n)
    return aspect, n


@router.callback_query(F.data == "menu:image")
async def open_image_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    aspect, n = await _ensure_image_defaults(state)
    await safe_edit_text(
        callback.message,
        _image_settings_text(aspect, n),
        reply_markup=image_menu_keyboard(aspect, n),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("img:aspect:"))
async def set_image_aspect(callback: CallbackQuery, state: FSMContext) -> None:
    aspect = callback.data.replace("img:aspect:", "", 1)
    current_aspect, _ = await _ensure_image_defaults(state)
    if current_aspect == aspect:
        await callback.answer("Aspect ratio sudah aktif")
        return
    await state.update_data(img_aspect=aspect)
    _, n = await _ensure_image_defaults(state)
    await safe_edit_text(
        callback.message,
        _image_settings_text(aspect, n),
        reply_markup=image_menu_keyboard(aspect, n),
    )
    await callback.answer("Aspect ratio diubah")


@router.callback_query(F.data.startswith("img:n:"))
async def set_image_count(callback: CallbackQuery, state: FSMContext) -> None:
    n = int(callback.data.replace("img:n:", "", 1))
    aspect, current_n = await _ensure_image_defaults(state)
    if current_n == n:
        await callback.answer("Jumlah gambar sudah aktif")
        return
    await state.update_data(img_n=n)
    await safe_edit_text(
        callback.message,
        _image_settings_text(aspect, n),
        reply_markup=image_menu_keyboard(aspect, n),
    )
    await callback.answer("Jumlah gambar diubah")


@router.callback_query(F.data == "img:prompt")
async def ask_image_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id if callback.from_user else 0
    admin_user = is_admin(user_id)
    _, n = await _ensure_image_defaults(state)
    allowed, status = await user_limit_manager.can_consume(
        user_id,
        image_units=n,
        is_admin_user=admin_user,
    )
    if not allowed:
        await callback.answer("Limit image harian tidak cukup", show_alert=True)
        await safe_edit_text(
            callback.message,
            (
                "❌ <b>Limit image harian tidak cukup</b>\n"
                f"Sisa image hari ini: <b>{status['images_remaining']}</b>\n"
                "Cek menu <b>My Limit</b> untuk detail."
            ),
            reply_markup=main_menu_keyboard(),
        )
        return

    await state.set_state(ImageFlow.waiting_prompt)
    await safe_edit_text(callback.message, "Kirim prompt gambar sekarang.")
    await callback.answer()


@router.message(ImageFlow.waiting_prompt)
async def handle_image_prompt(message: Message, state: FSMContext) -> None:
    prompt = (message.text or "").strip()
    if not prompt:
        await message.answer("Prompt tidak boleh kosong. Kirim ulang.")
        return

    user_id = message.from_user.id if message.from_user else 0
    admin_user = is_admin(user_id)
    aspect, n = await _ensure_image_defaults(state)
    allowed, status = await user_limit_manager.can_consume(
        user_id,
        image_units=n,
        is_admin_user=admin_user,
    )
    if not allowed:
        await state.clear()
        await message.answer(
            (
                "❌ Limit image harian habis.\n"
                f"Sisa image hari ini: {status['images_remaining']}"
            )
        )
        await message.answer("🏠 <b>Main Menu</b>\nPilih fitur yang ingin digunakan:", reply_markup=main_menu_keyboard())
        return

    wait_msg = await message.answer("⏳ Sedang generate image...")

    try:
        payload = await gateway_client.generate_image(prompt=prompt, n=n, aspect_ratio=aspect)
        data = payload.get("data", [])
        urls = [item.get("url", "") for item in data if item.get("url")]
        if not urls:
            await wait_msg.edit_text(f"Gagal: response kosong\n{payload}")
        else:
            try:
                await wait_msg.delete()
            except Exception:
                pass
            for url in urls:
                sent = False
                local_path = _resolve_local_image_path(url)
                if local_path:
                    try:
                        await message.answer_photo(photo=FSInputFile(str(local_path)))
                        sent = True
                    except Exception:
                        sent = False
                if sent:
                    continue
                try:
                    await message.answer_photo(photo=url)
                    sent = True
                except Exception:
                    sent = False
                if not sent:
                    await message.answer(url)
            await user_limit_manager.consume(
                user_id,
                image_units=min(n, len(urls)),
                is_admin_user=admin_user,
            )
    except Exception as exc:
        await wait_msg.edit_text(f"❌ Generate image gagal: {exc}")

    await state.clear()
    await message.answer("🏠 <b>Main Menu</b>\nPilih fitur yang ingin digunakan:", reply_markup=main_menu_keyboard())
