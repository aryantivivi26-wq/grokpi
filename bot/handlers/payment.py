"""
Payment handler — QRIS purchase flow for subscriptions.

Flow:
  pay:buy  → pick tier → pick duration → confirm → QRIS generated →
  bot polls check-status → on paid → auto-grant subscription
"""

import asyncio
import html
import logging
import time
import uuid
from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery

from .. import database as db
from ..config import settings
from ..keyboards import (
    pay_back_keyboard,
    pay_confirm_keyboard,
    pay_duration_keyboard,
    pay_tier_keyboard,
    pay_waiting_keyboard,
    subscription_admin_keyboard,
    subscription_menu_keyboard,
)
from ..payment_client import qris_client
from ..qr_utils import generate_qr_png
from ..security import is_admin
from ..states import PaymentFlow
from ..subscription_manager import (
    Duration,
    Tier,
    TIER_LABELS,
    DURATION_LABELS,
    subscription_manager,
)
from ..ui import clear_state, safe_edit_text

logger = logging.getLogger(__name__)

router = Router()

# ---------------------------------------------------------------------------
# Pricing table  (tier_duration → Rp)
# ---------------------------------------------------------------------------

PRICES = {
    "basic_daily": 5_000,
    "basic_weekly": 25_000,
    "basic_monthly": 75_000,
    "premium_daily": 8_000,
    "premium_weekly": 40_000,
    "premium_monthly": 120_000,
}


def _format_rp(amount: int) -> str:
    return f"Rp {amount:,}".replace(",", ".")


