"""
QRIS Payment Client for https://qris.hubify.store/

Methods:
  create_transaction(amount, order_id, customer_id) → dict
  check_status(transaction_id)                      → dict
  list_transactions(status, limit, offset)           → dict
"""

import logging
from typing import Any, Dict, Optional

import aiohttp

from .config import settings

logger = logging.getLogger(__name__)

_BASE = settings.QRIS_BASE_URL.rstrip("/")


class QRISClient:
    """Async client for the QRIS Hubify payment API."""

    def __init__(self) -> None:
        self._session: Optional[aiohttp.ClientSession] = None

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {settings.QRIS_API_KEY}",
            "Content-Type": "application/json",
        }

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    # ------------------------------------------------------------------
    # POST /create-transaction
    # ------------------------------------------------------------------
    async def create_transaction(
        self,
        amount: int,
        order_id: Optional[str] = None,
        customer_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a QRIS transaction.

        Returns dict with keys:
          success, transaction_id, amount_original, amount_unique,
          amount_total, qris_content, qris_image_url, expires_at
        """
        payload: Dict[str, Any] = {"amount": amount}
        if order_id:
            payload["order_id"] = order_id
        if customer_id:
            payload["customer_id"] = customer_id

        session = await self._get_session()
        async with session.post(
            f"{_BASE}/create-transaction",
            json=payload,
            headers=self._headers(),
        ) as resp:
            data = await resp.json()
            logger.info(
                "[QRIS] create_transaction amount=%s → status=%s tid=%s",
                amount,
                resp.status,
                data.get("transaction_id", "?"),
            )
            if resp.status != 200 or not data.get("success"):
                raise RuntimeError(f"QRIS create failed: {data}")
            return data

    # ------------------------------------------------------------------
    # GET /check-status/:transaction_id
    # ------------------------------------------------------------------
    async def check_status(self, transaction_id: str) -> Dict[str, Any]:
        """
        Check a transaction's payment status.

        Returns dict with keys:
          success, transaction: {transaction_id, status, amount_original,
          amount_unique, amount_total, paid_at}
        """
        session = await self._get_session()
        async with session.get(
            f"{_BASE}/check-status/{transaction_id}",
            headers=self._headers(),
        ) as resp:
            data = await resp.json()
            return data

    # ------------------------------------------------------------------
    # GET /transactions
    # ------------------------------------------------------------------
    async def list_transactions(
        self,
        status: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status
        session = await self._get_session()
        async with session.get(
            f"{_BASE}/transactions",
            headers=self._headers(),
            params=params,
        ) as resp:
            return await resp.json()


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

qris_client = QRISClient()
