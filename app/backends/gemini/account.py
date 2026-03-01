"""Account management for Gemini Business.

Handles single-account JWT/cooldown state and multi-account rotation.
Adapted from g2pi-main/core/account.py (simplified - no storage/persistence).
"""

import asyncio
import json
import logging
import os
import random
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .jwt_manager import JWTManager

logger = logging.getLogger(__name__)

QUOTA_TYPES = {"text": "Chat", "images": "Image", "videos": "Video"}


@dataclass
class AccountConfig:
    """Config for a single Gemini Business account."""

    account_id: str
    secure_c_ses: str
    host_c_oses: Optional[str]
    csesidx: str
    config_id: str
    expires_at: Optional[str] = None
    disabled: bool = False
    _last_cookie_refresh: float = 0.0

    def get_remaining_hours(self) -> Optional[float]:
        if not self.expires_at:
            return None
        try:
            tz = timezone(timedelta(hours=8))
            expire_time = datetime.strptime(self.expires_at, "%Y-%m-%d %H:%M:%S").replace(tzinfo=tz)
            now = datetime.now(tz)
            return (expire_time - now).total_seconds() / 3600
        except Exception:
            return None

    def is_expired(self) -> bool:
        remaining = self.get_remaining_hours()
        if remaining is None:
            return False
        return remaining <= 0


@dataclass(frozen=True)
class CooldownConfig:
    text: int = 60
    images: int = 60
    videos: int = 60


@dataclass(frozen=True)
class RetryPolicy:
    cooldowns: CooldownConfig = CooldownConfig()


class AccountManager:
    """Manages a single Gemini account with JWT and quota cooldowns."""

    def __init__(
        self,
        config: AccountConfig,
        http_client,
        user_agent: str,
        retry_policy: RetryPolicy,
    ):
        self.config = config
        self.http_client = http_client
        self.user_agent = user_agent
        self.text_cooldown_seconds = retry_policy.cooldowns.text
        self.images_cooldown_seconds = retry_policy.cooldowns.images
        self.videos_cooldown_seconds = retry_policy.cooldowns.videos
        self.jwt_manager: Optional["JWTManager"] = None
        self.is_available = True
        self.quota_cooldowns: Dict[str, float] = {}
        self.conversation_count = 0
        self.failure_count = 0
        self.session_usage_count = 0

    def _get_cooldown_seconds(self, quota_type: Optional[str]) -> int:
        if quota_type == "images":
            return self.images_cooldown_seconds
        if quota_type == "videos":
            return self.videos_cooldown_seconds
        return self.text_cooldown_seconds

    def handle_error(self, context: str = "", request_id: str = "", quota_type: Optional[str] = None) -> None:
        if not quota_type or quota_type not in QUOTA_TYPES:
            quota_type = "text"
        self.quota_cooldowns[quota_type] = time.time()
        cd = self._get_cooldown_seconds(quota_type)
        req_tag = f"[req_{request_id}] " if request_id else ""
        logger.warning(
            f"[ACCOUNT] [{self.config.account_id}] {req_tag}{context}, "
            f"{QUOTA_TYPES[quota_type]} cooldown {cd}s"
        )

    def is_quota_available(self, quota_type: str) -> bool:
        if quota_type not in QUOTA_TYPES:
            return True
        cooldown_time = self.quota_cooldowns.get(quota_type)
        if not cooldown_time:
            return True
        elapsed = time.time() - cooldown_time
        cd = self._get_cooldown_seconds(quota_type)
        if elapsed < cd:
            return False
        del self.quota_cooldowns[quota_type]
        return True

    def are_quotas_available(self, quota_types: Optional[Iterable[str]] = None) -> bool:
        if not quota_types:
            return True
        if isinstance(quota_types, str):
            quota_types = [quota_types]
        if not self.is_quota_available("text"):
            return False
        return all(self.is_quota_available(qt) for qt in quota_types if qt != "text")

    async def get_jwt(self, request_id: str = "") -> str:
        if self.config.is_expired():
            self.is_available = False
            raise RuntimeError(f"Account {self.config.account_id} has expired")
        try:
            if self.jwt_manager is None:
                from .jwt_manager import JWTManager
                self.jwt_manager = JWTManager(self.config, self.http_client, self.user_agent)
            jwt = await self.jwt_manager.get(request_id)
            self.is_available = True
            return jwt
        except Exception as e:
            self.handle_error("JWT refresh failed", request_id)
            raise


