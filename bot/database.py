"""
MongoDB database layer for the Telegram bot.

Collections:
  users          – user tracking (first_seen, last_seen, referral_code, trial_used)
  subscriptions  – tier, expiry, grant info per user
  daily_usage    – image/video usage counters per user per day
  payments       – QRIS payment records
  referrals      – referral tracking (referrer → referred)
  extra_quota    – purchased extra image/video quota (topup)
  reminders_sent – tracks expiry reminders already sent
"""

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from .config import settings

logger = logging.getLogger(__name__)

# MongoDB connection
_client: Optional[AsyncIOMotorClient] = None
_db: Optional[AsyncIOMotorDatabase] = None

# Keep this for backward compat (referenced in main.py log message)
DB_PATH: Path = Path(settings.LIMITS_STATE_FILE).parent / "bot.db"


# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------

async def get_db() -> AsyncIOMotorDatabase:
    global _client, _db
    if _db is None:
        mongo_uri = settings.MONGODB_URI
        db_name = settings.MONGODB_DB_NAME
        _client = AsyncIOMotorClient(mongo_uri)
        _db = _client[db_name]
        await _ensure_indexes(_db)
        logger.info(
            "[DB] Connected to MongoDB: %s / %s",
            mongo_uri.split("@")[-1] if "@" in mongo_uri else mongo_uri,
            db_name,
        )
    return _db


async def close_db() -> None:
    global _client, _db
    if _client is not None:
        _client.close()
        _client = None
        _db = None


async def _ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    """Create indexes for all collections."""
    await db.users.create_index("user_id", unique=True)
    await db.subscriptions.create_index("user_id", unique=True)
    await db.daily_usage.create_index([("user_id", 1), ("date_key", 1)], unique=True)
    await db.daily_usage.create_index("date_key")
    await db.payments.create_index([("user_id", 1), ("status", 1)])
    await db.payments.create_index("transaction_id", unique=True)
    await db.referrals.create_index("referrer_id")
    await db.referrals.create_index("referred_id", unique=True)
    await db.extra_quota.create_index("user_id", unique=True)
    await db.reminders_sent.create_index(
        [("user_id", 1), ("reminder", 1)], unique=True,
    )


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

    result = await db.users.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "first_name": first_name,
                "username": username,
                "last_seen": now,
            },
            "$setOnInsert": {
                "user_id": user_id,
                "first_seen": now,
                "referral_code": ref_code,
                "trial_used": 0,
                "referred_by": 0,
            },
        },
        upsert=True,
    )
    return result.upserted_id is not None


async def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    db = await get_db()
    doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    return dict(doc) if doc else None


async def get_all_user_ids() -> List[int]:
    """Return all user IDs (for broadcast)."""
    db = await get_db()
    ids = []
    async for doc in db.users.find({}, {"user_id": 1, "_id": 0}):
        ids.append(doc["user_id"])
    return ids


async def list_users(limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    db = await get_db()
    rows = []
    cursor = (
        db.users.find(
            {},
            {"_id": 0, "user_id": 1, "first_name": 1, "username": 1,
             "first_seen": 1, "last_seen": 1},
        )
        .sort("last_seen", -1)
        .skip(offset)
        .limit(limit)
    )
    async for doc in cursor:
        rows.append(dict(doc))
    return rows


async def count_users() -> int:
    db = await get_db()
    return await db.users.count_documents({})


async def delete_user(user_id: int) -> bool:
    """Delete a user and their related data."""
    db = await get_db()
    await db.users.delete_one({"user_id": user_id})
    await db.subscriptions.delete_one({"user_id": user_id})
    await db.daily_usage.delete_many({"user_id": user_id})
    await db.payments.delete_many({"user_id": user_id})
    return True


async def get_bot_stats() -> Dict[str, Any]:
    """Return aggregate statistics for the bot."""
    db = await get_db()
    now = time.time()

    total_users = await db.users.count_documents({})

    active_subs = await db.subscriptions.count_documents({
        "$and": [
            {"$or": [{"expires": {"$gt": now}}, {"expires": 0}]},
            {"tier": {"$ne": "free"}},
        ]
    })

    total_paid = await db.payments.count_documents({"status": "paid"})

    import datetime as _dt
    wib = _dt.timezone(_dt.timedelta(hours=7))
    today_key = _dt.datetime.now(wib).strftime("%Y-%m-%d")
    pipeline = [
        {"$match": {"date_key": today_key}},
        {"$group": {"_id": None, "count": {"$addToSet": "$user_id"}}},
        {"$project": {"count": {"$size": "$count"}}},
    ]
    result = await db.daily_usage.aggregate(pipeline).to_list(1)
    active_today = result[0]["count"] if result else 0

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
    doc = await db.subscriptions.find_one(
        {"user_id": user_id},
        {"_id": 0, "tier": 1, "expires": 1, "granted_by": 1, "granted_at": 1},
    )
    if doc is None:
        return None
    return {
        "tier": doc.get("tier", "free"),
        "expires": doc.get("expires", 0),
        "granted_by": doc.get("granted_by", 0),
        "granted_at": doc.get("granted_at", 0),
    }


async def upsert_subscription(
    user_id: int,
    tier: str,
    expires: float,
    granted_by: int = 0,
    granted_at: float = 0,
) -> None:
    db = await get_db()
    await db.subscriptions.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "user_id": user_id,
                "tier": tier,
                "expires": expires,
                "granted_by": granted_by,
                "granted_at": granted_at,
            },
        },
        upsert=True,
    )


