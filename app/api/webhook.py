"""
Webhook endpoint for QRIS Hubify payment callbacks.

When a QRIS payment is confirmed, Hubify sends a POST to this endpoint.
We verify the signature, find the matching payment, mark it paid,
and grant the subscription.

Mount this router in the FastAPI app.
"""

import hashlib
import hmac
import logging
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, Request, Response

logger = logging.getLogger(__name__)

router = APIRouter()

# Webhook secret — same env as bot
_WEBHOOK_SECRET = os.getenv("QRIS_WEBHOOK_SECRET", "")


def _verify_signature(body: bytes, signature: Optional[str], secret: str) -> bool:
    """Verify HMAC-SHA256 signature from X-Webhook-Signature header."""
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _verify_simple_secret(header_secret: Optional[str], secret: str) -> bool:
    """Verify X-Webhook-Secret header (simple comparison)."""
    if not secret or not header_secret:
        return False
    return hmac.compare_digest(header_secret, secret)


@router.post("/webhook/qris")
async def qris_webhook(
    request: Request,
    x_webhook_secret: Optional[str] = Header(None),
    x_webhook_signature: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """
    Receive payment webhook from QRIS Hubify.

    Expected body:
    {
        "amount": 50000,
        "order_id": "HUBIFY-12345-ABCD1234",
        "customer_id": "12345",
        "status": "completed",
        "payment_method": "qris",
        "completed_at": "2024-01-01T12:05:00.123+07:00"
    }
    """
    body = await request.body()

    # --- Verify authenticity ---
    secret = _WEBHOOK_SECRET
    verified = False

    if secret:
        # Try HMAC signature first
        if x_webhook_signature and _verify_signature(body, x_webhook_signature, secret):
            verified = True
        # Fallback: simple secret header
        elif x_webhook_secret and _verify_simple_secret(x_webhook_secret, secret):
            verified = True

        if not verified:
            logger.warning("[Webhook] Signature verification failed")
            return {"error": "invalid signature", "ok": False}
    else:
        logger.warning("[Webhook] No QRIS_WEBHOOK_SECRET set — accepting without verification")
        verified = True

    # --- Parse payload ---
    import json
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return {"error": "invalid json", "ok": False}

    status = payload.get("status", "")
    order_id = payload.get("order_id", "")
    customer_id = payload.get("customer_id", "")
    amount = payload.get("amount", 0)

    logger.info(
        "[Webhook] Received: status=%s order=%s customer=%s amount=%s",
        status, order_id, customer_id, amount,
    )

    if status != "completed":
        return {"ok": True, "action": "ignored", "reason": f"status={status}"}

    # --- Find and process payment ---
    # We need to import bot database module — but this runs in the FastAPI process,
    # not the bot process. Use a shared approach: write to a webhook queue file
    # that the bot checks, OR import bot.database directly if they share the same DB.
    #
    # Since the bot and gateway may run in the same process or use the same SQLite DB,
    # we import database directly.
    try:
        from bot import database as db

        # Find payment by customer_id (user_id)
        if customer_id:
            user_id = int(customer_id)
            pending = await db.get_pending_payment(user_id)
            if pending and pending["amount"] == amount:
                # Match found — grant subscription
                await _process_webhook_payment(pending)
                return {"ok": True, "action": "granted", "transaction_id": pending["transaction_id"]}
            elif pending:
                # Amount mismatch — still try to match
                logger.warning(
                    "[Webhook] Amount mismatch: expected=%s got=%s (txn=%s)",
                    pending["amount"], amount, pending["transaction_id"],
                )
                await _process_webhook_payment(pending)
                return {"ok": True, "action": "granted_amount_mismatch", "transaction_id": pending["transaction_id"]}

        return {"ok": True, "action": "no_match", "order_id": order_id}

    except Exception as e:
        logger.error("[Webhook] Processing error: %s", e, exc_info=True)
        return {"ok": False, "error": str(e)}


async def _process_webhook_payment(payment: Dict[str, Any]) -> None:
    """Mark payment paid and grant subscription or topup quota."""
    from bot import database as db
    from bot.subscription_manager import Duration, Tier, subscription_manager

    txn_id = payment["transaction_id"]
    marked = await db.mark_payment_paid(txn_id)
    if not marked:
        logger.info("[Webhook] Payment %s already processed", txn_id)
        return

    tier_str = payment["tier"]
    duration_str = payment["duration"]

    # --- Topup payments (tier starts with "topup_") ---
    if tier_str.startswith("topup_"):
        pack_id = tier_str.replace("topup_", "", 1)
        # Import topup packs definition
        try:
            from bot.handlers.topup import TOPUP_PACKS
            pack = TOPUP_PACKS.get(pack_id)
            if pack:
                await db.add_extra_quota(
                    payment["user_id"],
                    images=pack["images"],
                    videos=pack["videos"],
                )
                logger.info(
                    "[Webhook] Topup granted %s to user %s (txn=%s)",
                    pack_id, payment["user_id"], txn_id,
                )
            else:
                logger.error("[Webhook] Unknown topup pack: %s", pack_id)
        except Exception as e:
            logger.error("[Webhook] Topup processing error: %s", e)
        return

    # --- Subscription payments ---
    try:
        tier_enum = Tier(tier_str)
        dur_enum = Duration(duration_str)
    except ValueError:
        logger.error("[Webhook] Invalid tier/dur in payment: %s", payment)
        return

    await subscription_manager.grant(
        user_id=payment["user_id"],
        tier=tier_enum,
        duration=dur_enum,
        granted_by=0,
    )

    logger.info(
        "[Webhook] Granted %s %s to user %s (txn=%s)",
        payment["tier"], payment["duration"], payment["user_id"], txn_id,
    )