class MultiAccountManager:
    """Pool of AccountManagers with round-robin rotation and session caching."""

    def __init__(self, session_cache_ttl_seconds: int = 1800):
        self.accounts: Dict[str, AccountManager] = {}
        self.account_list: List[str] = []
        self._counter_lock = threading.Lock()
        self._request_counter = 0
        self._last_account_count = 0
        self._cache_lock = asyncio.Lock()
        self.global_session_cache: Dict[str, dict] = {}
        self.cache_max_size = 1000
        self.cache_ttl = session_cache_ttl_seconds
        self._session_locks: Dict[str, asyncio.Lock] = {}
        self._session_locks_lock = asyncio.Lock()

    def add_account(
        self,
        config: AccountConfig,
        http_client,
        user_agent: str,
        retry_policy: RetryPolicy,
    ) -> None:
        manager = AccountManager(config, http_client, user_agent, retry_policy)
        self.accounts[config.account_id] = manager
        self.account_list.append(config.account_id)
        logger.debug(f"[MULTI] Added account: {config.account_id}")

    def get_available_accounts(self, required_quota_types: Optional[Iterable[str]] = None) -> List[AccountManager]:
        available = []
        for acc in self.accounts.values():
            if acc.config.disabled:
                continue
            if acc.config.is_expired():
                continue
            if not acc.are_quotas_available(required_quota_types):
                continue
            available.append(acc)
        return available

    async def get_account(
        self,
        account_id: Optional[str] = None,
        request_id: str = "",
        required_quota_types: Optional[Iterable[str]] = None,
    ) -> AccountManager:
        if account_id:
            if account_id not in self.accounts:
                raise RuntimeError(f"Account {account_id} not found")
            account = self.accounts[account_id]
            if not account.are_quotas_available(required_quota_types):
                raise RuntimeError(f"Account {account_id} quota unavailable")
            return account

        available = self.get_available_accounts(required_quota_types)
        if not available:
            raise RuntimeError("No available Gemini accounts")

        with self._counter_lock:
            if len(available) != self._last_account_count:
                self._request_counter = random.randint(0, 999999)
                self._last_account_count = len(available)
            index = self._request_counter % len(available)
            self._request_counter += 1

        selected = available[index]
        selected.session_usage_count += 1
        logger.info(
            f"[MULTI] [req_{request_id}] Selected: {selected.config.account_id} "
            f"({index}/{len(available)})"
        )
        return selected

    async def set_session_cache(self, conv_key: str, account_id: str, session_id: str) -> None:
        async with self._cache_lock:
            self.global_session_cache[conv_key] = {
                "account_id": account_id,
                "session_id": session_id,
                "updated_at": time.time(),
            }
            # Evict if too large
            if len(self.global_session_cache) > self.cache_max_size:
                sorted_items = sorted(
                    self.global_session_cache.items(), key=lambda x: x[1]["updated_at"]
                )
                remove_count = len(sorted_items) - int(self.cache_max_size * 0.8)
                for key, _ in sorted_items[:remove_count]:
                    del self.global_session_cache[key]

    async def update_session_time(self, conv_key: str) -> None:
        async with self._cache_lock:
            if conv_key in self.global_session_cache:
                self.global_session_cache[conv_key]["updated_at"] = time.time()

    async def acquire_session_lock(self, conv_key: str) -> asyncio.Lock:
        async with self._session_locks_lock:
            if conv_key not in self._session_locks:
                self._session_locks[conv_key] = asyncio.Lock()
            return self._session_locks[conv_key]

    async def start_background_cleanup(self) -> None:
        """Periodically clean expired session caches."""
        try:
            while True:
                await asyncio.sleep(300)
                async with self._cache_lock:
                    current = time.time()
                    expired = [
                        k for k, v in self.global_session_cache.items()
                        if current - v["updated_at"] > self.cache_ttl
                    ]
                    for k in expired:
                        del self.global_session_cache[k]
                    if expired:
                        logger.info(f"[CACHE] Cleaned {len(expired)} expired sessions")
        except asyncio.CancelledError:
            pass

    def update_http_client(self, http_client) -> None:
        for acc in self.accounts.values():
            acc.http_client = http_client
            if acc.jwt_manager is not None:
                acc.jwt_manager.http_client = http_client


def load_gemini_accounts(
    accounts_config: str,
    http_client,
    user_agent: str,
    retry_policy: RetryPolicy,
    session_cache_ttl: int = 1800,
) -> MultiAccountManager:
    """
    Load Gemini accounts from a JSON string (env var GEMINI_ACCOUNTS_CONFIG).

    Expected format: [{"secure_c_ses": "...", "csesidx": "...", "config_id": "...", ...}, ...]
    """
    manager = MultiAccountManager(session_cache_ttl)

    if not accounts_config:
        logger.warning("[GEMINI] No accounts configured (GEMINI_ACCOUNTS_CONFIG is empty)")
        return manager

    try:
        accounts_data = json.loads(accounts_config)
    except json.JSONDecodeError as e:
        logger.error(f"[GEMINI] Failed to parse GEMINI_ACCOUNTS_CONFIG: {e}")
        return manager

    for i, acc in enumerate(accounts_data, 1):
        required = ["secure_c_ses", "csesidx", "config_id"]
        missing = [f for f in required if f not in acc]
        if missing:
            logger.error(f"[GEMINI] Account {i} missing fields: {missing}")
            continue

        config = AccountConfig(
            account_id=acc.get("id", f"gemini_{i}"),
            secure_c_ses=acc["secure_c_ses"],
            host_c_oses=acc.get("host_c_oses"),
            csesidx=acc["csesidx"],
            config_id=acc["config_id"],
            expires_at=acc.get("expires_at"),
            disabled=acc.get("disabled", False),
        )

        if config.is_expired():
            logger.debug(f"[GEMINI] Account {config.account_id} expired, skipping")

        manager.add_account(config, http_client, user_agent, retry_policy)

    logger.info(f"[GEMINI] Loaded {len(manager.accounts)} accounts")
    return manager