async def delete_subscription(user_id: int) -> bool:
    db = await get_db()
    result = await db.subscriptions.delete_one({"user_id": user_id})
    return result.deleted_count > 0


async def list_active_subscriptions() -> List[Dict[str, Any]]:
    db = await get_db()
    now = time.time()
    rows = []
    cursor = db.subscriptions.find(
        {"$or": [{"expires": {"$gt": now}}, {"expires": 0}]},
        {"_id": 0},
    )
    async for doc in cursor:
        rows.append({
            "user_id": doc["user_id"],
            "tier": doc.get("tier", "free"),
            "expires": doc.get("expires", 0),
            "granted_by": doc.get("granted_by", 0),
            "granted_at": doc.get("granted_at", 0),
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
    doc = {
        "user_id": user_id,
        "transaction_id": transaction_id,
        "tier": tier,
        "duration": duration,
        "amount": amount,
        "status": "pending",
        "created_at": now,
        "paid_at": 0,
    }
    await db.payments.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def get_payment(transaction_id: str) -> Optional[Dict[str, Any]]:
    db = await get_db()
    doc = await db.payments.find_one({"transaction_id": transaction_id}, {"_id": 0})
    return dict(doc) if doc else None


async def get_pending_payment(user_id: int) -> Optional[Dict[str, Any]]:
    """Get the latest pending payment for a user."""
    db = await get_db()
    doc = await db.payments.find_one(
        {"user_id": user_id, "status": "pending"},
        {"_id": 0},
        sort=[("created_at", -1)],
    )
    return dict(doc) if doc else None


async def mark_payment_paid(transaction_id: str) -> bool:
    db = await get_db()
    now = time.time()
    result = await db.payments.update_one(
        {"transaction_id": transaction_id, "status": "pending"},
        {"$set": {"status": "paid", "paid_at": now}},
    )
    return result.modified_count > 0


async def mark_payment_expired(transaction_id: str) -> bool:
    db = await get_db()
    result = await db.payments.update_one(
        {"transaction_id": transaction_id, "status": "pending"},
        {"$set": {"status": "expired"}},
    )
    return result.modified_count > 0


async def list_user_payments(user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    db = await get_db()
    rows = []
    cursor = (
        db.payments.find({"user_id": user_id}, {"_id": 0})
        .sort("created_at", -1)
        .limit(limit)
    )
    async for doc in cursor:
        rows.append(dict(doc))
    return rows


# ---------------------------------------------------------------------------
# Referrals
# ---------------------------------------------------------------------------

async def mark_trial_used(user_id: int) -> None:
    db = await get_db()
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"trial_used": 1}},
    )


async def set_referred_by(user_id: int, referrer_id: int) -> None:
    db = await get_db()
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"referred_by": referrer_id}},
    )


