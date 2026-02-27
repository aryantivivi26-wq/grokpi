from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from urllib.parse import quote

from ..client import gateway_client
from ..keyboards import admin_menu_keyboard, delete_confirm_keyboard, media_page_keyboard, sso_add_input_keyboard
from ..security import is_admin
from ..states import SSOFlow
from ..ui import safe_edit_text

router = Router()
PAGE_SIZE = 5


def _format_status(payload: dict) -> str:
    lines = ["📊 <b>Gateway Status</b>"]
    lines.append(f"• service: <b>{payload.get('service', 'unknown')}</b>")

    config = payload.get("config") or {}
    if isinstance(config, dict):
        for key in ["host", "port", "images_dir", "videos_dir", "rotation_strategy", "daily_limit"]:
            if key in config:
                lines.append(f"• {key}: <b>{config.get(key)}</b>")

    sso = payload.get("sso")
    if isinstance(sso, dict):
        lines.append("\n🔐 <b>SSO</b>")
        for key, value in sso.items():
            lines.append(f"• {key}: <b>{value}</b>")

    return "\n".join(lines)


def _ensure_admin(callback: CallbackQuery) -> bool:
    user_id = callback.from_user.id if callback.from_user else 0
    return is_admin(user_id)


async def _show_image_list(callback: CallbackQuery, state: FSMContext, start: int = 0) -> None:
    payload = await gateway_client.list_images(limit=50)
    images = payload.get("images", [])
    await state.update_data(admin_image_items=images)

    if not images:
        await safe_edit_text(callback.message, "Belum ada image cache.", reply_markup=admin_menu_keyboard())
        return

    end = min(start + PAGE_SIZE, len(images))
    lines = [f"🖼 <b>Image Cache (latest)</b>\nMenampilkan {start + 1}-{end} dari {len(images)}"]
    for idx, item in enumerate(images[start:end], start=start + 1):
        lines.append(f"{idx}. {item.get('filename')}\n{item.get('url')}")

    await safe_edit_text(
        callback.message,
        "\n\n".join(lines),
        reply_markup=media_page_keyboard("images", start, end, len(images)),
    )


async def _show_video_list(callback: CallbackQuery, state: FSMContext, start: int = 0) -> None:
    payload = await gateway_client.list_videos(limit=50)
    videos = payload.get("videos", [])
    await state.update_data(admin_video_items=videos)

    if not videos:
        await safe_edit_text(callback.message, "Belum ada video cache.", reply_markup=admin_menu_keyboard())
        return

    end = min(start + PAGE_SIZE, len(videos))
    lines = [f"🎬 <b>Video Cache (latest)</b>\nMenampilkan {start + 1}-{end} dari {len(videos)}"]
    for idx, item in enumerate(videos[start:end], start=start + 1):
        lines.append(f"{idx}. {item.get('filename')}\n{item.get('url')}")

    await safe_edit_text(
        callback.message,
        "\n\n".join(lines),
        reply_markup=media_page_keyboard("videos", start, end, len(videos)),
    )


