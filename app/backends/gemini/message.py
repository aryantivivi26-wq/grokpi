"""Message parsing utilities for Gemini backend.

Adapted from g2pi-main/core/message.py.
"""

import asyncio
import base64
import hashlib
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)


def get_conversation_key(messages: List[dict], client_identifier: str = "") -> str:
    """Generate a conversation fingerprint from the first 3 messages + client ID."""
    if not messages:
        return f"{client_identifier}:empty" if client_identifier else "empty"

    fingerprints = []
    for msg in messages[:3]:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if isinstance(content, list):
            text = extract_text_from_content(content)
        else:
            text = str(content)
        text = text.strip().lower()
        fingerprints.append(f"{role}:{text}")

    prefix = "|".join(fingerprints)
    if client_identifier:
        prefix = f"{client_identifier}|{prefix}"

    return hashlib.md5(prefix.encode()).hexdigest()


def extract_text_from_content(content) -> str:
    """Extract text from message content (string or multimodal list)."""
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        return "".join(x.get("text", "") for x in content if x.get("type") == "text")
    return str(content)


async def parse_last_message(
    messages: List[Dict[str, Any]],
    http_client: httpx.AsyncClient,
    request_id: str = "",
) -> Tuple[str, List[Dict[str, str]]]:
    """
    Parse the last message, extracting text and file attachments.

    Returns: (text_content, images_list)
      where images_list = [{"mime": str, "data": str_base64}, ...]
    """
    if not messages:
        return "", []

    last_msg = messages[-1]
    content = last_msg.get("content", "")

    text_content = ""
    images: List[Dict[str, str]] = []
    image_urls: List[str] = []

    if isinstance(content, str):
        text_content = content
    elif isinstance(content, list):
        for part in content:
            if part.get("type") == "text":
                text_content += part.get("text", "")
            elif part.get("type") == "image_url":
                url = part.get("image_url", {}).get("url", "")
                match = re.match(r"data:([^;]+);base64,(.+)", url)
                if match:
                    images.append({"mime": match.group(1), "data": match.group(2)})
                elif url.startswith(("http://", "https://")):
                    image_urls.append(url)
                else:
                    logger.warning(f"[FILE] [req_{request_id}] Unsupported file format: {url[:30]}...")

    # Download remote image URLs
    if image_urls:
        async def download_url(url: str) -> Optional[Dict[str, str]]:
            try:
                resp = await http_client.get(url, timeout=30, follow_redirects=True)
                if resp.status_code == 404:
                    logger.warning(f"[FILE] [req_{request_id}] URL not found (404): {url[:50]}...")
                    return None
                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "application/octet-stream").split(";")[0]
                b64 = base64.b64encode(resp.content).decode()
                return {"mime": content_type, "data": b64}
            except Exception as e:
                logger.warning(f"[FILE] [req_{request_id}] Download failed: {url[:50]}... - {e}")
                return None

        results = await asyncio.gather(*[download_url(u) for u in image_urls], return_exceptions=True)
        for result in results:
            if isinstance(result, dict):
                images.append(result)

    return text_content, images


def build_full_context_text(messages: List[Dict[str, Any]]) -> str:
    """Build full conversation context as plain text (for session retries)."""
    prompt = ""
    for msg in messages:
        role = "User" if msg.get("role") in ("user", "system") else "Assistant"
        content = msg.get("content", "")
        content_str = extract_text_from_content(content)

        if isinstance(content, list):
            image_count = sum(1 for part in content if part.get("type") == "image_url")
            if image_count > 0:
                content_str += "[Image]" * image_count

        prompt += f"{role}: {content_str}\n\n"
    return prompt
