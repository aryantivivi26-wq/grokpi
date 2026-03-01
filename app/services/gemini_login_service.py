"""
Gemini Auto-Login Service

Orchestrates headless Chrome login to refresh Gemini Business cookies
automatically when they're about to expire.

Flow:
1. Detect accounts with cookies expiring within REFRESH_WINDOW_HOURS
2. Launch headless Chrome via GeminiAutomation (DrissionPage)
3. Navigate Google auth → send email code → poll generator.email → enter code
4. Extract new cookies (__Secure-C_SES, __Host-C_OSES, csesidx, config_id)
5. Update account config in the gateway's MultiAccountManager
"""

import asyncio
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("gemini.autologin")

# Config
REFRESH_WINDOW_HOURS = int(os.environ.get("GEMINI_REFRESH_WINDOW_HOURS", "2"))
REFRESH_CHECK_INTERVAL_MINUTES = int(os.environ.get("GEMINI_REFRESH_INTERVAL_MINUTES", "30"))
BROWSER_HEADLESS = os.environ.get("GEMINI_BROWSER_HEADLESS", "true").lower() in ("1", "true", "yes")
AUTH_PROXY = os.environ.get("GEMINI_AUTH_PROXY", "")
GENERATOR_EMAIL_DOMAINS = [
    d.strip()
    for d in os.environ.get("GENERATOR_EMAIL_DOMAINS", "").split(",")
    if d.strip()
]


class GeminiAutoLoginService:
    """Manages automatic cookie refresh for Gemini Business accounts."""

    def __init__(self):
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gemini-login")
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._current_login: Optional[str] = None  # account_id being refreshed
        self._on_refresh_callback: Optional[Callable] = None

    def set_refresh_callback(self, callback: Callable):
        """Set callback to be called after successful refresh with (account_index, new_config)."""
        self._on_refresh_callback = callback

    async def refresh_account(self, account: dict, index: int) -> dict:
        """
        Refresh a single account's cookies via browser automation.

        Args:
            account: dict with keys: email, secure_c_ses, host_c_oses, csesidx, config_id,
                     mail_provider, mail_domains (optional)
            index: account index (for logging/callback)

        Returns:
            dict with success/error and optionally new config
        """
        email = account.get("email", "")
        if not email:
            return {"success": False, "error": "No email configured for this account"}

        mail_provider = (account.get("mail_provider") or "generatoremail").lower()
        mail_domains = account.get("mail_domains") or GENERATOR_EMAIL_DOMAINS

        if not mail_domains:
            return {
                "success": False,
                "error": "No generator.email domains configured. Set GENERATOR_EMAIL_DOMAINS env var.",
            }

        self._current_login = email
        logger.info("[AutoLogin] Starting refresh for account %d (%s)", index + 1, email)

        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(
                self._executor,
                self._do_login,
                email,
                mail_provider,
                mail_domains,
                index,
            )
        except Exception as exc:
            logger.error("[AutoLogin] Login executor error: %s", exc)
            result = {"success": False, "error": str(exc)}
        finally:
            self._current_login = None

        if result.get("success") and self._on_refresh_callback:
            try:
                await self._on_refresh_callback(index, result["config"])
            except Exception as exc:
                logger.error("[AutoLogin] Refresh callback error: %s", exc)

        return result

    def _do_login(self, email: str, mail_provider: str, mail_domains: list, index: int) -> dict:
        """Synchronous login in thread pool."""
        try:
            from .automation.browser_login import GeminiAutomation
            from .automation.email_client import GeneratorEmailClient

            def log_cb(level, message):
                getattr(logger, level if level in ("info", "warning", "error", "debug") else "info")(
                    "[AutoLogin][Server %d] %s", index + 1, message
                )

            # Create mail client
            mail_client = GeneratorEmailClient(
                domains=mail_domains,
                log_callback=log_cb,
            )
            mail_client.set_credentials(email)

            # Create browser automation
            automation = GeminiAutomation(
                proxy=AUTH_PROXY,
                headless=BROWSER_HEADLESS,
                timeout=90,
                log_callback=log_cb,
            )

            log_cb("info", f"🔐 Starting Gemini login for {email}...")
            result = automation.login_and_extract(email, mail_client)

            if not result.get("success"):
                error = result.get("error", "Unknown error")
                log_cb("error", f"❌ Login failed: {error}")
                return {"success": False, "error": error}

            config = result["config"]
            log_cb("info", "✅ Login successful! New cookies extracted.")
            return {
                "success": True,
                "config": {
                    "secure_c_ses": config.get("secure_c_ses", ""),
                    "host_c_oses": config.get("host_c_oses", ""),
                    "csesidx": config.get("csesidx", ""),
                    "config_id": config.get("config_id", ""),
                    "expires_at": config.get("expires_at", ""),
                },
            }

        except ImportError as exc:
            logger.error("[AutoLogin] Missing dependency: %s", exc)
            return {
                "success": False,
                "error": f"Missing dependency: {exc}. Install DrissionPage and Chromium.",
            }
        except Exception as exc:
            logger.error("[AutoLogin] Unexpected error: %s", exc)
            return {"success": False, "error": str(exc)}

    def is_account_expiring(self, account: dict) -> bool:
        """Check if account cookies are expiring within REFRESH_WINDOW_HOURS."""
        expires_at = account.get("expires_at", "")
        if not expires_at:
            return False

        try:
            # expires_at is in Beijing time (UTC+8) format: "YYYY-MM-DD HH:MM:SS"
            beijing_tz = timezone(timedelta(hours=8))
            expire_time = datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S")
            expire_time = expire_time.replace(tzinfo=beijing_tz)
            now = datetime.now(beijing_tz)
            remaining_hours = (expire_time - now).total_seconds() / 3600
            return remaining_hours <= REFRESH_WINDOW_HOURS
        except Exception:
            return False

    def get_status(self) -> dict:
        """Return current service status."""
        return {
            "running": self._running,
            "current_login": self._current_login,
            "refresh_window_hours": REFRESH_WINDOW_HOURS,
            "check_interval_minutes": REFRESH_CHECK_INTERVAL_MINUTES,
            "headless": BROWSER_HEADLESS,
            "domains_configured": len(GENERATOR_EMAIL_DOMAINS),
        }


# Singleton
gemini_auto_login = GeminiAutoLoginService()