@router.callback_query(F.data == "menu:admin")
async def open_admin_menu(callback: CallbackQuery) -> None:
    if not _ensure_admin(callback):
        await callback.answer("Akses admin ditolak", show_alert=True)
        return

    await callback.message.edit_text(
        "🛠 <b>Admin Panel</b>\nPilih aksi admin:",
        reply_markup=admin_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin:status")
async def admin_status(callback: CallbackQuery) -> None:
    if not _ensure_admin(callback):
        await callback.answer("Akses admin ditolak", show_alert=True)
        return

    try:
        payload = await gateway_client.admin_status()
        text = _format_status(payload)
    except Exception as exc:
        text = f"❌ Gagal ambil status: {exc}"

    await safe_edit_text(callback.message, text, reply_markup=admin_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "admin:reload_sso")
async def admin_reload_sso(callback: CallbackQuery) -> None:
    if not _ensure_admin(callback):
        await callback.answer("Akses admin ditolak", show_alert=True)
        return

    try:
        payload = await gateway_client.reload_sso()
        await safe_edit_text(callback.message, f"✅ Reload SSO: {payload}", reply_markup=admin_menu_keyboard())
    except Exception as exc:
        await safe_edit_text(callback.message, f"❌ Reload SSO gagal: {exc}", reply_markup=admin_menu_keyboard())

    await callback.answer()


@router.callback_query(F.data == "admin:add_key")
async def admin_add_key(callback: CallbackQuery, state: FSMContext) -> None:
    if not _ensure_admin(callback):
        await callback.answer("Akses admin ditolak", show_alert=True)
        return

    await state.update_data(sso_return_menu="admin")
    await state.set_state(SSOFlow.waiting_new_key)
    await safe_edit_text(
        callback.message,
        "Kirim 1 value sso baru (tanpa prefix).",
        reply_markup=sso_add_input_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin:images")
async def admin_images(callback: CallbackQuery, state: FSMContext) -> None:
    if not _ensure_admin(callback):
        await callback.answer("Akses admin ditolak", show_alert=True)
        return

    try:
        await _show_image_list(callback, state)
    except Exception as exc:
        await safe_edit_text(callback.message, f"❌ Gagal load image cache: {exc}", reply_markup=admin_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "admin:videos")
async def admin_videos(callback: CallbackQuery, state: FSMContext) -> None:
    if not _ensure_admin(callback):
        await callback.answer("Akses admin ditolak", show_alert=True)
        return

    try:
        await _show_video_list(callback, state)
    except Exception as exc:
        await safe_edit_text(callback.message, f"❌ Gagal load video cache: {exc}", reply_markup=admin_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("admin:page:"))
async def admin_media_page(callback: CallbackQuery, state: FSMContext) -> None:
    if not _ensure_admin(callback):
        await callback.answer("Akses admin ditolak", show_alert=True)
        return

    parts = (callback.data or "").split(":")
    if len(parts) != 4:
        await callback.answer("Aksi tidak valid", show_alert=True)
        return

    _, _, media_type, start_raw = parts
    try:
        start = max(0, int(start_raw))
    except ValueError:
        await callback.answer("Halaman tidak valid", show_alert=True)
        return

    try:
        if media_type == "images":
            await _show_image_list(callback, state, start=start)
        else:
            await _show_video_list(callback, state, start=start)
    except Exception as exc:
        await safe_edit_text(callback.message, f"❌ Gagal buka halaman media: {exc}", reply_markup=admin_menu_keyboard())

    await callback.answer()


@router.callback_query(F.data.startswith("admin:deleteask:"))
async def admin_delete_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    if not _ensure_admin(callback):
        await callback.answer("Akses admin ditolak", show_alert=True)
        return

    parts = (callback.data or "").split(":")
    if len(parts) != 4:
        await callback.answer("Aksi tidak valid", show_alert=True)
        return

    _, _, media_type, idx_raw = parts
    try:
        idx = int(idx_raw)
    except ValueError:
        await callback.answer("Index tidak valid", show_alert=True)
        return

    data = await state.get_data()
    items_key = "admin_image_items" if media_type == "images" else "admin_video_items"
    items = data.get(items_key, [])
    if idx < 0 or idx >= len(items):
        await callback.answer("Data list sudah tidak sinkron, refresh dulu", show_alert=True)
        return

    filename = items[idx].get("filename", "unknown")
    back_start = (idx // PAGE_SIZE) * PAGE_SIZE
    await safe_edit_text(
        callback.message,
        f"⚠️ Konfirmasi hapus {media_type[:-1]}:\n<b>{filename}</b>",
        reply_markup=delete_confirm_keyboard(media_type, idx, back_start),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:deleteok:"))
async def admin_delete_media(callback: CallbackQuery, state: FSMContext) -> None:
    if not _ensure_admin(callback):
        await callback.answer("Akses admin ditolak", show_alert=True)
        return

    parts = (callback.data or "").split(":")
    if len(parts) != 4:
        await callback.answer("Aksi tidak valid", show_alert=True)
        return

    _, _, media_type, idx_raw = parts
    try:
        idx = int(idx_raw)
    except ValueError:
        await callback.answer("Index tidak valid", show_alert=True)
        return

    data = await state.get_data()
    items_key = "admin_image_items" if media_type == "images" else "admin_video_items"
    items = data.get(items_key, [])

    if idx < 0 or idx >= len(items):
        await callback.answer("Data list sudah tidak sinkron, refresh dulu", show_alert=True)
        return

    filename = items[idx].get("filename", "")
    if not filename:
        await callback.answer("Filename tidak valid", show_alert=True)
        return
    encoded = quote(filename, safe="")
    back_start = (idx // PAGE_SIZE) * PAGE_SIZE

    try:
        if media_type == "images":
            await gateway_client.delete_image(encoded)
            await _show_image_list(callback, state, start=back_start)
        else:
            await gateway_client.delete_video(encoded)
            await _show_video_list(callback, state, start=back_start)
    except Exception as exc:
        await safe_edit_text(callback.message, f"❌ Gagal hapus media: {exc}", reply_markup=admin_menu_keyboard())

    await callback.answer()
