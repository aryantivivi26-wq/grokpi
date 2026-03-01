from typing import Any, Dict

import aiohttp

from .config import settings


class GatewayClient:
    def __init__(self, base_url: str, api_key: str = "", timeout_seconds: int = 240):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.post(url, headers=self._headers(), json=payload) as response:
                text = await response.text()
                try:
                    data = await response.json(content_type=None)
                except Exception:
                    data = {"raw": text}
                if response.status >= 400:
                    raise RuntimeError(f"{response.status} - {data}")
                return data

    async def _get(self, path: str) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.get(url, headers=self._headers()) as response:
                text = await response.text()
                try:
                    data = await response.json(content_type=None)
                except Exception:
                    data = {"raw": text}
                if response.status >= 400:
                    raise RuntimeError(f"{response.status} - {data}")
                return data

    async def generate_image(self, prompt: str, n: int, aspect_ratio: str, model: str = "grok-2-image") -> Dict[str, Any]:
        return await self._post(
            "/v1/images/generations",
            {
                "prompt": prompt,
                "model": model,
                "n": n,
                "aspect_ratio": aspect_ratio,
            },
        )

    async def generate_video(
        self,
        prompt: str,
        aspect_ratio: str,
        duration_seconds: int,
        resolution: str,
        preset: str,
        model: str = "grok-2-video",
    ) -> Dict[str, Any]:
        return await self._post(
            "/v1/videos/generations",
            {
                "prompt": prompt,
                "model": model,
                "aspect_ratio": aspect_ratio,
                "duration_seconds": duration_seconds,
                "resolution": resolution,
                "preset": preset,
            },
        )

    async def admin_status(self) -> Dict[str, Any]:
        return await self._get("/admin/status")

    async def reload_sso(self) -> Dict[str, Any]:
        return await self._post("/admin/sso/reload", {})

    async def reload_gemini(self, accounts_json: str = "") -> Dict[str, Any]:
        payload = {}
        if accounts_json:
            payload["accounts_config"] = accounts_json
        return await self._post("/admin/gemini/reload", payload)

    async def gemini_health(self) -> Dict[str, Any]:
        return await self._get("/admin/gemini/health")

    async def list_images(self, limit: int = 12) -> Dict[str, Any]:
        return await self._get(f"/admin/images/list?limit={limit}")

    async def list_videos(self, limit: int = 12) -> Dict[str, Any]:
        return await self._get(f"/admin/videos/list?limit={limit}")

    async def delete_image(self, filename: str) -> Dict[str, Any]:
        return await self._request("DELETE", f"/admin/media/image/{filename}")

    async def delete_video(self, filename: str) -> Dict[str, Any]:
        return await self._request("DELETE", f"/admin/media/video/{filename}")

    async def clear_images(self) -> Dict[str, Any]:
        return await self._request("DELETE", "/admin/images/clear")

    async def clear_videos(self) -> Dict[str, Any]:
        return await self._request("DELETE", "/admin/videos/clear")

    async def _request(self, method: str, path: str) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.request(method, url, headers=self._headers()) as response:
                text = await response.text()
                try:
                    data = await response.json(content_type=None)
                except Exception:
                    data = {"raw": text}
                if response.status >= 400:
                    raise RuntimeError(f"{response.status} - {data}")
                return data


gateway_client = GatewayClient(
    base_url=settings.GATEWAY_BASE_URL,
    api_key=settings.gateway_api_key,
    timeout_seconds=settings.REQUEST_TIMEOUT_SECONDS,
)
