from pathlib import Path
from urllib.parse import unquote, urlparse

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from ..client import gateway_client
from ..keyboards import image_menu_keyboard, main_menu_keyboard
from ..rate_limiter import check_cooldown, record_request
from ..security import is_admin
from ..states import ImageFlow
from ..subscription_manager import subscription_manager
from ..ui import clear_state, get_backend, safe_edit_text
from ..user_limit_manager import user_limit_manager
from .common import HOME_TEXT

router = Router()
ROOT_DIR = Path(__file__).resolve().parents[2]
IMAGES_DIR = ROOT_DIR / "data" / "images"

# Backend → image model mapping
BACKEND_IMAGE_MODEL = {
    "grok": "grok-2-image",
    "gemini": "gemini-imagen",
}


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


def _image_settings_text(aspect: str, n: int, max_batch: int = 1) -> str:
    batch_line = ""
    if max_batch > 1:
        batch_line = f" · Batch max <b>{max_batch}</b>"
    return (
        "<b>🖼 Buat Gambar</b>\n"
        f"Rasio <b>{aspect}</b> · Jumlah <b>{n}</b>{batch_line}\n\n"
        "Atur rasio dan jumlah gambar di bawah,\n"
        "lalu tekan <b>✏️ Tulis Prompt</b> dan ketik deskripsi gambar.\n"
        "<i>Contoh: kucing lucu memakai topi astronot</i>"
    )


async def _ensure_image_defaults(state: FSMContext) -> tuple[str, int]:
    data = await state.get_data()
    aspect = data.get("img_aspect", "1:1")
    n = data.get("img_n", 1)
    await state.update_data(img_aspect=aspect, img_n=n)
    return aspect, n


