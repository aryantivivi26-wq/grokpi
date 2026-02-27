"""
Topup quota handler — buy extra image/video credits via QRIS.

Packs:
  50 images  = Rp 3.000
  100 images = Rp 5.000
  20 videos  = Rp 5.000
  50 videos  = Rp 10.000
"""

import asyncio
import base64
import html
import logging
import time
import uuid
from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.types import BufferedInputFile, CallbackQuery

from .. import database as db
from ..config import settings
from ..keyboards import pay_back_keyboard
from ..payment_client import qris_client
from ..ui import safe_edit_text

logger = logging.getLogger(__name__)

router = Router()

# ---------------------------------------------------------------------------
# Topup packs
# ---------------------------------------------------------------------------

TOPUP_PACKS = {
    "img50":  {"images": 50,  "videos": 0,  "price": 3_000,  "label": "50 Image"},
    "img100": {"images": 100, "videos": 0,  "price": 5_000,  "label": "100 Image"},
    "vid20":  {"images": 0,   "videos": 20, "price": 5_000,  "label": "20 Video"},
    "vid50":  {"images": 0,   "videos": 50, "price": 10_000, "label": "50 Video"},
}


def _format_rp(amount: int) -> str:
    return f"Rp {amount:,}".replace(",", ".")


def _topup_menu_keyboard():
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    rows = []
    for pack_id, pack in TOPUP_PACKS.items():
        rows.append([InlineKeyboardButton(
            text=f"{'🖼' if pack['images'] else '🎬'} {pack['label']} — {_format_rp(pack['price'])}",
            callback_data=f"topup:buy:{pack_id}",
        )])
    rows.append([InlineKeyboardButton(text="📦 Cek Kuota Extra", callback_data="topup:balance")])
    rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _topup_confirm_keyboard(pack_id: str, price: int):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"✅ Bayar {_format_rp(price)}",
            callback_data=f"topup:confirm:{pack_id}",
        )],
        [InlineKeyboardButton(text="❌ Batal", callback_data="menu:topup")],
    ])


def _topup_waiting_keyboard(txn_id: str):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Cek Status", callback_data=f"topup:check:{txn_id}")],
        [InlineKeyboardButton(text="❌ Batalkan", callback_data=f"topup:cancel:{txn_id}")],
    ])


# ---------------------------------------------------------------------------
# Show topup menu
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "menu:topup")
async def show_topup_menu(callback: CallbackQuery) -> None:
    extra = await db.get_extra_quota(callback.from_user.id)
    text = (
        "📦 <b>Topup Kuota Extra</b>\n\n"
        "Beli kuota tambahan yang <b>tidak expired</b> dan bisa digunakan "
        "saat limit harian habis.\n\n"
        f"📦 <b>Saldo Extra Kamu:</b>\n"
        f"├ Image: <b>{extra['images']}</b>\n"
        f"└ Video: <b>{extra['videos']}</b>\n\n"
        "Pilih paket yang ingin dibeli:"
    )
    await safe_edit_text(callback.message, text, reply_markup=_topup_menu_keyboard())
    await callback.answer()


# ---------------------------------------------------------------------------
# Check extra balance
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "topup:balance")
async def topup_balance(callback: CallbackQuery) -> None:
    extra = await db.get_extra_quota(callback.from_user.id)
    await callback.answer(
        f"📦 Extra: {extra['images']} img, {extra['videos']} vid",
        show_alert=True,
    )


# ---------------------------------------------------------------------------
# Buy pack — confirm screen
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("topup:buy:"))
async def topup_buy(callback: CallbackQuery) -> None:
    pack_id = callback.data.replace("topup:buy:", "", 1)
    pack = TOPUP_PACKS.get(pack_id)
    if not pack:
        await callback.answer("Paket tidak ditemukan", show_alert=True)
        return

    text = (
        f"🧾 <b>Konfirmasi Topup</b>\n\n"
        f"• Paket: <b>{pack['label']}</b>\n"
        f"• Harga: <b>{_format_rp(pack['price'])}</b>\n\n"
        f"Kuota akan langsung ditambahkan ke saldo extra kamu."
    )
    await safe_edit_text(
        callback.message,
        text,
        reply_markup=_topup_confirm_keyboard(pack_id, pack["price"]),
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Confirm & create QRIS
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("topup:confirm:"))
async def topup_create_qris(callback: CallbackQuery, bot: Bot) -> None:
    pack_id = callback.data.replace("topup:confirm:", "", 1)
    pack = TOPUP_PACKS.get(pack_id)
    if not pack:
        await callback.answer("Paket tidak valid", show_alert=True)
        return

    user_id = callback.from_user.id
    amount = pack["price"]
    order_id = f"TOPUP-{user_id}-{uuid.uuid4().hex[:8].upper()}"

    # Check pending payment
    pending = await db.get_pending_payment(user_id)
    if pending:
        await callback.answer("Masih ada pembayaran pending. Selesaikan dulu.", show_alert=True)
        return

    await safe_edit_text(callback.message, "⏳ Membuat QRIS topup...")
    await callback.answer()

    try:
        result = await qris_client.create_transaction(
            amount=amount,
            order_id=order_id,
            customer_id=str(user_id),
        )
    except Exception as e:
        logger.error("[Topup] QRIS create failed: %s", e)
        await safe_edit_text(
            callback.message,
            f"❌ Gagal membuat QRIS:\n<code>{html.escape(str(e)[:200])}</code>",
            reply_markup=pay_back_keyboard(),
        )
        return

    txn_id = result["transaction_id"]
    amount_total = result.get("amount_total", amount)
    qris_image_b64 = result.get("qris_image_url", "")

    # Save as payment record (tier=topup_PACKID, duration=topup)
    await db.create_payment(
        user_id=user_id,
        transaction_id=txn_id,
        tier=f"topup_{pack_id}",
        duration="topup",
        amount=amount_total,
    )

    caption = (
        f"📱 <b>Scan QRIS untuk Topup</b>\n\n"
        f"• Order: <code>{order_id}</code>\n"
        f"• Paket: <b>{pack['label']}</b>\n"
        f"• Total: <b>{_format_rp(amount_total)}</b>\n\n"
        f"⏳ Bot akan otomatis cek pembayaran."
    )

    chat_id = callback.message.chat.id
    try:
        if qris_image_b64.startswith("data:"):
            b64_data = qris_image_b64.split(",", 1)[1]
        else:
            b64_data = qris_image_b64
        image_bytes = base64.b64decode(b64_data)
        photo = BufferedInputFile(image_bytes, filename="qris_topup.png")
        await bot.send_photo(
            chat_id=chat_id,
            photo=photo,
            caption=caption,
            reply_markup=_topup_waiting_keyboard(txn_id),
        )
    except Exception as e:
        logger.warning("[Topup] QR image failed: %s", e)
        await bot.send_message(
            chat_id=chat_id,
            text=caption,
            reply_markup=_topup_waiting_keyboard(txn_id),
        )

    try:
        await callback.message.delete()
    except Exception:
        pass

    # Start background polling
    asyncio.create_task(
        _poll_topup(bot, chat_id, user_id, txn_id, pack_id)
    )


