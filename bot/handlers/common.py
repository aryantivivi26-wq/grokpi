import time as _time
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import database as db
from ..keyboards import admin_menu_keyboard, backend_select_keyboard, gemini_menu_keyboard, main_menu_keyboard, sso_menu_keyboard
from ..security import is_admin
from ..subscription_manager import (
    DURATION_LABELS,
    TIER_LABELS,
    TIER_LIMITS,
    UNLIMITED,
    Tier,
    subscription_manager,
)
from ..ui import clear_state, get_backend, safe_edit_text
from ..user_limit_manager import user_limit_manager

router = Router()

HOME_TEXT = (
    "<b>Hubify Studio</b> — Bot pembuat gambar &amp; video AI.\n"
    "Pilih menu di bawah untuk mulai."
)

# Trial duration: 12 hours
TRIAL_SECONDS = 12 * 3600


# ---------------------------------------------------------------------------
# /start — welcome with user statistics + referral + trial
# ---------------------------------------------------------------------------

@router.message(CommandStart(deep_link=True))
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, command: CommandObject = None) -> None:
    user = message.from_user
    user_id = user.id if user else 0
    name = user.first_name if user else "User"
    username = f"@{user.username}" if user and user.username else "-"
    now = datetime.now()

    # Track user in database (returns True if brand new)
    is_new = await db.upsert_user(
        user_id=user_id,
        first_name=user.first_name if user else "",
        username=user.username if user and user.username else "",
    )

    extra_messages: list[str] = []

    # --- Referral deep link processing ---
    if command and command.args and command.args.startswith("ref_"):
        try:
            referrer_id = int(command.args.replace("ref_", "", 1))
            if is_new and referrer_id != user_id:
                from .referral import process_referral
                ref_msg = await process_referral(user_id, referrer_id)
                if ref_msg:
                    extra_messages.append(ref_msg)
        except (ValueError, TypeError):
            pass

    # --- Auto-trial for new users (12h Premium) ---
    if is_new:
        user_data = await db.get_user(user_id)
        if user_data and not user_data.get("trial_used", 0):
            import time
            trial_expires = time.time() + TRIAL_SECONDS
            await db.upsert_subscription(
                user_id=user_id,
                tier=Tier.PREMIUM.value,
                expires=trial_expires,
                granted_by=0,
                granted_at=time.time(),
            )
            await db.mark_trial_used(user_id)
            extra_messages.append(
                "🎁 <b>Selamat Datang!</b>\n\n"
                "Kamu mendapat <b>💎 Premium Trial 12 Jam</b> gratis.\n\n"
                "Selama trial, kamu bisa:\n"
                "• Generate gambar &amp; video <b>tanpa batas</b>\n"
                "• Batch beberapa prompt sekaligus\n\n"
                "<i>Trial berakhir otomatis setelah 12 jam.</i>"
            )

    # Subscription info
    sub = await subscription_manager.get_subscription(user_id)
    tier = Tier(sub.tier) if sub.tier in [t.value for t in Tier] else Tier.FREE
    tier_label = TIER_LABELS[tier]
    limits = TIER_LIMITS[tier]

    # Usage info
    admin_user = is_admin(user_id)
    status = await user_limit_manager.get_status(user_id, is_admin_user=admin_user)

    # Bot stats
    stats = await db.get_bot_stats()

    # Build welcome text
    backend = await get_backend(state)
    backend_label = {"grok": "⚡ Grok", "gemini": "✦ Gemini"}.get(backend, backend)

    lines = [
        f"Halo, <b>{name}</b>! Selamat datang di <b>Hubify Studio</b>.",
        f"Bot ini bisa membuat <b>gambar</b> dan <b>video</b> dari teks menggunakan AI.\n",
        f"<code>{user_id}</code> · {username} · {tier_label}",
        f"Model aktif: <b>{backend_label}</b>",
        f"<i>Tekan tombol model di bawah kalau mau ganti.</i>",
    ]

    # Subscription status
    if tier != Tier.FREE and sub.expires > 0:
        remaining = sub.expires - _time.time()
        if remaining > 0:
            days = int(remaining // 86400)
            hours = int((remaining % 86400) // 3600)
            mins = int((remaining % 3600) // 60)
            if days > 0:
                lines.append(f"\n💎 Langganan · sisa <b>{days}h {hours}j {mins}m</b>")
            else:
                lines.append(f"\n💎 Langganan · sisa <b>{hours}j {mins}m</b>")
        else:
            lines.append("\n💎 Langganan · <b>Expired</b>")

    # Daily usage
    if admin_user:
        lines.append("\n📊 Kuota hari ini · <b>Unlimited</b>")
    else:
        img_lim = limits.images_per_day
        vid_lim = limits.videos_per_day
        img_used = status["images_used"]
        vid_used = status["videos_used"]
        img_txt = f"{img_used}/∞" if img_lim >= UNLIMITED else f"{img_used}/{img_lim}"
        vid_txt = f"{vid_used}/∞" if vid_lim >= UNLIMITED else f"{vid_used}/{vid_lim}"
        lines.append(f"\n📊 Image <b>{img_txt}</b> · Video <b>{vid_txt}</b>")

        extra_img = status.get("extra_images", 0)
        extra_vid = status.get("extra_videos", 0)
        if extra_img > 0 or extra_vid > 0:
            lines.append(f"📦 Extra: <b>{extra_img}</b> img · <b>{extra_vid}</b> vid")

    # Bot statistics
    lines.append(
        f"\n👥 <b>{stats['total_users']}</b> users · "
        f"<b>{stats['active_subs']}</b> subs · "
        f"<b>{stats['active_today']}</b> aktif"
    )

    # Send extra messages first (referral bonus, trial)
    for extra_msg in extra_messages:
        await message.answer(extra_msg)

    await message.answer("\n".join(lines), reply_markup=main_menu_keyboard(backend))


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    text = (
        "<b>Bantuan — Cara Pakai Hubify Studio</b>\n"
        "─────────────────\n\n"
        "<b>Cara mulai:</b>\n"
        "1. Tekan /start untuk buka menu\n"
        "2. Pilih <b>🖼 Image</b> atau <b>🎬 Video</b>\n"
        "3. Atur pengaturan lalu ketik perintah (prompt)\n"
        "4. Tunggu hasil jadi — bot akan kirim hasilnya\n\n"
        "<b>Menu:</b>\n"
        "🖼 <b>Image</b> — Buat gambar dari teks\n"
        "🎬 <b>Video</b> — Buat video pendek dari teks\n"
        "💎 <b>Langganan</b> — Lihat/upgrade paket kamu\n"
        "📊 <b>Kuota</b> — Cek sisa jatah harian\n"
        "📦 <b>Topup</b> — Beli kuota tambahan (tidak expired)\n"
        "🏆 <b>Ranking</b> — Papan peringkat bulanan\n"
        "🔗 <b>Referral</b> — Ajak teman, dapat bonus gratis\n\n"
        "<b>Perintah:</b>\n"
        "/start — Kembali ke menu utama\n"
        "/help — Tampilkan bantuan ini\n"
        "/cancel — Batalkan proses yang sedang berjalan\n\n"
        "<i>Tanya jawab:\n"
        "• User baru otomatis dapat trial Premium 12 jam.\n"
        "• Referral → kamu &amp; teman dapat +10 image gratis.\n"
        "• Kuota topup tidak pernah expired.</i>"
    )
    await message.answer(text)


# ---------------------------------------------------------------------------
# /admin — admin panel (command only, not in main menu)
# ---------------------------------------------------------------------------

@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else 0
    if not is_admin(user_id):
        await message.answer("❌ Akses ditolak. Khusus admin.")
        return
    await message.answer(
        "<b>Admin Panel</b>",
        reply_markup=admin_menu_keyboard(),
    )


@router.message(Command("gemini"))
async def cmd_gemini(message: Message) -> None:
    """Shortcut to open Gemini Server Manager directly."""
    user_id = message.from_user.id if message.from_user else 0
    if not is_admin(user_id):
        await message.answer("❌ Akses ditolak. Khusus admin.")
        return

    # Import gemini_mgr to get server keyboard data
    from .gemini import gemini_mgr
    data = gemini_mgr.get_server_keyboard_data()
    kb = gemini_menu_keyboard(server_data=data if data else None)
    await message.answer(
        "<b>✦ Gemini Manager</b>\n"
        "<i>Kelola server Gemini Business.</i>",
        reply_markup=kb,
    )


@router.message(Command("sso"))
async def cmd_sso(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else 0
    if not is_admin(user_id):
        await message.answer("❌ Akses ditolak. Khusus admin.")
        return
    await message.answer(
        "<b>🔑 SSO Manager</b>",
        reply_markup=sso_menu_keyboard(),
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await clear_state(state)
    await message.answer("Dibatalkan.")
    await message.answer(HOME_TEXT, reply_markup=main_menu_keyboard(await get_backend(state)))


@router.callback_query(F.data == "menu:home")
async def to_home(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    backend = data.get("backend", "grok")
    await safe_edit_text(
        callback.message,
        HOME_TEXT,
        reply_markup=main_menu_keyboard(backend),
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Backend selection toggle
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "menu:backend")
async def open_backend_menu(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    current = data.get("backend", "grok")
    await safe_edit_text(
        callback.message,
        (
            "<b>Pilih Model AI</b>\n\n"
            "⚡ <b>Grok</b> — AI dari xAI. Bisa atur rasio, jumlah, batch.\n"
            "✦ <b>Gemini</b> — AI dari Google. Otomatis, tanpa pengaturan.\n\n"
            f"Saat ini aktif: <b>{current.title()}</b>\n"
            "<i>Tekan salah satu untuk mengganti model.</i>"
        ),
        reply_markup=backend_select_keyboard(current),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("backend:"))
async def set_backend(callback: CallbackQuery, state: FSMContext) -> None:
    new_backend = callback.data.replace("backend:", "", 1)
    data = await state.get_data()
    current = data.get("backend", "grok")

    if new_backend == current:
        await callback.answer(f"{new_backend.title()} sudah aktif")
        return

    await state.update_data(backend=new_backend)
    await safe_edit_text(
        callback.message,
        HOME_TEXT,
        reply_markup=main_menu_keyboard(new_backend),
    )
    await callback.answer(f"Model: {new_backend.title()}")


@router.callback_query(F.data == "menu:limit")
async def show_my_limit(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id if callback.from_user else 0
    admin_user = is_admin(user_id)
    status = await user_limit_manager.get_status(user_id, is_admin_user=admin_user)

    # get tier info
    tier = await subscription_manager.get_tier(user_id)
    tier_label = TIER_LABELS.get(tier, "Free")
    sub = await subscription_manager.get_subscription(user_id)

    if admin_user:
        text = (
            "<b>📊 Kuota Harian</b>\n\n"
            "Role: <b>Admin</b>\n"
            "Limit: <b>Unlimited</b>"
        )
    else:
        img_limit = status['images_limit']
        vid_limit = status['videos_limit']
        img_txt = f"{status['images_used']}/∞" if img_limit >= UNLIMITED else f"{status['images_used']}/{img_limit}"
        vid_txt = f"{status['videos_used']}/∞" if vid_limit >= UNLIMITED else f"{status['videos_used']}/{vid_limit}"

        text = (
            "<b>📊 Kuota Harian</b>\n"
            "<i>Jatah pemakaian kamu hari ini</i>\n"
            "─────────────────\n\n"
            f"Tier: <b>{tier_label}</b>\n"
        )

        if tier != Tier.FREE and sub.expires > 0:
            remaining = sub.expires - _time.time()
            if remaining > 0:
                days = int(remaining // 86400)
                hours = int((remaining % 86400) // 3600)
                mins = int((remaining % 3600) // 60)
                if days > 0:
                    text += f"Sisa: <b>{days}h {hours}j {mins}m</b>\n"
                else:
                    text += f"Sisa: <b>{hours}j {mins}m</b>\n"

        text += (
            f"\nImage: <b>{img_txt}</b> (gambar)\n"
            f"Video: <b>{vid_txt}</b> (video)\n"
            f"Reset: setiap hari pukul 00:00 WIB\n"
        )

        extra_img = status.get("extra_images", 0)
        extra_vid = status.get("extra_videos", 0)
        if extra_img > 0 or extra_vid > 0:
            text += f"\nExtra: <b>{extra_img}</b> img · <b>{extra_vid}</b> vid"

        from ..rate_limiter import get_cooldown_text
        text += f"\nCooldown: <b>{get_cooldown_text(tier)}</b>"
        text += "\n\n<i>Kuota reset otomatis setiap hari.\nMau lebih? Upgrade langganan atau topup.</i>"

    await safe_edit_text(callback.message, text, reply_markup=main_menu_keyboard(await get_backend(state)))
    await callback.answer()


@router.callback_query(F.data == "menu:clean")
async def clean_chat(callback: CallbackQuery, state: FSMContext) -> None:
    await clear_state(state)
    if callback.message:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(HOME_TEXT, reply_markup=main_menu_keyboard(await get_backend(state)))
    await callback.answer("Dibersihkan")


@router.callback_query(F.data == "noop")
async def noop_callback(callback: CallbackQuery) -> None:
    await callback.answer()


@router.message(StateFilter(None))
async def fallback_message(message: Message) -> None:
    await message.answer(
        "Perintah tidak dikenali.\n\n"
        "Ketik /start untuk buka menu utama,\n"
        "atau /help untuk panduan lengkap."
    )
