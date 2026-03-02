"""
SQLite database layer for the Telegram bot.

Tables:
  users          – user tracking (first_seen, last_seen, referral_code, trial_used)
  subscriptions  – tier, expiry, grant info per user
  daily_usage    – image/video usage counters per user per day
  payments       – QRIS payment records
  referrals      – referral tracking (referrer → referred)
  extra_quota    – purchased extra image/video quota (topup)
  reminders_sent – tracks expiry reminders already sent
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
        CREATE TABLE IF NOT EXISTS users (
            user_id        INTEGER PRIMARY KEY,
            first_name     TEXT    NOT NULL DEFAULT '',
            username       TEXT    NOT NULL DEFAULT '',
            first_seen     REAL    NOT NULL DEFAULT 0,
            last_seen      REAL    NOT NULL DEFAULT 0,
            referral_code  TEXT    NOT NULL DEFAULT '',
            trial_used     INTEGER NOT NULL DEFAULT 0,
            referred_by    INTEGER NOT NULL DEFAULT 0
        );

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

        CREATE TABLE IF NOT EXISTS referrals (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER NOT NULL,
            referred_id INTEGER NOT NULL UNIQUE,
            bonus_given INTEGER NOT NULL DEFAULT 0,
            created_at  REAL    NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS extra_quota (
            user_id  INTEGER PRIMARY KEY,
            images   INTEGER NOT NULL DEFAULT 0,
            videos   INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS reminders_sent (
            user_id    INTEGER NOT NULL,
            reminder   TEXT    NOT NULL,
            sent_at    REAL    NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, reminder)
        );

        CREATE INDEX IF NOT EXISTS idx_payments_user
            ON payments (user_id, status);
        CREATE INDEX IF NOT EXISTS idx_payments_txn
            ON payments (transaction_id);
        CREATE INDEX IF NOT EXISTS idx_referrals_referrer
            ON referrals (referrer_id);
        CREATE INDEX IF NOT EXISTS idx_daily_usage_date
            ON daily_usage (date_key);
    """)

    # --- Schema migration: add columns if missing ---
    try:
        await db.execute("SELECT referral_code FROM users LIMIT 1")
    except Exception:
        await db.execute("ALTER TABLE users ADD COLUMN referral_code TEXT NOT NULL DEFAULT ''")
    try:
        await db.execute("SELECT trial_used FROM users LIMIT 1")
    except Exception:
        await db.execute("ALTER TABLE users ADD COLUMN trial_used INTEGER NOT NULL DEFAULT 0")
    try:
        await db.execute("SELECT referred_by FROM users LIMIT 1")
    except Exception:
        await db.execute("ALTER TABLE users ADD COLUMN referred_by INTEGER NOT NULL DEFAULT 0")

    await db.commit()


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

async def upsert_user(user_id: int, first_name: str = "", username: str = "") -> bool:
    """Insert or update a user record (called on every /start).
    Returns True if this is a brand-new user (first seen now).
    """
    db = await get_db()
    now = time.time()
    ref_code = f"ref_{user_id}"

    # Check if user already exists
    async with db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)) as cur:
        existing = await cur.fetchone()

    await db.execute(
        """
        INSERT INTO users (user_id, first_name, username, first_seen, last_seen, referral_code)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            first_name = excluded.first_name,
            username   = excluded.username,
            last_seen  = excluded.last_seen
        """,
        (user_id, first_name, username, now, now, ref_code),
    )
    await db.commit()
    return existing is None