async def create_referral(referrer_id: int, referred_id: int) -> bool:
    """Record a referral. Returns True if successfully created (not duplicate)."""
    db = await get_db()
    now = time.time()
    try:
        await db.referrals.insert_one({
            "referrer_id": referrer_id,
            "referred_id": referred_id,
            "bonus_given": 0,
            "created_at": now,
        })
        return True
    except Exception:
        return False


async def mark_referral_bonus(referred_id: int) -> None:
    db = await get_db()
    await db.referrals.update_one(
        {"referred_id": referred_id},
        {"$set": {"bonus_given": 1}},
    )


async def count_referrals(referrer_id: int) -> int:
    db = await get_db()
    return await db.referrals.count_documents({"referrer_id": referrer_id})


async def get_referral_by_referred(referred_id: int) -> Optional[Dict[str, Any]]:
    db = await get_db()
    doc = await db.referrals.find_one(
        {"referred_id": referred_id},
        {"_id": 0, "referrer_id": 1, "referred_id": 1, "bonus_given": 1, "created_at": 1},
    )
    return dict(doc) if doc else None


# ---------------------------------------------------------------------------
# Extra Quota (Topup)
# ---------------------------------------------------------------------------

async def get_extra_quota(user_id: int) -> Dict[str, int]:
    db = await get_db()
    doc = await db.extra_quota.find_one({"user_id": user_id}, {"_id": 0})
    if doc is None:
        return {"images": 0, "videos": 0}
    return {"images": doc.get("images", 0), "videos": doc.get("videos", 0)}


async def add_extra_quota(user_id: int, images: int = 0, videos: int = 0) -> Dict[str, int]:
    db = await get_db()
    await db.extra_quota.update_one(
        {"user_id": user_id},
        {
            "$inc": {"images": images, "videos": videos},
            "$setOnInsert": {"user_id": user_id},
        },
        upsert=True,
    )
    return await get_extra_quota(user_id)


async def deduct_extra_quota(user_id: int, images: int = 0, videos: int = 0) -> bool:
    """Deduct from extra quota. Returns True if sufficient quota available."""
    db = await get_db()
    quota = await get_extra_quota(user_id)
    if quota["images"] < images or quota["videos"] < videos:
        return False
    await db.extra_quota.update_one(
        {"user_id": user_id},
        {"$inc": {"images": -images, "videos": -videos}},
    )
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
    pipeline = [
        {"$match": {"date_key": {"$regex": f"^{month_prefix}"}}},
        {
            "$group": {
                "_id": "$user_id",
                "total_images": {"$sum": "$images"},
                "total_videos": {"$sum": "$videos"},
            }
        },
        {"$addFields": {"total": {"$add": ["$total_images", "$total_videos"]}}},
        {"$sort": {"total": -1}},
        {"$limit": limit},
        {
            "$lookup": {
                "from": "users",
                "localField": "_id",
                "foreignField": "user_id",
                "as": "user_info",
            }
        },
        {
            "$project": {
                "_id": 0,
                "user_id": "$_id",
                "total_images": 1,
                "total_videos": 1,
                "total": 1,
                "first_name": {
                    "$ifNull": [{"$arrayElemAt": ["$user_info.first_name", 0]}, ""]
                },
                "username": {
                    "$ifNull": [{"$arrayElemAt": ["$user_info.username", 0]}, ""]
                },
            }
        },
    ]
    return await db.daily_usage.aggregate(pipeline).to_list(limit)


# ---------------------------------------------------------------------------
# Reminders
# ---------------------------------------------------------------------------

async def get_expiring_subscriptions(within_seconds: float = 86400) -> List[Dict[str, Any]]:
    """Find subscriptions expiring within the given timeframe."""
    db = await get_db()
    now = time.time()
    cutoff = now + within_seconds

    pipeline = [
        {
            "$match": {
                "expires": {"$gt": now, "$lte": cutoff},
                "tier": {"$ne": "free"},
            }
        },
        {
            "$lookup": {
                "from": "users",
                "localField": "user_id",
                "foreignField": "user_id",
                "as": "user_info",
            }
        },
        {
            "$project": {
                "_id": 0,
                "user_id": 1,
                "tier": 1,
                "expires": 1,
                "first_name": {
                    "$ifNull": [{"$arrayElemAt": ["$user_info.first_name", 0]}, ""]
                },
            }
        },
    ]
    return await db.subscriptions.aggregate(pipeline).to_list(100)


