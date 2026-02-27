import time as _time
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import database as db
from ..keyboards import admin_menu_keyboard, backend_select_keyboard, main_menu_keyboard, sso_menu_keyboard
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

HOME_TEXT = "🏠 <b>Main Menu</b>\nPilih fitur yang ingin digunakan:"

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
                "🎁 <b>Selamat Datang!</b>\n"
                "Kamu mendapat <b>💎 Premium Trial 12 Jam</b> gratis!\n"
                "Nikmati generate tanpa batas selama trial berlaku. 🚀"
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
    lines = [
        f"Halo, <b>{name}</b>! 👋",
        f"Selamat datang di <b>GrokPi Bot</b>",
        f"{now.strftime('%A, %d %B %Y pukul %H.%M.%S')}\n",
        f"📊 <b>User Info:</b>",
        f"├ ID: <code>{user_id}</code>",
        f"├ Username: {username}",
        f"└ Tier: {tier_label}\n",
    ]

    # Subscription status
    if tier != Tier.FREE and sub.expires > 0:
        remaining = sub.expires - _time.time()
        if remaining > 0:
            days = int(remaining // 86400)
            hours = int((remaining % 86400) // 3600)
            mins = int((remaining % 3600) // 60)
            exp_dt = datetime.fromtimestamp(sub.expires)
            lines.append("💎 <b>Langganan Aktif:</b>")
            lines.append(f"├ Berlaku sampai: <b>{exp_dt:%d/%m/%Y %H:%M}</b>")
            if days > 0:
                lines.append(f"└ Sisa waktu: <b>{days}h {hours}j {mins}m</b>\n")
            else:
                lines.append(f"└ Sisa waktu: <b>{hours}j {mins}m</b>\n")
        else:
            lines.append("💎 Langganan: <b>Expired</b>\n")
    elif tier == Tier.FREE:
        lines.append("💎 Langganan: <b>Belum berlangganan</b>\n")

    # Daily usage
    if admin_user:
        lines.append("📈 <b>Pemakaian Hari Ini:</b>")
        lines.append("└ <b>Unlimited (Admin)</b>\n")
    else:
        img_lim = limits.images_per_day
        vid_lim = limits.videos_per_day
        img_used = status["images_used"]
        vid_used = status["videos_used"]
        img_txt = f"{img_used}/♾️" if img_lim >= UNLIMITED else f"{img_used}/{img_lim}"
        vid_txt = f"{vid_used}/♾️" if vid_lim >= UNLIMITED else f"{vid_used}/{vid_lim}"
        lines.append("📈 <b>Pemakaian Hari Ini:</b>")
        lines.append(f"├ Image: <b>{img_txt}</b>")
        lines.append(f"├ Video: <b>{vid_txt}</b>")
        lines.append(f"└ Reset: <b>00:00 WIB</b>\n")

        # Extra quota info
        extra_img = status.get("extra_images", 0)
        extra_vid = status.get("extra_videos", 0)
        if extra_img > 0 or extra_vid > 0:
            lines.append("📦 <b>Extra Kuota:</b>")
            lines.append(f"├ Image: <b>{extra_img}</b>")
            lines.append(f"└ Video: <b>{extra_vid}</b>\n")

    # Bot statistics
    lines.append("🤖 <b>Bot Stats:</b>")
    lines.append(f"├ Total User: <b>{stats['total_users']}</b>")
    lines.append(f"├ Subscriber Aktif: <b>{stats['active_subs']}</b>")
    lines.append(f"└ Aktif Hari Ini: <b>{stats['active_today']}</b>\n")

    lines.append("📌 <b>Shortcuts:</b>")
    lines.append("├ /start — Buka menu utama")
    lines.append("├ /help — Bantuan")
    lines.append("└ /cancel — Batalkan proses aktif")

    # Send extra messages first (referral bonus, trial)
    for extra_msg in extra_messages:
        await message.answer(extra_msg)

    await message.answer("\n".join(lines), reply_markup=main_menu_keyboard(await get_backend(state)))


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    text = (
        "ℹ️ <b>Bantuan</b>\n\n"
        "📌 <b>Commands:</b>\n"
        "├ /start — Menu utama + statistik\n"
        "├ /help — Halaman ini\n"
        "├ /cancel — Batalkan proses aktif\n"
        "└ /admin — Panel admin (khusus admin)\n\n"
        "🖼 <b>Image</b> — Generate gambar dari teks\n"
        "🎬 <b>Video</b> — Generate video dari teks\n"
        "💎 <b>Subscription</b> — Kelola & beli langganan\n"
        "📈 <b>My Limit</b> — Cek sisa kuota harian\n"
        "📦 <b>Topup Kuota</b> — Beli kuota tambahan\n"
        "🏆 <b>Leaderboard</b> — Top generator bulan ini\n"
        "🔗 <b>Referral</b> — Ajak teman, dapat bonus\n\n"
        "💡 <b>Tips:</b>\n"
        "• User baru dapat trial Premium 12 jam!\n"
        "• Ajak teman via referral → bonus +10 image\n"
        "• Kuota extra dari topup tidak expired"
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
        "🛠 <b>Admin Panel</b>\nPilih aksi admin:",
        reply_markup=admin_menu_keyboard(),
    )


@router.message(Command("sso"))
async def cmd_sso(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else 0
    if not is_admin(user_id):
        await message.answer("❌ Akses ditolak. Khusus admin.")
        return
    await message.answer(
        "🔐 <b>SSO Manager</b>",
        reply_markup=sso_menu_keyboard(),
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await clear_state(state)
    await message.answer("✅ Flow dibatalkan.")
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
            "🤖 <b>Pilih Model</b>\n\n"
            "Pilih AI model yang ingin digunakan:\n\n"
            "⚡ <b>Grok</b> — Image & Video generation (xAI)\n"
            "💎 <b>Gemini</b> — Image & Video generation (Google)\n\n"
            f"Aktif saat ini: <b>{current.title()}</b>"
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
    await callback.answer(f"✅ Model diubah ke {new_backend.title()}")


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
            "📈 <b>My Limit</b>\n"
            "Role: <b>Admin</b>\n"
            "Status: <b>Unlimited</b>"
        )
    else:
        img_limit = status['images_limit']
        vid_limit = status['videos_limit']
        img_txt = f"{status['images_used']}/♾️" if img_limit >= UNLIMITED else f"{status['images_used']}/{img_limit} (sisa {status['images_remaining']})"
        vid_txt = f"{status['videos_used']}/♾️" if vid_limit >= UNLIMITED else f"{status['videos_used']}/{vid_limit} (sisa {status['videos_remaining']})"

        text = (
            "📈 <b>My Limit</b>\n\n"
            f"• Tier: <b>{tier_label}</b>\n"
        )

        # Show subscription remaining time
        if tier != Tier.FREE and sub.expires > 0:
            remaining = sub.expires - _time.time()
            if remaining > 0:
                days = int(remaining // 86400)
                hours = int((remaining % 86400) // 3600)
                mins = int((remaining % 3600) // 60)
                if days > 0:
                    text += f"• Sisa langganan: <b>{days}h {hours}j {mins}m</b>\n"
                else:
                    text += f"• Sisa langganan: <b>{hours}j {mins}m</b>\n"

        text += (
            f"\n📊 <b>Pemakaian Hari Ini:</b>\n"
            f"• Image: <b>{img_txt}</b>\n"
            f"• Video: <b>{vid_txt}</b>\n"
            f"• Reset: <b>00:00 WIB</b>\n"
        )

        # Extra quota
        extra_img = status.get("extra_images", 0)
        extra_vid = status.get("extra_videos", 0)
        if extra_img > 0 or extra_vid > 0:
            text += (
                f"\n📦 <b>Extra Kuota:</b>\n"
                f"• Image: <b>{extra_img}</b>\n"
                f"• Video: <b>{extra_vid}</b>"
            )

        # Cooldown info
        from ..rate_limiter import get_cooldown_text
        text += f"\n\n⏱ Cooldown: <b>{get_cooldown_text(tier)}</b>"

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
    await callback.answer("Menu dibersihkan")


@router.callback_query(F.data == "noop")
async def noop_callback(callback: CallbackQuery) -> None:
    await callback.answer()


@router.message(StateFilter(None))
async def fallback_message(message: Message) -> None:
    await message.answer(
        "Perintah tidak dikenali. Gunakan /start untuk membuka menu atau /help untuk bantuan."
    )
