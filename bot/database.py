"""
SQLite database layer for the Telegram bot.

Tables:
  subscriptions – tier, expiry, grant info per user
  daily_usage   – image/video usage counters per user per day
  payments      – QRIS payment records
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiosqlite

from .config import settings

logger = logging.getLogger(__name__)

DB_PATH: Path = Path(settings.LIMITS_STATE_FILE).parent / "bot.db"

_db: Optional[aiosqlite.Connection] = None
_lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------

async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _db = await aiosqlite.connect(str(DB_PATH))
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA journal_mode=WAL")
        await _db.execute("PRAGMA foreign_keys=ON")
        await _init_tables(_db)
    return _db


async def close_db() -> None:
    global _db
    if _db is not None:
        await _db.close()
        _db = None


async def _init_tables(db: aiosqlite.Connection) -> None:
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            user_id     INTEGER PRIMARY KEY,
            tier        TEXT    NOT NULL DEFAULT 'free',
            expires     REAL    NOT NULL DEFAULT 0,
            granted_by  INTEGER NOT NULL DEFAULT 0,
            granted_at  REAL    NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS daily_usage (
            user_id     INTEGER NOT NULL,
            date_key    TEXT    NOT NULL,
            images      INTEGER NOT NULL DEFAULT 0,
            videos      INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, date_key)
        );

        CREATE TABLE IF NOT EXISTS payments (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL,
            transaction_id  TEXT    NOT NULL UNIQUE,
            tier            TEXT    NOT NULL,
            duration        TEXT    NOT NULL,
            amount          INTEGER NOT NULL,
            status          TEXT    NOT NULL DEFAULT 'pending',
            created_at      REAL    NOT NULL DEFAULT 0,
            paid_at         REAL    NOT NULL DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_payments_user
            ON payments (user_id, status);
        CREATE INDEX IF NOT EXISTS idx_payments_txn
            ON payments (transaction_id);
    """)
    await db.commit()


# ---------------------------------------------------------------------------
# Subscriptions
# ---------------------------------------------------------------------------