async def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    db = await get_db()
    async with db.execute(
        "SELECT user_id, first_name, username, first_seen, last_seen, "
        "referral_code, trial_used, referred_by FROM users WHERE user_id = ?",
        (user_id,),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


async def get_all_user_ids() -> List[int]:
    """Return all user IDs (for broadcast)."""
    db = await get_db()
    ids = []
    async with db.execute("SELECT user_id FROM users") as cur:
        async for row in cur:
            ids.append(row["user_id"])
    return ids


async def list_users(limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    db = await get_db()
    rows = []
    async with db.execute(
        "SELECT user_id, first_name, username, first_seen, last_seen "
        "FROM users ORDER BY last_seen DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ) as cur:
        async for row in cur:
            rows.append({k: row[k] for k in row.keys()})
    return rows


async def count_users() -> int:
    db = await get_db()
    async with db.execute("SELECT COUNT(*) as cnt FROM users") as cur:
        row = await cur.fetchone()
    return row["cnt"] if row else 0


async def delete_user(user_id: int) -> bool:
    """Delete a user and their related data."""
    db = await get_db()
    await db.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    await db.execute("DELETE FROM subscriptions WHERE user_id = ?", (user_id,))
    await db.execute("DELETE FROM daily_usage WHERE user_id = ?", (user_id,))
    await db.execute("DELETE FROM payments WHERE user_id = ?", (user_id,))
    await db.commit()
    return True


async def get_bot_stats() -> Dict[str, Any]:
    """Return aggregate statistics for the bot."""
    db = await get_db()
    now = time.time()

    async with db.execute("SELECT COUNT(*) as cnt FROM users") as cur:
        total_users = (await cur.fetchone())["cnt"]

    async with db.execute(
        "SELECT COUNT(*) as cnt FROM subscriptions WHERE (expires > ? OR expires = 0) AND tier != 'free'",
        (now,),
    ) as cur:
        active_subs = (await cur.fetchone())["cnt"]

    async with db.execute("SELECT COUNT(*) as cnt FROM payments WHERE status = 'paid'") as cur:
        total_paid = (await cur.fetchone())["cnt"]

    # Today's active users (from daily_usage)
    import datetime as _dt
    wib = _dt.timezone(_dt.timedelta(hours=7))
    today_key = _dt.datetime.now(wib).strftime("%Y-%m-%d")
    async with db.execute(
        "SELECT COUNT(DISTINCT user_id) as cnt FROM daily_usage WHERE date_key = ?",
        (today_key,),
    ) as cur:
        active_today = (await cur.fetchone())["cnt"]

    return {
        "total_users": total_users,
        "active_subs": active_subs,
        "total_paid": total_paid,
        "active_today": active_today,
    }


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
# Referrals
# ---------------------------------------------------------------------------

async def mark_trial_used(user_id: int) -> None:
    db = await get_db()
    await db.execute("UPDATE users SET trial_used = 1 WHERE user_id = ?", (user_id,))
    await db.commit()


async def set_referred_by(user_id: int, referrer_id: int) -> None:
    db = await get_db()
    await db.execute(
        "UPDATE users SET referred_by = ? WHERE user_id = ?",
        (referrer_id, user_id),
    )
    await db.commit()


async def create_referral(referrer_id: int, referred_id: int) -> bool:
    """Record a referral. Returns True if successfully created (not duplicate)."""
    db = await get_db()
    now = time.time()
    try:
        await db.execute(
            "INSERT INTO referrals (referrer_id, referred_id, created_at) VALUES (?, ?, ?)",
            (referrer_id, referred_id, now),
        )
        await db.commit()
        return True
    except Exception:
        return False


async def mark_referral_bonus(referred_id: int) -> None:
    db = await get_db()
    await db.execute(
        "UPDATE referrals SET bonus_given = 1 WHERE referred_id = ?",
        (referred_id,),
    )
    await db.commit()


async def count_referrals(referrer_id: int) -> int:
    db = await get_db()
    async with db.execute(
        "SELECT COUNT(*) as cnt FROM referrals WHERE referrer_id = ?",
        (referrer_id,),
    ) as cur:
        row = await cur.fetchone()
    return row["cnt"] if row else 0


async def get_referral_by_referred(referred_id: int) -> Optional[Dict[str, Any]]:
    db = await get_db()
    async with db.execute(
        "SELECT referrer_id, referred_id, bonus_given, created_at "
        "FROM referrals WHERE referred_id = ?",
        (referred_id,),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


# ---------------------------------------------------------------------------
# Extra Quota (Topup)
# ---------------------------------------------------------------------------

async def get_extra_quota(user_id: int) -> Dict[str, int]:
    db = await get_db()
    async with db.execute(
        "SELECT images, videos FROM extra_quota WHERE user_id = ?",
        (user_id,),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return {"images": 0, "videos": 0}
    return {"images": row["images"], "videos": row["videos"]}


async def add_extra_quota(user_id: int, images: int = 0, videos: int = 0) -> Dict[str, int]:
    db = await get_db()
    await db.execute(
        """
        INSERT INTO extra_quota (user_id, images, videos)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            images = extra_quota.images + excluded.images,
            videos = extra_quota.videos + excluded.videos
        """,
        (user_id, images, videos),
    )
    await db.commit()
    return await get_extra_quota(user_id)


async def deduct_extra_quota(user_id: int, images: int = 0, videos: int = 0) -> bool:
    """Deduct from extra quota. Returns True if sufficient quota available."""
    db = await get_db()
    quota = await get_extra_quota(user_id)
    if quota["images"] < images or quota["videos"] < videos:
        return False
    await db.execute(
        "UPDATE extra_quota SET images = images - ?, videos = videos - ? WHERE user_id = ?",
        (images, videos, user_id),
    )
    await db.commit()
    return True


# ---------------------------------------------------------------------------
# Leaderboard
# ---------------------------------------------------------------------------

async def get_leaderboard(limit: int = 10) -> List[Dict[str, Any]]:
    """Get top users by total generation count for the current month."""
    import datetime
    wib = datetime.timezone(datetime.timedelta(hours=7))
    month_prefix = datetime.datetime.now(wib).strftime("%Y-%m")
    db = await get_db()
    rows = []
    async with db.execute(
        """
        SELECT d.user_id,
               COALESCE(u.first_name, '') as first_name,
               COALESCE(u.username, '') as username,
               SUM(d.images) as total_images,
               SUM(d.videos) as total_videos,
               SUM(d.images) + SUM(d.videos) as total
        FROM daily_usage d
        LEFT JOIN users u ON d.user_id = u.user_id
        WHERE d.date_key LIKE ?
        GROUP BY d.user_id
        ORDER BY total DESC
        LIMIT ?
        """,
        (f"{month_prefix}%", limit),
    ) as cur:
        async for row in cur:
            rows.append({k: row[k] for k in row.keys()})
    return rows


# ---------------------------------------------------------------------------
# Reminders
# ---------------------------------------------------------------------------

async def get_expiring_subscriptions(within_seconds: float = 86400) -> List[Dict[str, Any]]:
    """Find subscriptions expiring within the given timeframe."""
    db = await get_db()
    now = time.time()
    cutoff = now + within_seconds
    rows = []
    async with db.execute(
        """
        SELECT s.user_id, s.tier, s.expires,
               COALESCE(u.first_name, '') as first_name
        FROM subscriptions s
        LEFT JOIN users u ON s.user_id = u.user_id
        WHERE s.expires > ? AND s.expires <= ? AND s.tier != 'free'
        """,
        (now, cutoff),
    ) as cur:
        async for row in cur:
            rows.append({k: row[k] for k in row.keys()})
    return rows


async def is_reminder_sent(user_id: int, reminder: str) -> bool:
    db = await get_db()
    async with db.execute(
        "SELECT 1 FROM reminders_sent WHERE user_id = ? AND reminder = ?",
        (user_id, reminder),
    ) as cur:
        return await cur.fetchone() is not None


async def mark_reminder_sent(user_id: int, reminder: str) -> None:
    db = await get_db()
    now = time.time()
    await db.execute(
        """
        INSERT OR REPLACE INTO reminders_sent (user_id, reminder, sent_at)
        VALUES (?, ?, ?)
        """,
        (user_id, reminder, now),
    )
    await db.commit()


async def cleanup_old_reminders() -> int:
    """Delete reminder records for expired subscriptions."""
    db = await get_db()
    now = time.time()
    cur = await db.execute(
        """
        DELETE FROM reminders_sent WHERE user_id NOT IN (
            SELECT user_id FROM subscriptions WHERE expires > ?
        )
        """,
        (now,),
    )
    await db.commit()
    return cur.rowcount


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