async def is_reminder_sent(user_id: int, reminder: str) -> bool:
    db = await get_db()
    doc = await db.reminders_sent.find_one(
        {"user_id": user_id, "reminder": reminder}
    )
    return doc is not None


async def mark_reminder_sent(user_id: int, reminder: str) -> None:
    db = await get_db()
    now = time.time()
    await db.reminders_sent.update_one(
        {"user_id": user_id, "reminder": reminder},
        {"$set": {"user_id": user_id, "reminder": reminder, "sent_at": now}},
        upsert=True,
    )


async def cleanup_old_reminders() -> int:
    """Delete reminder records for expired subscriptions."""
    db = await get_db()
    now = time.time()

    active_ids = []
    async for doc in db.subscriptions.find(
        {"expires": {"$gt": now}}, {"user_id": 1, "_id": 0}
    ):
        active_ids.append(doc["user_id"])

    if active_ids:
        result = await db.reminders_sent.delete_many(
            {"user_id": {"$nin": active_ids}}
        )
    else:
        result = await db.reminders_sent.delete_many({})

    return result.deleted_count


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
    doc = await db.daily_usage.find_one(
        {"user_id": user_id, "date_key": date_key},
        {"_id": 0, "images": 1, "videos": 1},
    )
    if doc is None:
        return {"images": 0, "videos": 0}
    return {"images": doc.get("images", 0), "videos": doc.get("videos", 0)}


async def add_usage(user_id: int, images: int = 0, videos: int = 0) -> Dict[str, int]:
    db = await get_db()
    date_key = _today_key()
    await db.daily_usage.update_one(
        {"user_id": user_id, "date_key": date_key},
        {
            "$inc": {"images": images, "videos": videos},
            "$setOnInsert": {"user_id": user_id, "date_key": date_key},
        },
        upsert=True,
    )
    return await get_usage(user_id)


async def reset_all_daily_usage() -> int:
    """Delete all daily_usage documents. Returns count deleted."""
    db = await get_db()
    result = await db.daily_usage.delete_many({})
    return result.deleted_count


async def cleanup_old_usage(days_to_keep: int = 2) -> int:
    """Delete usage records older than N days."""
    import datetime
    wib = datetime.timezone(datetime.timedelta(hours=7))
    cutoff = (
        datetime.datetime.now(wib) - datetime.timedelta(days=days_to_keep)
    ).strftime("%Y-%m-%d")
    db = await get_db()
    result = await db.daily_usage.delete_many({"date_key": {"$lt": cutoff}})
    return result.deleted_count


# ---------------------------------------------------------------------------
# Migration helpers
# ---------------------------------------------------------------------------