@router.callback_query(F.data == "menu:image")
async def open_image_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await clear_state(state)
    user_id = callback.from_user.id if callback.from_user else 0
    backend = await get_backend(state)

    # Gemini: no settings, go straight to prompt (always 1 image, landscape)
    if backend == "gemini":
        admin_user = is_admin(user_id)
        tier = await subscription_manager.get_tier(user_id)
        allowed_cd, remaining_cd = check_cooldown(user_id, tier, is_admin=admin_user)
        if not allowed_cd:
            await callback.answer(f"Cooldown {remaining_cd}s", show_alert=True)
            return
        allowed, status = await user_limit_manager.can_consume(
            user_id, image_units=1, is_admin_user=admin_user,
        )
        if not allowed:
            await callback.answer("Limit image habis", show_alert=True)
            await safe_edit_text(
                callback.message,
                f"Limit image habis. Sisa: <b>{status['images_remaining']}</b>",
                reply_markup=main_menu_keyboard(backend),
            )
            return
        await state.set_state(ImageFlow.waiting_prompt)
        await safe_edit_text(
            callback.message,
            "<b>✦ Gemini Image</b>\n"
            "Format dan rasio otomatis · 1 gambar per prompt\n\n"
            "Silakan ketik deskripsi gambar yang kamu inginkan.\n"
            "<i>Contoh: pemandangan gunung saat matahari terbit</i>",
        )
        await callback.answer()
        return

    # Grok: show settings menu
    tier_limits = await subscription_manager.get_limits(user_id)
    aspect, n = await _ensure_image_defaults(state)
    # clamp n to tier max
    if n > tier_limits.max_images_per_request:
        n = tier_limits.max_images_per_request
        await state.update_data(img_n=n)
    await safe_edit_text(
        callback.message,
        _image_settings_text(aspect, n, tier_limits.max_batch_prompts),
        reply_markup=image_menu_keyboard(aspect, n, tier_limits.max_images_per_request, tier_limits.max_batch_prompts),
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
    user_id = callback.from_user.id if callback.from_user else 0
    tier_limits = await subscription_manager.get_limits(user_id)
    await safe_edit_text(
        callback.message,
        _image_settings_text(aspect, n, tier_limits.max_batch_prompts),
        reply_markup=image_menu_keyboard(aspect, n, tier_limits.max_images_per_request, tier_limits.max_batch_prompts),
    )
    await callback.answer("Aspect ratio diubah")


@router.callback_query(F.data.startswith("img:n:"))
async def set_image_count(callback: CallbackQuery, state: FSMContext) -> None:
    n = int(callback.data.replace("img:n:", "", 1))
    aspect, current_n = await _ensure_image_defaults(state)
    user_id = callback.from_user.id if callback.from_user else 0
    tier_limits = await subscription_manager.get_limits(user_id)
    if n > tier_limits.max_images_per_request:
        await callback.answer(f"Tier kamu max {tier_limits.max_images_per_request} gambar/request", show_alert=True)
        return
    if current_n == n:
        await callback.answer("Jumlah gambar sudah aktif")
        return
    await state.update_data(img_n=n)
    await safe_edit_text(
        callback.message,
        _image_settings_text(aspect, n, tier_limits.max_batch_prompts),
        reply_markup=image_menu_keyboard(aspect, n, tier_limits.max_images_per_request, tier_limits.max_batch_prompts),
    )
    await callback.answer("Jumlah gambar diubah")


@router.callback_query(F.data == "img:prompt")
async def ask_image_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id if callback.from_user else 0
    admin_user = is_admin(user_id)

    # Rate limit check
    tier = await subscription_manager.get_tier(user_id)
    allowed_cd, remaining_cd = check_cooldown(user_id, tier, is_admin=admin_user)
    if not allowed_cd:
        await callback.answer(f"Cooldown {remaining_cd}s", show_alert=True)
        return

    _, n = await _ensure_image_defaults(state)
    allowed, status = await user_limit_manager.can_consume(
        user_id,
        image_units=n,
        is_admin_user=admin_user,
    )
    if not allowed:
        await callback.answer("Limit image habis", show_alert=True)
        await safe_edit_text(
            callback.message,
            f"Limit image habis. Sisa: <b>{status['images_remaining']}</b>",
            reply_markup=main_menu_keyboard(await get_backend(state)),
        )
        return

    await state.set_state(ImageFlow.waiting_prompt)
    await safe_edit_text(
        callback.message,
        "Ketik deskripsi gambar yang kamu inginkan.\n"
        "<i>Contoh: kucing lucu memakai topi astronot</i>"
    )
    await callback.answer()


@router.callback_query(F.data == "img:batch")
async def ask_batch_prompts(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id if callback.from_user else 0
    admin_user = is_admin(user_id)
    tier_limits = await subscription_manager.get_limits(user_id)

    if tier_limits.max_batch_prompts <= 1:
        await callback.answer("Upgrade tier untuk batch prompt", show_alert=True)
        return

    # Rate limit check
    tier = await subscription_manager.get_tier(user_id)
    allowed_cd, remaining_cd = check_cooldown(user_id, tier, is_admin=admin_user)
    if not allowed_cd:
        await callback.answer(f"Cooldown {remaining_cd}s", show_alert=True)
        return

    _, n = await _ensure_image_defaults(state)
    total_images = n * tier_limits.max_batch_prompts
    allowed, status = await user_limit_manager.can_consume(
        user_id,
        image_units=n,  # at least 1 prompt worth
        is_admin_user=admin_user,
    )
    if not allowed:
        await callback.answer("Limit image habis", show_alert=True)
        return

    await state.set_state(ImageFlow.waiting_batch_prompts)
    await safe_edit_text(
        callback.message,
        (
            f"<b>Batch Prompt</b>\n"
            f"Kirim beberapa deskripsi gambar sekaligus.\n\n"
            f"Tulis max <b>{tier_limits.max_batch_prompts}</b> prompt,\n"
            f"satu deskripsi per baris.\n"
            f"Tiap deskripsi menghasilkan <b>{n}</b> gambar.\n\n"
            f"<i>Contoh:</i>\n"
            f"<code>kucing lucu di taman\n"
            f"sunset di pantai\n"
            f"robot futuristik</code>"
        ),
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Helper: generate + send images for a single prompt
# ---------------------------------------------------------------------------

async def _generate_and_send(
    message: Message,
    prompt: str,
    n: int,
    aspect: str,
    user_id: int,
    admin_user: bool,
    prompt_label: str = "",
    model: str = "grok-2-image",
) -> int:
    """Generate images for one prompt. Returns number of images actually sent."""
    label = f" [{prompt_label}]" if prompt_label else ""
    wait_msg = await message.answer(f"⏳ Generating{label}…")

    try:
        payload = await gateway_client.generate_image(prompt=prompt, n=n, aspect_ratio=aspect, model=model)
        data = payload.get("data", [])
        urls = [item.get("url", "") for item in data if item.get("url")]
        if not urls:
            await wait_msg.edit_text(f"Gagal{label} — response kosong")
            return 0

        try:
            await wait_msg.delete()
        except Exception:
            pass

        sent_count = 0
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
                sent_count += 1
                continue
            try:
                await message.answer_photo(photo=url)
                sent = True
            except Exception:
                sent = False
            if not sent:
                await message.answer(url)
            sent_count += 1

        return sent_count
    except Exception as exc:
        await wait_msg.edit_text(f"Gagal{label}: {exc}")
        return 0


@router.message(ImageFlow.waiting_prompt)
async def handle_image_prompt(message: Message, state: FSMContext) -> None:
    prompt = (message.text or "").strip()
    if not prompt:
        await message.answer("Prompt tidak boleh kosong. Kirim ulang.")
        return

    user_id = message.from_user.id if message.from_user else 0
    admin_user = is_admin(user_id)
    data = await state.get_data()
    backend = data.get("backend", "grok")

    # Gemini: fixed 1 image, no forced aspect (user decides via prompt)
    if backend == "gemini":
        n = 1
        aspect = ""
    else:
        aspect, n = await _ensure_image_defaults(state)

    allowed, status = await user_limit_manager.can_consume(
        user_id,
        image_units=n,
        is_admin_user=admin_user,
    )
    if not allowed:
        await clear_state(state)
        await message.answer(
            f"Limit image habis. Sisa: {status['images_remaining']}"
        )
        await message.answer(HOME_TEXT, reply_markup=main_menu_keyboard(await get_backend(state)))
        return

    model = BACKEND_IMAGE_MODEL.get(backend, "grok-2-image")
    sent = await _generate_and_send(message, prompt, n, aspect, user_id, admin_user, model=model)
    if sent > 0:
        await user_limit_manager.consume(user_id, image_units=sent, is_admin_user=admin_user)
        record_request(user_id)

    await clear_state(state)
    await message.answer(HOME_TEXT, reply_markup=main_menu_keyboard(await get_backend(state)))


@router.message(ImageFlow.waiting_batch_prompts)
async def handle_batch_prompts(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if not raw:
        await message.answer("Prompt tidak boleh kosong. Kirim ulang.")
        return

    user_id = message.from_user.id if message.from_user else 0
    admin_user = is_admin(user_id)
    tier_limits = await subscription_manager.get_limits(user_id)
    aspect, n = await _ensure_image_defaults(state)

    # Parse prompts (one per line)
    prompts = [line.strip() for line in raw.splitlines() if line.strip()]
    if not prompts:
        await message.answer("Prompt tidak boleh kosong. Kirim ulang.")
        return

    max_batch = tier_limits.max_batch_prompts
    if len(prompts) > max_batch:
        await message.answer(
            f"Max {max_batch} prompt — hanya {max_batch} pertama diproses."
        )
        prompts = prompts[:max_batch]

    total_images_needed = n * len(prompts)
    allowed, status = await user_limit_manager.can_consume(
        user_id, image_units=total_images_needed, is_admin_user=admin_user,
    )
    if not allowed:
        # try to process as many as possible
        remaining = int(status["images_remaining"])
        can_do = remaining // n if n > 0 else 0
        if can_do <= 0:
            await clear_state(state)
            await message.answer(f"Limit image habis. Sisa: {remaining}")
            await message.answer(HOME_TEXT, reply_markup=main_menu_keyboard(await get_backend(state)))
            return
        await message.answer(
            f"Limit cukup untuk {can_do} prompt saja (sisa: {remaining})."
        )
        prompts = prompts[:can_do]

    await message.answer(f"Batch generate: <b>{len(prompts)}</b> prompt × <b>{n}</b> gambar…")

    data = await state.get_data()
    backend = data.get("backend", "grok")
    model = BACKEND_IMAGE_MODEL.get(backend, "grok-2-image")

    total_sent = 0
    for idx, prompt in enumerate(prompts, 1):
        sent = await _generate_and_send(
            message, prompt, n, aspect, user_id, admin_user,
            prompt_label=f"{idx}/{len(prompts)}",
            model=model,
        )
        if sent > 0:
            await user_limit_manager.consume(user_id, image_units=sent, is_admin_user=admin_user)
            total_sent += sent

    await message.answer(f"Batch selesai — <b>{total_sent}</b> gambar")
    if total_sent > 0:
        record_request(user_id)
    await clear_state(state)
    await message.answer(HOME_TEXT, reply_markup=main_menu_keyboard(await get_backend(state)))