async def get_subscription(user_id: int) -> Optional[Dict[str, Any]]:
    db = await get_db()
    async with db.execute(
        "SELECT tier, expires, granted_by, granted_at FROM subscriptions WHERE user_id = ?",
        (user_id,),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return None
    return {
        "tier": row["tier"],
        "expires": row["expires"],
        "granted_by": row["granted_by"],
        "granted_at": row["granted_at"],
    }


async def upsert_subscription(
    user_id: int,
    tier: str,
    expires: float,
    granted_by: int = 0,
    granted_at: float = 0,
) -> None:
    db = await get_db()
    await db.execute(
        """
        INSERT INTO subscriptions (user_id, tier, expires, granted_by, granted_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            tier = excluded.tier,
            expires = excluded.expires,
            granted_by = excluded.granted_by,
            granted_at = excluded.granted_at
        """,
        (user_id, tier, expires, granted_by, granted_at),
    )
    await db.commit()


async def delete_subscription(user_id: int) -> bool:
    db = await get_db()
    cur = await db.execute("DELETE FROM subscriptions WHERE user_id = ?", (user_id,))
    await db.commit()
    return cur.rowcount > 0


async def list_active_subscriptions() -> List[Dict[str, Any]]:
    db = await get_db()
    now = time.time()
    rows = []
    async with db.execute(
        "SELECT user_id, tier, expires, granted_by, granted_at FROM subscriptions WHERE expires > ? OR expires = 0",
        (now,),
    ) as cur:
        async for row in cur:
            rows.append({
                "user_id": row["user_id"],
                "tier": row["tier"],
                "expires": row["expires"],
                "granted_by": row["granted_by"],
                "granted_at": row["granted_at"],
            })
    return rows


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------

async def create_payment(
    user_id: int,
    transaction_id: str,
    tier: str,
    duration: str,
    amount: int,
) -> Dict[str, Any]:
    db = await get_db()
    now = time.time()
    await db.execute(
        """
        INSERT INTO payments (user_id, transaction_id, tier, duration, amount, status, created_at)
        VALUES (?, ?, ?, ?, ?, 'pending', ?)
        """,
        (user_id, transaction_id, tier, duration, amount, now),
    )
    await db.commit()
    return {
        "user_id": user_id,
        "transaction_id": transaction_id,
        "tier": tier,
        "duration": duration,
        "amount": amount,
        "status": "pending",
        "created_at": now,
    }


async def get_payment(transaction_id: str) -> Optional[Dict[str, Any]]:
    db = await get_db()
    async with db.execute(
        "SELECT id, user_id, transaction_id, tier, duration, amount, status, created_at, paid_at "
        "FROM payments WHERE transaction_id = ?",
        (transaction_id,),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


async def get_pending_payment(user_id: int) -> Optional[Dict[str, Any]]:
    """Get the latest pending payment for a user."""
    db = await get_db()
    async with db.execute(
        "SELECT id, user_id, transaction_id, tier, duration, amount, status, created_at, paid_at "
        "FROM payments WHERE user_id = ? AND status = 'pending' ORDER BY created_at DESC LIMIT 1",
        (user_id,),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


async def mark_payment_paid(transaction_id: str) -> bool:
    db = await get_db()
    now = time.time()
    cur = await db.execute(
        "UPDATE payments SET status = 'paid', paid_at = ? WHERE transaction_id = ? AND status = 'pending'",
        (now, transaction_id),
    )
    await db.commit()
    return cur.rowcount > 0


async def mark_payment_expired(transaction_id: str) -> bool:
    db = await get_db()
    cur = await db.execute(
        "UPDATE payments SET status = 'expired' WHERE transaction_id = ? AND status = 'pending'",
        (transaction_id,),
    )
    await db.commit()
    return cur.rowcount > 0


async def list_user_payments(user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    db = await get_db()
    rows = []
    async with db.execute(
        "SELECT id, user_id, transaction_id, tier, duration, amount, status, created_at, paid_at "
        "FROM payments WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
        (user_id, limit),
    ) as cur:
        async for row in cur:
            rows.append({k: row[k] for k in row.keys()})
    return rows


# ---------------------------------------------------------------------------
# Daily usage
# ---------------------------------------------------------------------------

def _today_key() -> str:
    """Return today's date key in WIB (UTC+7)."""
    import datetime
    wib = datetime.timezone(datetime.timedelta(hours=7))
    return datetime.datetime.now(wib).strftime("%Y-%m-%d")


async def get_usage(user_id: int) -> Dict[str, int]:
    db = await get_db()
    date_key = _today_key()
    async with db.execute(
        "SELECT images, videos FROM daily_usage WHERE user_id = ? AND date_key = ?",
        (user_id, date_key),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return {"images": 0, "videos": 0}
    return {"images": row["images"], "videos": row["videos"]}


async def add_usage(user_id: int, images: int = 0, videos: int = 0) -> Dict[str, int]:
    db = await get_db()
    date_key = _today_key()
    await db.execute(
        """
        INSERT INTO daily_usage (user_id, date_key, images, videos)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id, date_key) DO UPDATE SET
            images = daily_usage.images + excluded.images,
            videos = daily_usage.videos + excluded.videos
        """,
        (user_id, date_key, images, videos),
    )
    await db.commit()
    return await get_usage(user_id)


async def reset_all_daily_usage() -> int:
    """Delete all daily_usage rows. Returns count deleted."""
    db = await get_db()
    cur = await db.execute("DELETE FROM daily_usage")
    await db.commit()
    return cur.rowcount


async def cleanup_old_usage(days_to_keep: int = 2) -> int:
    """Delete usage records older than N days."""
    import datetime
    wib = datetime.timezone(datetime.timedelta(hours=7))
    cutoff = (datetime.datetime.now(wib) - datetime.timedelta(days=days_to_keep)).strftime("%Y-%m-%d")
    db = await get_db()
    cur = await db.execute("DELETE FROM daily_usage WHERE date_key < ?", (cutoff,))
    await db.commit()
    return cur.rowcount


# ---------------------------------------------------------------------------
# Migration helper: import from old JSON files
# ---------------------------------------------------------------------------

async def migrate_from_json(
    limits_file: Path,
    subs_file: Path,
) -> Dict[str, int]:
    """One-time migration from old JSON files to SQLite."""
    import json
    stats = {"subscriptions": 0, "usage": 0}

    # Migrate subscriptions
    if subs_file.exists():
        try:
            data = json.loads(subs_file.read_text(encoding="utf-8"))
            for uid, rec in data.items():
                await upsert_subscription(
                    user_id=int(uid),
                    tier=rec.get("tier", "free"),
                    expires=float(rec.get("expires", 0)),
                    granted_by=int(rec.get("granted_by", 0)),
                    granted_at=float(rec.get("granted_at", 0)),
                )
                stats["subscriptions"] += 1
            # Rename old file
            subs_file.rename(subs_file.with_suffix(".json.bak"))
            logger.info(f"Migrated {stats['subscriptions']} subscriptions from JSON")
        except Exception as e:
            logger.warning(f"Failed to migrate subscriptions JSON: {e}")

    # Migrate usage
    if limits_file.exists():
        try:
            data = json.loads(limits_file.read_text(encoding="utf-8"))
            users = data.get("users", {})
            date_key = _today_key()
            db = await get_db()
            for uid, usage in users.items():
                if not isinstance(usage, dict):
                    continue
                imgs = int((usage).get("images", 0) or 0)
                vids = int((usage).get("videos", 0) or 0)
                if imgs > 0 or vids > 0:
                    await db.execute(
                        """
                        INSERT INTO daily_usage (user_id, date_key, images, videos)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(user_id, date_key) DO UPDATE SET
                            images = excluded.images, videos = excluded.videos
                        """,
                        (int(uid), date_key, imgs, vids),
                    )
                    stats["usage"] += 1
            await db.commit()
            limits_file.rename(limits_file.with_suffix(".json.bak"))
            logger.info(f"Migrated {stats['usage']} usage records from JSON")
        except Exception as e:
            logger.warning(f"Failed to migrate limits JSON: {e}")

    return stats