# ---------------------------------------------------------------------------
# Manual check
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("topup:check:"))
async def topup_check(callback: CallbackQuery) -> None:
    txn_id = callback.data.replace("topup:check:", "", 1)
    try:
        result = await qris_client.check_status(txn_id)
        status = result.get("transaction", {}).get("status", "unknown")
    except Exception as e:
        await callback.answer(f"Error: {str(e)[:50]}", show_alert=True)
        return

    icons = {"paid": "✅ Sudah dibayar!", "pending": "⏳ Belum dibayar", "expired": "⏰ Expired"}
    await callback.answer(icons.get(status, f"Status: {status}"), show_alert=True)


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("topup:cancel:"))
async def topup_cancel(callback: CallbackQuery) -> None:
    txn_id = callback.data.replace("topup:cancel:", "", 1)
    await db.mark_payment_expired(txn_id)
    await callback.message.answer("❌ Topup dibatalkan.", reply_markup=_topup_menu_keyboard())
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Background poller
# ---------------------------------------------------------------------------

async def _poll_topup(
    bot: Bot,
    chat_id: int,
    user_id: int,
    transaction_id: str,
    pack_id: str,
) -> None:
    interval = settings.QRIS_POLL_INTERVAL
    timeout = settings.QRIS_POLL_TIMEOUT
    start = time.time()

    while time.time() - start < timeout:
        await asyncio.sleep(interval)

        payment = await db.get_payment(transaction_id)
        if payment and payment["status"] != "pending":
            if payment["status"] == "paid":
                logger.info("[Topup] Already processed: %s", transaction_id)
            return

        try:
            result = await qris_client.check_status(transaction_id)
            status = result.get("transaction", {}).get("status", "pending")
        except Exception as e:
            logger.warning("[Topup] Poll error %s: %s", transaction_id, e)
            continue

        if status == "paid":
            await _grant_topup(bot, chat_id, user_id, transaction_id, pack_id)
            return

        if status == "expired":
            await db.mark_payment_expired(transaction_id)
            try:
                await bot.send_message(chat_id, "⏰ QRIS topup expired. Buat transaksi baru.")
            except Exception:
                pass
            return

    await db.mark_payment_expired(transaction_id)
    try:
        await bot.send_message(chat_id, "⏰ Waktu pembayaran topup habis (15 menit).")
    except Exception:
        pass


async def _grant_topup(
    bot: Bot,
    chat_id: int,
    user_id: int,
    transaction_id: str,
    pack_id: str,
) -> None:
    marked = await db.mark_payment_paid(transaction_id)
    if not marked:
        return

    pack = TOPUP_PACKS.get(pack_id)
    if not pack:
        logger.error("[Topup] Unknown pack: %s", pack_id)
        return

    await db.add_extra_quota(user_id, images=pack["images"], videos=pack["videos"])

    extra = await db.get_extra_quota(user_id)
    text = (
        f"🎉 <b>Topup Berhasil!</b>\n\n"
        f"• Paket: <b>{pack['label']}</b>\n"
        f"• Ditambahkan: <b>+{pack['images']} img, +{pack['videos']} vid</b>\n\n"
        f"📦 <b>Saldo Extra Sekarang:</b>\n"
        f"├ Image: <b>{extra['images']}</b>\n"
        f"└ Video: <b>{extra['videos']}</b>\n\n"
        f"Kuota ini tidak expired dan bisa dipakai kapan saja! 🚀"
    )

    try:
        await bot.send_message(chat_id, text)
    except Exception as e:
        logger.error("[Topup] Notify failed for %s: %s", user_id, e)

    logger.info("[Topup] Granted %s to user %s (txn=%s)", pack_id, user_id, transaction_id)
