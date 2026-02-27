import html
from pathlib import Path
from urllib.parse import unquote, urlparse

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from ..client import gateway_client
from ..keyboards import main_menu_keyboard, video_menu_keyboard
from ..rate_limiter import check_cooldown, record_request
from ..security import is_admin
from ..states import VideoFlow
from ..subscription_manager import subscription_manager
from ..ui import clear_state, get_backend, safe_edit_text
from ..user_limit_manager import user_limit_manager

router = Router()
ROOT_DIR = Path(__file__).resolve().parents[2]
VIDEOS_DIR = ROOT_DIR / "data" / "videos"

# Backend → video model mapping
BACKEND_VIDEO_MODEL = {
    "grok": "grok-2-video",
    "gemini": "gemini-veo",
}


def _resolve_local_video_path(url: str) -> Path | None:
    try:
        parsed = urlparse(url)
        filename = Path(unquote(parsed.path)).name
    except Exception:
        return None
    if not filename:
        return None
    file_path = VIDEOS_DIR / filename
    if file_path.exists() and file_path.is_file():
        return file_path
    return None


def _is_local_url(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return host in {"127.0.0.1", "localhost", "0.0.0.0"}


def _video_settings_text(aspect: str, duration: int, resolution: str, preset: str) -> str:
    return (
        "🎬 <b>Video Generator</b>\n"
        f"• Aspect ratio: <b>{aspect}</b>\n"
        f"• Duration: <b>{duration}s</b>\n"
        f"• Resolution: <b>{resolution}</b>\n"
        f"• Preset: <b>{preset}</b>\n\n"
        "Atur parameter, lalu klik <b>Enter Prompt</b>."
    )


async def _ensure_video_defaults(state: FSMContext) -> tuple[str, int, str, str]:
    data = await state.get_data()
    aspect = data.get("vid_aspect", "9:16")
    duration = data.get("vid_duration", 6)
    resolution = data.get("vid_resolution", "480p")
    preset = data.get("vid_preset", "normal")
    await state.update_data(
        vid_aspect=aspect,
        vid_duration=duration,
        vid_resolution=resolution,
        vid_preset=preset,
    )
    return aspect, duration, resolution, preset


@router.callback_query(F.data == "menu:video")
async def open_video_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await clear_state(state)
    user_id = callback.from_user.id if callback.from_user else 0
    backend = await get_backend(state)

    # Gemini: no settings, go straight to prompt (landscape, 8s, fixed)
    if backend == "gemini":
        admin_user = is_admin(user_id)
        tier = await subscription_manager.get_tier(user_id)
        allowed_cd, remaining_cd = check_cooldown(user_id, tier, is_admin=admin_user)
        if not allowed_cd:
            await callback.answer(f"⏱ Cooldown! Tunggu {remaining_cd} detik lagi.", show_alert=True)
            return
        allowed, status = await user_limit_manager.can_consume(
            user_id, video_units=1, is_admin_user=admin_user,
        )
        if not allowed:
            await callback.answer("Limit video harian habis", show_alert=True)
            await safe_edit_text(
                callback.message,
                (
                    "❌ <b>Limit video harian habis</b>\n"
                    f"Sisa video hari ini: <b>{status['videos_remaining']}</b>\n"
                    "Cek menu <b>My Limit</b> untuk detail."
                ),
                reply_markup=main_menu_keyboard(backend),
            )
            return
        await state.set_state(VideoFlow.waiting_prompt)
        await safe_edit_text(
            callback.message,
            "🎬 <b>Gemini Video Generator</b>\n"
            "• Format: <b>Landscape</b> (otomatis)\n"
            "• Durasi: <b>8 detik</b>\n\n"
            "✍️ Kirim prompt video sekarang.",
        )
        await callback.answer()
        return

    # Grok: show settings menu
    aspect, duration, resolution, preset = await _ensure_video_defaults(state)
    await safe_edit_text(
        callback.message,
        _video_settings_text(aspect, duration, resolution, preset),
        reply_markup=video_menu_keyboard(aspect, duration, resolution, preset),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("vid:aspect:"))
async def set_video_aspect(callback: CallbackQuery, state: FSMContext) -> None:
    aspect = callback.data.replace("vid:aspect:", "", 1)
    current_aspect, duration, resolution, preset = await _ensure_video_defaults(state)
    if current_aspect == aspect:
        await callback.answer("Aspect ratio sudah aktif")
        return
    await state.update_data(vid_aspect=aspect)
    await safe_edit_text(
        callback.message,
        _video_settings_text(aspect, duration, resolution, preset),
        reply_markup=video_menu_keyboard(aspect, duration, resolution, preset),
    )
    await callback.answer("Aspect ratio diubah")


@router.callback_query(F.data.startswith("vid:duration:"))
async def set_video_duration(callback: CallbackQuery, state: FSMContext) -> None:
    duration = int(callback.data.replace("vid:duration:", "", 1))
    aspect, current_duration, resolution, preset = await _ensure_video_defaults(state)
    if current_duration == duration:
        await callback.answer("Duration sudah aktif")
        return
    await state.update_data(vid_duration=duration)
    await safe_edit_text(
        callback.message,
        _video_settings_text(aspect, duration, resolution, preset),
        reply_markup=video_menu_keyboard(aspect, duration, resolution, preset),
    )
    await callback.answer("Duration diubah")


@router.callback_query(F.data.startswith("vid:resolution:"))
async def set_video_resolution(callback: CallbackQuery, state: FSMContext) -> None:
    resolution = callback.data.replace("vid:resolution:", "", 1)
    aspect, duration, current_resolution, preset = await _ensure_video_defaults(state)
    if current_resolution == resolution:
        await callback.answer("Resolution sudah aktif")
        return
    await state.update_data(vid_resolution=resolution)
    await safe_edit_text(
        callback.message,
        _video_settings_text(aspect, duration, resolution, preset),
        reply_markup=video_menu_keyboard(aspect, duration, resolution, preset),
    )
    await callback.answer("Resolution diubah")


@router.callback_query(F.data.startswith("vid:preset:"))
async def set_video_preset(callback: CallbackQuery, state: FSMContext) -> None:
    preset = callback.data.replace("vid:preset:", "", 1)
    aspect, duration, resolution, current_preset = await _ensure_video_defaults(state)
    if current_preset == preset:
        await callback.answer("Preset sudah aktif")
        return
    await state.update_data(vid_preset=preset)
    await safe_edit_text(
        callback.message,
        _video_settings_text(aspect, duration, resolution, preset),
        reply_markup=video_menu_keyboard(aspect, duration, resolution, preset),
    )
    await callback.answer("Preset diubah")


@router.callback_query(F.data == "vid:prompt")
async def ask_video_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id if callback.from_user else 0
    admin_user = is_admin(user_id)

    # Rate limit check
    tier = await subscription_manager.get_tier(user_id)
    allowed_cd, remaining_cd = check_cooldown(user_id, tier, is_admin=admin_user)
    if not allowed_cd:
        await callback.answer(f"⏱ Cooldown! Tunggu {remaining_cd} detik lagi.", show_alert=True)
        return

    allowed, status = await user_limit_manager.can_consume(
        user_id,
        video_units=1,
        is_admin_user=admin_user,
    )
    if not allowed:
        await callback.answer("Limit video harian habis", show_alert=True)
        await safe_edit_text(
            callback.message,
            (
                "❌ <b>Limit video harian habis</b>\n"
                f"Sisa video hari ini: <b>{status['videos_remaining']}</b>\n"
                "Cek menu <b>My Limit</b> untuk detail."
            ),
            reply_markup=main_menu_keyboard(await get_backend(state)),
        )
        return

    await state.set_state(VideoFlow.waiting_prompt)
    await safe_edit_text(callback.message, "Kirim prompt video sekarang.")
    await callback.answer()


@router.message(VideoFlow.waiting_prompt)
async def handle_video_prompt(message: Message, state: FSMContext) -> None:
    prompt = (message.text or "").strip()
    if not prompt:
        await message.answer("Prompt tidak boleh kosong. Kirim ulang.")
        return

    user_id = message.from_user.id if message.from_user else 0
    admin_user = is_admin(user_id)
    allowed, status = await user_limit_manager.can_consume(
        user_id,
        video_units=1,
        is_admin_user=admin_user,
    )
    if not allowed:
        await clear_state(state)
        await message.answer(
            (
                "❌ Limit video harian habis.\n"
                f"Sisa video hari ini: {status['videos_remaining']}"
            )
        )
        await message.answer("🏠 <b>Main Menu</b>\nPilih fitur yang ingin digunakan:", reply_markup=main_menu_keyboard(await get_backend(state)))
        return

    aspect, duration, resolution, preset = await _ensure_video_defaults(state)
    wait_msg = await message.answer("⏳ Sedang generate video... proses bisa lebih lama")

    data = await state.get_data()
    backend = data.get("backend", "grok")
    model = BACKEND_VIDEO_MODEL.get(backend, "grok-2-video")

    # Gemini: override to fixed landscape 8s
    if backend == "gemini":
        aspect = "16:9"
        duration = 8
        resolution = "720p"
        preset = "normal"

    try:
        payload = await gateway_client.generate_video(
            prompt=prompt,
            aspect_ratio=aspect,
            duration_seconds=duration,
            resolution=resolution,
            preset=preset,
            model=model,
        )
        data = payload.get("data", [])
        item = data[0] if data else {}
        video_url = item.get("video_url") or item.get("url")

        if not video_url:
            await wait_msg.edit_text("❌ Gagal: video URL tidak ditemukan di response.")
        else:
            try:
                await wait_msg.delete()
            except Exception:
                pass
            sent = False
            local_path = _resolve_local_video_path(video_url)
            if local_path:
                try:
                    await message.answer_video(video=FSInputFile(str(local_path)))
                    sent = True
                except Exception:
                    sent = False
                if not sent:
                    try:
                        await message.answer_document(document=FSInputFile(str(local_path)))
                        sent = True
                    except Exception:
                        sent = False
            if sent:
                await user_limit_manager.consume(
                    user_id,
                    video_units=1,
                    is_admin_user=admin_user,
                )
                record_request(user_id)
                await clear_state(state)
                await message.answer("🏠 <b>Main Menu</b>\nPilih fitur yang ingin digunakan:", reply_markup=main_menu_keyboard(await get_backend(state)))
                return
            if not _is_local_url(video_url):
                try:
                    await message.answer_video(video=video_url)
                    sent = True
                except Exception:
                    sent = False
            if not sent:
                await message.answer(video_url)
            else:
                await user_limit_manager.consume(
                    user_id,
                    video_units=1,
                    is_admin_user=admin_user,
                )
                record_request(user_id)
    except Exception as exc:
        exc_str = str(exc)
        if "403" in exc_str and ("Just a moment" in exc_str or "DOCTYPE" in exc_str or "Cloudflare" in exc_str):
            err_msg = (
                "❌ <b>Generate video gagal: Cloudflare Block (403)</b>\n\n"
                "Gateway ditolak oleh Cloudflare karena IP server berbeda dari IP saat mengambil "
                "<code>CF_CLEARANCE</code>.\n\n"
                "<b>Solusi:</b> Jalankan gateway di local PC kamu, lalu update "
                "<code>CF_CLEARANCE</code> di file <code>.env</code>."
            )
        elif "rate_limit" in exc_str or "429" in exc_str:
            err_msg = "❌ <b>Rate limit</b>: SSO key sudah mencapai batas. Coba beberapa saat lagi."
        elif "401" in exc_str or "unauthorized" in exc_str.lower():
            err_msg = "❌ <b>Unauthorized</b>: SSO token tidak valid atau sudah kadaluarsa."
        else:
            short = html.escape(exc_str[:300])
            err_msg = f"❌ <b>Generate video gagal:</b>\n<code>{short}</code>"
        try:
            await wait_msg.edit_text(err_msg)
        except Exception:
            await wait_msg.edit_text("❌ Generate video gagal.")

    await clear_state(state)
    await message.answer("🏠 <b>Main Menu</b>\nPilih fitur yang ingin digunakan:", reply_markup=main_menu_keyboard(await get_backend(state)))