# ---------------------------------------------------------------------------
# Step 1: choose tier
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "pay:buy")
async def pay_choose_tier(callback: CallbackQuery, state: FSMContext) -> None:
    await clear_state(state)
    await safe_edit_text(
        callback.message,
        "<b>Beli Subscription</b>\n"
        "<i>Pilih paket untuk upgrade kuota harian</i>\n\n"
        "Pilih tier:",
        reply_markup=pay_tier_keyboard(),
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Step 2: choose duration (shows prices)
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("pay:tier:"))
async def pay_choose_duration(callback: CallbackQuery) -> None:
    tier = callback.data.replace("pay:tier:", "", 1)  # "basic" or "premium"
    tier_label = TIER_LABELS.get(Tier(tier), tier)
    text = f"<b>Beli {tier_label}</b>\n\nPilih durasi:"
    await safe_edit_text(
        callback.message,
        text,
        reply_markup=pay_duration_keyboard(tier, PRICES),
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Step 3: confirm
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("pay:dur:"))
async def pay_confirm(callback: CallbackQuery) -> None:
    parts = callback.data.replace("pay:dur:", "", 1).split(":")
    if len(parts) != 2:
        await callback.answer("Invalid data", show_alert=True)
        return
    tier, duration = parts
    price_key = f"{tier}_{duration}"
    amount = PRICES.get(price_key, 0)
    if amount <= 0:
        await callback.answer("Harga tidak tersedia", show_alert=True)
        return

    tier_label = TIER_LABELS.get(Tier(tier), tier)
    dur_label = DURATION_LABELS.get(Duration(duration), duration)
    text = (
        f"<b>Konfirmasi Pembayaran</b>\n\n"
        f"Tier: <b>{tier_label}</b>\n"
        f"Durasi: <b>{dur_label}</b>\n"
        f"Harga: <b>{_format_rp(amount)}</b>\n\n"
        f"Tekan tombol di bawah untuk lanjut ke pembayaran QRIS."
    )
    await safe_edit_text(
        callback.message,
        text,
        reply_markup=pay_confirm_keyboard(tier, duration, amount),
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Step 4: create QRIS & send QR image
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("pay:confirm:"))
async def pay_create_qris(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    parts = callback.data.replace("pay:confirm:", "", 1).split(":")
    if len(parts) != 2:
        await callback.answer("Invalid data", show_alert=True)
        return
    tier, duration = parts
    price_key = f"{tier}_{duration}"
    amount = PRICES.get(price_key, 0)
    if amount <= 0:
        await callback.answer("Harga tidak valid", show_alert=True)
        return

    user_id = callback.from_user.id if callback.from_user else 0

    # Check if user already has a pending payment
    pending = await db.get_pending_payment(user_id)
    if pending:
        await callback.answer(
            "Kamu masih punya pembayaran pending. Selesaikan atau batalkan dulu.",
            show_alert=True,
        )
        return

    # Create order_id
    order_id = f"HUBIFY-{user_id}-{uuid.uuid4().hex[:8].upper()}"

    await safe_edit_text(callback.message, "⏳ Membuat QRIS…")
    await callback.answer()

    try:
        result = await qris_client.create_transaction(
            amount=amount,
            order_id=order_id,
            customer_id=str(user_id),
        )
    except Exception as e:
        logger.error("[Payment] QRIS create failed: %s", e)
        await safe_edit_text(
            callback.message,
            f"Gagal membuat QRIS:\n<code>{html.escape(str(e)[:200])}</code>",
            reply_markup=pay_back_keyboard(),
        )
        return

    txn_id = result["transaction_id"]
    amount_total = result.get("amount_total", amount)
    expires_at = result.get("expires_at", "")
    qris_content = result.get("qris_content", "")

    # Save payment record
    await db.create_payment(
        user_id=user_id,
        transaction_id=txn_id,
        tier=tier,
        duration=duration,
        amount=amount_total,
    )

    tier_label = TIER_LABELS.get(Tier(tier), tier)
    dur_label = DURATION_LABELS.get(Duration(duration), duration)
    caption = (
        f"<b>Scan QRIS untuk Bayar</b>\n\n"
        f"Order: <code>{order_id}</code>\n"
        f"Tier: <b>{tier_label}</b> · {dur_label}\n"
        f"Total: <b>{_format_rp(amount_total)}</b>\n"
    )
    if expires_at:
        caption += f"Berlaku sampai: <b>{expires_at}</b>\n"
    caption += (
        "\nBuka e-wallet (GoPay, OVO, Dana, dll),\n"
        "scan kode QR di atas, lalu bayar.\n\n"
        "<i>Bot otomatis mengecek pembayaran.</i>"
    )

    # Send QR image
    chat_id = callback.message.chat.id if callback.message else user_id
    qr_message_id = None
    try:
        if not qris_content:
            raise ValueError("qris_content kosong dari API")
        image_bytes = generate_qr_png(qris_content)
        photo = BufferedInputFile(image_bytes, filename="qris.png")
        sent = await bot.send_photo(
            chat_id=chat_id,
            photo=photo,
            caption=caption,
            reply_markup=pay_waiting_keyboard(txn_id),
        )
        qr_message_id = sent.message_id
    except Exception as e:
        logger.warning("[Payment] Failed to send QR image: %s", e)
        # Fallback: send text-only
        sent = await bot.send_message(
            chat_id=chat_id,
            text=caption + f"\n\n(QR image gagal dikirim: {html.escape(str(e)[:100])})",
            reply_markup=pay_waiting_keyboard(txn_id),
        )
        qr_message_id = sent.message_id

    # Delete the "creating QRIS" message
    try:
        await callback.message.delete()
    except Exception:
        pass

    # Start background polling
    await state.set_state(PaymentFlow.waiting_confirm)
    await state.update_data(pay_txn_id=txn_id)
    asyncio.create_task(
        _poll_payment(
            bot=bot,
            chat_id=chat_id,
            user_id=user_id,
            transaction_id=txn_id,
            tier=tier,
            duration=duration,
            qr_message_id=qr_message_id,
        )
    )


# ---------------------------------------------------------------------------
# Manual status check
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("pay:check:"))
async def pay_manual_check(callback: CallbackQuery) -> None:
    txn_id = callback.data.replace("pay:check:", "", 1)
    try:
        result = await qris_client.check_status(txn_id)
        txn = result.get("transaction", {})
        status = txn.get("status", "unknown")
    except Exception as e:
        await callback.answer(f"Error: {str(e)[:50]}", show_alert=True)
        return

    if status == "paid":
        await callback.answer("✅ Pembayaran terdeteksi! Subscription segera aktif.", show_alert=True)
    elif status == "pending":
        await callback.answer("⏳ Belum ada pembayaran. Silakan scan QRIS.", show_alert=True)
    elif status == "expired":
        await callback.answer("⏰ QRIS sudah expired. Silakan buat ulang.", show_alert=True)
    else:
        await callback.answer(f"Status: {status}", show_alert=True)