async def migrate_from_sqlite(sqlite_path: Path) -> Dict[str, int]:
    """One-time migration from old SQLite database to MongoDB."""
    import aiosqlite

    if not sqlite_path.exists():
        return {
            "users": 0, "subscriptions": 0, "payments": 0,
            "referrals": 0, "daily_usage": 0,
        }

    stats = {
        "users": 0, "subscriptions": 0, "payments": 0,
        "referrals": 0, "daily_usage": 0,
    }
    mongo = await get_db()

    try:
        async with aiosqlite.connect(str(sqlite_path)) as sdb:
            sdb.row_factory = aiosqlite.Row

            # Migrate users
            try:
                async with sdb.execute("SELECT * FROM users") as cur:
                    async for row in cur:
                        doc = {k: row[k] for k in row.keys()}
                        try:
                            await mongo.users.update_one(
                                {"user_id": doc["user_id"]},
                                {"$setOnInsert": doc},
                                upsert=True,
                            )
                            stats["users"] += 1
                        except Exception:
                            pass
            except Exception as e:
                logger.warning("Failed to migrate users: %s", e)

            # Migrate subscriptions
            try:
                async with sdb.execute("SELECT * FROM subscriptions") as cur:
                    async for row in cur:
                        doc = {k: row[k] for k in row.keys()}
                        try:
                            await mongo.subscriptions.update_one(
                                {"user_id": doc["user_id"]},
                                {"$setOnInsert": doc},
                                upsert=True,
                            )
                            stats["subscriptions"] += 1
                        except Exception:
                            pass
            except Exception as e:
                logger.warning("Failed to migrate subscriptions: %s", e)

            # Migrate payments
            try:
                async with sdb.execute("SELECT * FROM payments") as cur:
                    async for row in cur:
                        doc = {k: row[k] for k in row.keys()}
                        doc.pop("id", None)
                        try:
                            await mongo.payments.update_one(
                                {"transaction_id": doc["transaction_id"]},
                                {"$setOnInsert": doc},
                                upsert=True,
                            )
                            stats["payments"] += 1
                        except Exception:
                            pass
            except Exception as e:
                logger.warning("Failed to migrate payments: %s", e)

            # Migrate referrals
            try:
                async with sdb.execute("SELECT * FROM referrals") as cur:
                    async for row in cur:
                        doc = {k: row[k] for k in row.keys()}
                        doc.pop("id", None)
                        try:
                            await mongo.referrals.update_one(
                                {"referred_id": doc["referred_id"]},
                                {"$setOnInsert": doc},
                                upsert=True,
                            )
                            stats["referrals"] += 1
                        except Exception:
                            pass
            except Exception as e:
                logger.warning("Failed to migrate referrals: %s", e)

            # Migrate daily_usage
            try:
                async with sdb.execute("SELECT * FROM daily_usage") as cur:
                    async for row in cur:
                        doc = {k: row[k] for k in row.keys()}
                        try:
                            await mongo.daily_usage.update_one(
                                {"user_id": doc["user_id"], "date_key": doc["date_key"]},
                                {"$setOnInsert": doc},
                                upsert=True,
                            )
                            stats["daily_usage"] += 1
                        except Exception:
                            pass
            except Exception as e:
                logger.warning("Failed to migrate daily_usage: %s", e)

            # Migrate extra_quota
            try:
                async with sdb.execute("SELECT * FROM extra_quota") as cur:
                    async for row in cur:
                        doc = {k: row[k] for k in row.keys()}
                        try:
                            await mongo.extra_quota.update_one(
                                {"user_id": doc["user_id"]},
                                {"$setOnInsert": doc},
                                upsert=True,
                            )
                        except Exception:
                            pass
            except Exception as e:
                logger.warning("Failed to migrate extra_quota: %s", e)

            # Migrate reminders_sent
            try:
                async with sdb.execute("SELECT * FROM reminders_sent") as cur:
                    async for row in cur:
                        doc = {k: row[k] for k in row.keys()}
                        try:
                            await mongo.reminders_sent.update_one(
                                {"user_id": doc["user_id"], "reminder": doc["reminder"]},
                                {"$setOnInsert": doc},
                                upsert=True,
                            )
                        except Exception:
                            pass
            except Exception as e:
                logger.warning("Failed to migrate reminders_sent: %s", e)

        # Rename old SQLite file to .bak
        sqlite_path.rename(sqlite_path.with_suffix(".db.bak"))
        logger.info("[Migration] SQLite -> MongoDB complete: %s", stats)

    except Exception as e:
        logger.error("[Migration] Failed: %s", e)

    return stats


async def migrate_from_json(
    limits_file: Path,
    subs_file: Path,
) -> Dict[str, int]:
    """One-time migration from old JSON files to MongoDB."""
    import json
    stats = {"subscriptions": 0, "usage": 0}

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
            subs_file.rename(subs_file.with_suffix(".json.bak"))
            logger.info("Migrated %d subscriptions from JSON", stats["subscriptions"])
        except Exception as e:
            logger.warning("Failed to migrate subscriptions JSON: %s", e)

    if limits_file.exists():
        try:
            data = json.loads(limits_file.read_text(encoding="utf-8"))
            users = data.get("users", {})
            for uid, usage in users.items():
                if not isinstance(usage, dict):
                    continue
                imgs = int((usage).get("images", 0) or 0)
                vids = int((usage).get("videos", 0) or 0)
                if imgs > 0 or vids > 0:
                    await add_usage(int(uid), images=imgs, videos=vids)
                    stats["usage"] += 1
            limits_file.rename(limits_file.with_suffix(".json.bak"))
            logger.info("Migrated %d usage records from JSON", stats["usage"])
        except Exception as e:
            logger.warning("Failed to migrate limits JSON: %s", e)

    return stats
