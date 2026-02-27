"""Grok backend client.

Wraps the existing grok_client (WebSocket-based image/video generation)
as a BackendClient for the unified multi-backend routing system.
"""

import json
import time
import uuid
from typing import Any, Dict, List, Optional

from app.backends.base import BackendClient
from app.core.config import settings
from app.core.logger import logger
from app.services.grok_client import grok_client, ImageProgress, GenerationProgress
from app.services.sso_manager import sso_manager


class GrokBackendClient(BackendClient):
    """Grok image/video generation backend using WebSocket."""

    @property
    def name(self) -> str:
        return "grok"

    async def initialize(self) -> None:
        """Grok client initializes via sso_manager in main.py lifespan - nothing extra needed."""
        logger.info("[GROK] Backend wrapper initialized")

    async def shutdown(self) -> None:
        pass

    def list_models(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": "grok-imagine",
                "object": "model",
                "created": 1700000000,
                "owned_by": "xai",
                "permission": [],
                "root": "grok-imagine",
                "parent": None,
            },
            {
                "id": "grok-2-image",
                "object": "model",
                "created": 1700000000,
                "owned_by": "xai",
                "permission": [],
                "root": "grok-2-image",
                "parent": None,
            },
            {
                "id": "grok-2-video",
                "object": "model",
                "created": 1700000000,
                "owned_by": "xai",
                "permission": [],
                "root": "grok-2-video",
                "parent": None,
            },
        ]

    async def chat(
        self,
        *,
        model: str,
        messages: List[Dict[str, Any]],
        stream: bool = False,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        request_id: str = "",
        base_url: str = "",
    ) -> Any:
        """
        Chat completions for Grok (image generation via chat).

        For Grok, chat is essentially image generation - extract prompt from
        the last user message and generate images.
        """
        # Extract prompt from messages
        prompt = ""
        n = 4
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    prompt = content.strip()
                elif isinstance(content, list):
                    prompt = "".join(
                        p.get("text", "") for p in content if p.get("type") == "text"
                    ).strip()
                if prompt:
                    break

        if not prompt:
            raise ValueError("No prompt found in messages")

        chat_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"

        if stream:
            return self._stream_chat_generate(prompt, n, chat_id)

        # Non-streaming
        result = await grok_client.generate(
            prompt=prompt,
            n=n,
            enable_nsfw=True,
        )

        if not result.get("success"):
            raise RuntimeError(result.get("error", "Image generation failed"))

        urls = result.get("urls", [])
        content = "Generated images:\n\n" + "\n".join(f"![Image]({url})" for url in urls)

        return {
            "id": chat_id,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": len(prompt), "completion_tokens": len(content), "total_tokens": len(prompt) + len(content)},
        }

    async def _stream_chat_generate(self, prompt: str, n: int, chunk_id: str):
        """Stream chat generation for Grok images."""
        stage_progress = {"preview": 33, "medium": 66, "final": 99}
        image_stages: Dict[str, str] = {}

        def _chunk(content: str = "", finish_reason: Optional[str] = None, thinking: Optional[str] = None) -> str:
            delta: Dict[str, Any] = {}
            if content:
                delta["content"] = content
            if thinking:
                delta["thinking"] = thinking
            chunk = {
                "id": chunk_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": "grok-imagine",
                "choices": [{"index": 0, "delta": delta if delta else {}, "finish_reason": finish_reason}],
            }
            return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

        yield _chunk(thinking=f"Generating image: {prompt[:50]}...")

        try:
            async for item in grok_client.generate_stream(
                prompt=prompt, n=n, enable_nsfw=True
            ):
                if item.get("type") == "progress":
                    image_id = item["image_id"]
                    stage = item["stage"]
                    if image_stages.get(image_id) != stage:
                        image_stages[image_id] = stage
                        progress = stage_progress.get(stage, 0)
                        total = item["total"]
                        stage_names = {"preview": "Preview", "medium": "Medium", "final": "HD"}
                        thinking_text = (
                            f"Image {len(image_stages)}/{total} - "
                            f"{stage_names.get(stage, stage)} ({progress}%)"
                        )
                        yield _chunk(thinking=thinking_text)

                elif item.get("type") == "result":
                    if item.get("success"):
                        urls = item.get("urls", [])
                        yield _chunk(thinking=f"Done! {len(urls)} images generated")
                        content = "Generated images:\n\n"
                        for i, url in enumerate(urls, 1):
                            content += f"![Image{i}]({url})\n\n"
                        yield _chunk(content=content)
                    else:
                        yield _chunk(content=f"Generation failed: {item.get('error', 'Unknown error')}")
                    yield _chunk(finish_reason="stop")
                    break

            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.error(f"[GROK] Stream error: {e}")
            yield _chunk(content=f"Error: {str(e)}")
            yield _chunk(finish_reason="stop")
            yield "data: [DONE]\n\n"

    async def generate_image(
        self,
        *,
        prompt: str,
        model: str = "grok-2-image",
        n: int = 4,
        aspect_ratio: str = "2:3",
        response_format: str = "url",
        base_url: str = "",
        request_id: str = "",
    ) -> Dict[str, Any]:
        """Generate images with Grok."""
        result = await grok_client.generate(
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            n=n or settings.DEFAULT_IMAGE_COUNT,
            enable_nsfw=True,
        )

        if not result.get("success"):
            error_msg = result.get("error", "Image generation failed")
            error_code = result.get("error_code", "")
            raise RuntimeError(f"{error_code}: {error_msg}" if error_code else error_msg)

        if response_format == "b64_json":
            data = [{"b64_json": b64} for b64 in result.get("b64_list", [])]
        else:
            data = [{"url": url} for url in result.get("urls", [])]

        return {"created": int(time.time()), "data": data}

    async def generate_video(
        self,
        *,
        prompt: str,
        model: str = "grok-2-video",
        aspect_ratio: str = "16:9",
        duration_seconds: int = 6,
        resolution: str = "480p",
        preset: str = "normal",
        response_format: str = "url",
        base_url: str = "",
        request_id: str = "",
    ) -> Dict[str, Any]:
        """Generate video with Grok."""
        result = await grok_client.generate_video(
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            duration_seconds=duration_seconds,
            resolution=resolution,
            preset=preset,
            enable_nsfw=True,
        )

        if not result.get("success"):
            error_msg = result.get("error", "Video generation failed")
            error_code = result.get("error_code", "")
            raise RuntimeError(f"{error_code}: {error_msg}" if error_code else error_msg)

        if response_format == "b64_json":
            data = [{"b64_json": b64} for b64 in result.get("b64_list", [])]
        else:
            data = [{"url": url} for url in result.get("urls", [])]

        return {"created": int(time.time()), "data": data}

    async def get_status(self) -> Dict[str, Any]:
        try:
            from app.services.sso_manager import sso_manager
            import asyncio

            if hasattr(sso_manager, "get_status") and asyncio.iscoroutinefunction(sso_manager.get_status):
                sso_status = await sso_manager.get_status()
            else:
                sso_status = sso_manager.get_status()

            return {
                "status": "ok",
                "sso_total": sso_status.get("total", sso_status.get("total_keys", 0)),
                "sso_failed": sso_status.get("failed", sso_status.get("failed_count", 0)),
                "models": ["grok-imagine", "grok-2-image", "grok-2-video"],
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}