# ---------------------------------------------------------------------------
# Cancel pending payment
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("pay:cancel:"))
async def pay_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    txn_id = callback.data.replace("pay:cancel:", "", 1)
    await db.mark_payment_expired(txn_id)
    await clear_state(state)

    user_id = callback.from_user.id if callback.from_user else 0
    kb = subscription_admin_keyboard() if is_admin(user_id) else subscription_menu_keyboard()
    await callback.message.answer(
        "Pembayaran dibatalkan.",
        reply_markup=kb,
    )
    await callback.answer()

    # Try to delete the QR message
    try:
        await callback.message.delete()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Payment history
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "pay:history")
async def pay_history(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id if callback.from_user else 0
    payments = await db.list_user_payments(user_id, limit=10)

    if not payments:
        await safe_edit_text(
            callback.message,
            "<b>Riwayat Pembayaran</b>\n\nBelum ada transaksi.",
            reply_markup=pay_back_keyboard(),
        )
        await callback.answer()
        return

    lines = ["<b>Riwayat Pembayaran</b>\n"]
    status_icons = {"paid": "✓", "pending": "⏳", "expired": "⏰"}
    for p in payments:
        icon = status_icons.get(p["status"], "❓")
        tier_label = TIER_LABELS.get(Tier(p["tier"]), p["tier"]) if p["tier"] in [t.value for t in Tier] else p["tier"]
        dt = datetime.fromtimestamp(p["created_at"]).strftime("%d/%m %H:%M") if p["created_at"] else "-"
        lines.append(
            f"{icon} {dt} — {tier_label} — {_format_rp(p['amount'])} — {p['status']}"
        )

    await safe_edit_text(
        callback.message,
        "\n".join(lines),
        reply_markup=pay_back_keyboard(),
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Background payment poller
# ---------------------------------------------------------------------------

async def _poll_payment(
    bot: Bot,
    chat_id: int,
    user_id: int,
    transaction_id: str,
    tier: str,
    duration: str,
    qr_message_id: int | None = None,
) -> None:
    """Poll QRIS check-status until paid, expired, or timeout."""
    interval = settings.QRIS_POLL_INTERVAL
    timeout = settings.QRIS_POLL_TIMEOUT
    start = time.time()

    while time.time() - start < timeout:
        await asyncio.sleep(interval)

        # Check if payment was already processed (e.g. via webhook)
        payment = await db.get_payment(transaction_id)
        if payment and payment["status"] != "pending":
            if payment["status"] == "paid":
                logger.info("[Payment] Already processed by webhook: %s", transaction_id)
            return

        try:
            result = await qris_client.check_status(transaction_id)
            txn = result.get("transaction", {})
            status = txn.get("status", "pending")
        except Exception as e:
            logger.warning("[Payment] Poll error for %s: %s", transaction_id, e)
            continue

        if status == "paid":
            await _delete_qr_message(bot, chat_id, qr_message_id)
            await _grant_from_payment(bot, chat_id, user_id, transaction_id, tier, duration)
            return

        if status == "expired":
            await db.mark_payment_expired(transaction_id)
            await _delete_qr_message(bot, chat_id, qr_message_id)
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text="⏰ QRIS expired. Buat transaksi baru.",
                    reply_markup=pay_back_keyboard(),
                )
            except Exception:
                pass
            return

    # Timeout — mark expired
    await db.mark_payment_expired(transaction_id)
    await _delete_qr_message(bot, chat_id, qr_message_id)
    try:
        await bot.send_message(
            chat_id=chat_id,
            text="⏰ Waktu pembayaran habis. Buat transaksi baru.",
            reply_markup=pay_back_keyboard(),
        )
    except Exception:
        pass


async def _delete_qr_message(bot: Bot, chat_id: int, message_id: int | None) -> None:
    """Delete the QR image message silently."""
    if not message_id:
        return
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass


async def _grant_from_payment(
    bot: Bot,
    chat_id: int,
    user_id: int,
    transaction_id: str,
    tier: str,
    duration: str,
) -> None:
    """Mark payment as paid and grant subscription."""
    # Idempotency: only process if still pending
    marked = await db.mark_payment_paid(transaction_id)
    if not marked:
        return  # already processed

    try:
        tier_enum = Tier(tier)
        dur_enum = Duration(duration)
    except ValueError:
        logger.error("[Payment] Invalid tier/dur: %s/%s", tier, duration)
        return

    sub = await subscription_manager.grant(
        user_id=user_id,
        tier=tier_enum,
        duration=dur_enum,
        granted_by=0,  # system/payment
    )

    exp_text = datetime.fromtimestamp(sub.expires).strftime("%Y-%m-%d %H:%M")
    tier_label = TIER_LABELS[tier_enum]
    dur_label = DURATION_LABELS[dur_enum]
    text = (
        f"<b>Pembayaran Berhasil!</b>\n\n"
        f"Tier: <b>{tier_label}</b>\n"
        f"Durasi: <b>{dur_label}</b>\n"
        f"Aktif sampai: <b>{exp_text}</b>\n\n"
        f"Subscription kamu sudah aktif."
    )

    try:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=pay_back_keyboard(),
        )
    except Exception as e:
        logger.error("[Payment] Failed to notify user %s: %s", user_id, e)

    logger.info(
        "[Payment] Granted %s %s to user %s (txn=%s)",
        tier, duration, user_id, transaction_id,
    )
