"""JWT module for Gemini Business API authentication.

Generates JWT tokens using HMAC-SHA256 from session cookies.
Adapted from g2pi-main/core/jwt.py.
"""

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import time
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from .account import AccountConfig

logger = logging.getLogger(__name__)


def urlsafe_b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def kq_encode(s: str) -> str:
    b = bytearray()
    for ch in s:
        v = ord(ch)
        if v > 255:
            b.append(v & 255)
            b.append(v >> 8)
        else:
            b.append(v)
    return urlsafe_b64encode(bytes(b))


def create_jwt(key_bytes: bytes, key_id: str, csesidx: str) -> str:
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT", "kid": key_id}
    payload = {
        "iss": "https://business.gemini.google",
        "aud": "https://biz-discoveryengine.googleapis.com",
        "sub": f"csesidx/{csesidx}",
        "iat": now,
        "exp": now + 300,
        "nbf": now,
    }
    header_b64 = kq_encode(json.dumps(header, separators=(",", ":")))
    payload_b64 = kq_encode(json.dumps(payload, separators=(",", ":")))
    message = f"{header_b64}.{payload_b64}"
    sig = hmac.new(key_bytes, message.encode(), hashlib.sha256).digest()
    return f"{message}.{urlsafe_b64encode(sig)}"


class JWTManager:
    """Manages JWT token retrieval and caching for a single account."""

    def __init__(self, config: "AccountConfig", http_client: httpx.AsyncClient, user_agent: str) -> None:
        self.config = config
        self.http_client = http_client
        self.user_agent = user_agent
        self.jwt: str = ""
        self.expires: float = 0
        self._lock = asyncio.Lock()

    async def get(self, request_id: str = "") -> str:
        """Get a valid JWT token (refreshes if expired)."""
        async with self._lock:
            if time.time() > self.expires:
                await self._refresh(request_id)
            return self.jwt

    async def _refresh(self, request_id: str = "") -> None:
        """Refresh the JWT token from Google auth endpoint.

        Also captures any Set-Cookie headers to auto-refresh session cookies.
        """
        cookie = f"__Secure-C_SES={self.config.secure_c_ses}"
        if self.config.host_c_oses:
            cookie += f"; __Host-C_OSES={self.config.host_c_oses}"

        req_tag = f"[req_{request_id}] " if request_id else ""
        r = await self.http_client.get(
            "https://business.gemini.google/auth/getoxsrf",
            params={"csesidx": self.config.csesidx},
            headers={
                "cookie": cookie,
                "user-agent": self.user_agent,
                "referer": "https://business.gemini.google/",
            },
        )
        if r.status_code != 200:
            logger.error(f"[AUTH] [{self.config.account_id}] {req_tag}JWT refresh failed: {r.status_code}")
            raise httpx.HTTPStatusError(
                f"getoxsrf failed: {r.status_code}",
                request=r.request,
                response=r,
            )

        # Auto-refresh: capture rotated cookies from Set-Cookie headers
        self._capture_set_cookies(r, request_id)

        txt = r.text[4:] if r.text.startswith(")]}'") else r.text
        data = json.loads(txt)

        key_bytes = base64.urlsafe_b64decode(data["xsrfToken"] + "==")
        self.jwt = create_jwt(key_bytes, data["keyId"], self.config.csesidx)
        self.expires = time.time() + 270

    def _capture_set_cookies(self, response, request_id: str = "") -> None:
        """Extract any rotated cookies from the response and update config."""
        set_cookie_headers = response.headers.multi_items()
        updated = False
        for name, value in set_cookie_headers:
            if name.lower() != "set-cookie":
                continue
            cookie_str = value.split(";")[0]  # "name=value"
            if "=" not in cookie_str:
                continue
            cname, cval = cookie_str.split("=", 1)
            cname = cname.strip()
            cval = cval.strip()
            if cname == "__Secure-C_SES" and cval and cval != self.config.secure_c_ses:
                old_prefix = self.config.secure_c_ses[:20]
                self.config.secure_c_ses = cval
                updated = True
                logger.info(
                    f"[AUTH] [{self.config.account_id}] Cookie __Secure-C_SES auto-refreshed "
                    f"(was {old_prefix}...)"
                )
            elif cname == "__Host-C_OSES" and cval and cval != (self.config.host_c_oses or ""):
                self.config.host_c_oses = cval
                updated = True
                logger.info(f"[AUTH] [{self.config.account_id}] Cookie __Host-C_OSES auto-refreshed")
        if updated:
            # Mark last refresh time  
            self.config._last_cookie_refresh = time.time()
