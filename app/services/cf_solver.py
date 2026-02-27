"""Auto CF_CLEARANCE refresher via FlareSolverr

Secara otomatis mengambil dan memperbarui cf_clearance cookie dari grok.com
menggunakan FlareSolverr yang berjalan di Docker.

Konfigurasi di .env:
    FLARESOLVERR_URL=http://localhost:8191   (default)
    CF_REFRESH_INTERVAL=3600                 (refresh setiap N detik, default 1 jam)
"""

import asyncio
import time
from typing import Optional

import aiohttp

from app.core.config import settings
from app.core.logger import logger


class CFSolver:
    """Mengelola auto-refresh cf_clearance dari FlareSolverr"""

    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._last_refresh: float = 0
        self._consecutive_failures: int = 0
        self.user_agent: str = ""  # UA dari FlareSolverr, harus match cf_clearance

    @property
    def flaresolverr_url(self) -> str:
        return getattr(settings, "FLARESOLVERR_URL", "") or "http://localhost:8191"

    @property
    def refresh_interval(self) -> int:
        return getattr(settings, "CF_REFRESH_INTERVAL", 0) or 3600

    async def _is_flaresolverr_available(self) -> bool:
        """Cek apakah FlareSolverr berjalan"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.flaresolverr_url, timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return "FlareSolverr" in data.get("msg", "")
        except Exception:
            pass
        return False

    async def fetch_cf_clearance(self) -> Optional[str]:
        """Ambil cf_clearance dari FlareSolverr satu kali"""
        url = f"{self.flaresolverr_url}/v1"
        payload = {
            "cmd": "request.get",
            "url": "https://grok.com",
            "maxTimeout": 60000,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=90),
                ) as resp:
                    if resp.status != 200:
                        logger.warning(f"[CF] FlareSolverr response: {resp.status}")
                        return None

                    data = await resp.json()
                    status = data.get("status")
                    if status != "ok":
                        logger.warning(f"[CF] FlareSolverr status: {status} - {data.get('message', '')[:100]}")
                        return None

                    # Capture user-agent (cf_clearance terikat ke UA)
                    solution = data.get("solution", {})
                    ua = solution.get("userAgent", "")
                    if ua:
                        self.user_agent = ua
                        logger.info(f"[CF] User-Agent: {ua[:60]}...")

                    cookies = solution.get("cookies", [])
                    for cookie in cookies:
                        if cookie.get("name") == "cf_clearance":
                            return cookie["value"]

                    logger.warning("[CF] cf_clearance tidak ditemukan di response cookies")
                    return None
        except asyncio.TimeoutError:
            logger.warning("[CF] FlareSolverr timeout (90s)")
            return None
        except Exception as e:
            logger.warning(f"[CF] Error: {e}")
            return None

    async def refresh_once(self) -> bool:
        """Refresh cf_clearance sekali dan update settings"""
        logger.info("[CF] Mengambil cf_clearance dari FlareSolverr...")

        value = await self.fetch_cf_clearance()
        if not value:
            self._consecutive_failures += 1
            logger.warning(f"[CF] Gagal mengambil cf_clearance (gagal berturut: {self._consecutive_failures}x)")
            return False

        old = settings.CF_CLEARANCE
        settings.CF_CLEARANCE = value
        self._last_refresh = time.time()
        self._consecutive_failures = 0

        if old and old != value:
            logger.info(f"[CF] cf_clearance diperbarui: {value[:30]}...")
        else:
            logger.info(f"[CF] cf_clearance diperoleh: {value[:30]}...")

        return True

    async def _loop(self):
        """Background loop yang refresh cf_clearance secara berkala"""
        # Refresh pertama saat startup
        await self.refresh_once()

        while True:
            interval = self.refresh_interval
            # Back-off jika gagal berturut-turut
            if self._consecutive_failures > 0:
                interval = min(interval, 300 * self._consecutive_failures)

            await asyncio.sleep(interval)

            try:
                await self.refresh_once()
            except Exception as e:
                logger.error(f"[CF] Error di refresh loop: {e}")
                self._consecutive_failures += 1

    async def start(self):
        """Mulai background auto-refresh jika FlareSolverr tersedia"""
        available = await self._is_flaresolverr_available()
        if not available:
            logger.info("[CF] FlareSolverr tidak terdeteksi, auto-refresh dinonaktifkan")
            return False

        logger.info(f"[CF] FlareSolverr terdeteksi di {self.flaresolverr_url}")
        logger.info(f"[CF] Auto-refresh aktif (interval: {self.refresh_interval}s)")

        self._task = asyncio.create_task(self._loop())
        return True

    async def stop(self):
        """Hentikan background auto-refresh"""
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            logger.info("[CF] Auto-refresh dihentikan")

    def get_status(self) -> dict:
        """Status untuk admin endpoint"""
        return {
            "active": self._task is not None and not self._task.done(),
            "last_refresh": self._last_refresh,
            "consecutive_failures": self._consecutive_failures,
            "cf_clearance_set": bool(settings.CF_CLEARANCE),
            "cf_clearance_prefix": settings.CF_CLEARANCE[:20] + "..." if settings.CF_CLEARANCE else "",
            "user_agent": self.user_agent[:60] + "..." if self.user_agent else "",
        }


cf_solver = CFSolver()
