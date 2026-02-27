"""Google API helpers for Gemini Business.

Handles session creation, file upload, downloads, and common headers.
Adapted from g2pi-main/core/google_api.py.
"""

import asyncio
import json
import logging
import os
import time
import uuid
from typing import TYPE_CHECKING, List

import httpx

if TYPE_CHECKING:
    from .account import AccountManager

logger = logging.getLogger(__name__)

GEMINI_API_BASE = "https://biz-discoveryengine.googleapis.com/v1alpha"


def get_common_headers(jwt: str, user_agent: str) -> dict:
    """Generate common request headers."""
    return {
        "accept": "*/*",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
        "authorization": f"Bearer {jwt}",
        "content-type": "application/json",
        "origin": "https://business.gemini.google",
        "referer": "https://business.gemini.google/",
        "user-agent": user_agent,
        "x-server-timeout": "1800",
        "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site",
    }


async def make_request_with_jwt_retry(
    account_mgr: "AccountManager",
    method: str,
    url: str,
    http_client: httpx.AsyncClient,
    user_agent: str,
    request_id: str = "",
    **kwargs,
) -> httpx.Response:
    """Make HTTP request with automatic JWT retry on 401."""
    jwt = await account_mgr.get_jwt(request_id)
    headers = get_common_headers(jwt, user_agent)

    extra_headers = kwargs.pop("headers", None)
    if extra_headers:
        headers.update(extra_headers)

    if method.upper() == "GET":
        resp = await http_client.get(url, headers=headers, **kwargs)
    elif method.upper() == "POST":
        resp = await http_client.post(url, headers=headers, **kwargs)
    else:
        raise ValueError(f"Unsupported HTTP method: {method}")

    # Retry once on 401
    if resp.status_code == 401:
        jwt = await account_mgr.get_jwt(request_id)
        headers = get_common_headers(jwt, user_agent)
        if extra_headers:
            headers.update(extra_headers)

        if method.upper() == "GET":
            resp = await http_client.get(url, headers=headers, **kwargs)
        elif method.upper() == "POST":
            resp = await http_client.post(url, headers=headers, **kwargs)

    return resp


async def create_google_session(
    account_manager: "AccountManager",
    http_client: httpx.AsyncClient,
    user_agent: str,
    request_id: str = "",
) -> str:
    """Create a new Google Discovery Engine session."""
    jwt = await account_manager.get_jwt(request_id)
    headers = get_common_headers(jwt, user_agent)
    body = {
        "configId": account_manager.config.config_id,
        "additionalParams": {"token": "-"},
        "createSessionRequest": {"session": {"name": "", "displayName": ""}},
    }

    req_tag = f"[req_{request_id}] " if request_id else ""
    r = await http_client.post(
        f"{GEMINI_API_BASE}/locations/global/widgetCreateSession",
        headers=headers,
        json=body,
    )
    if r.status_code != 200:
        logger.error(
            f"[SESSION] [{account_manager.config.account_id}] {req_tag}Session create failed: {r.status_code}"
        )
        raise httpx.HTTPStatusError(
            f"createSession failed: {r.status_code}",
            request=r.request,
            response=r,
        )
    sess_name = r.json()["session"]["name"]
    logger.info(f"[SESSION] [{account_manager.config.account_id}] {req_tag}Created: {sess_name[-12:]}")
    return sess_name


async def upload_context_file(
    session_name: str,
    mime_type: str,
    base64_content: str,
    account_manager: "AccountManager",
    http_client: httpx.AsyncClient,
    user_agent: str,
    request_id: str = "",
) -> str:
    """Upload a file to a session, return fileId."""
    jwt = await account_manager.get_jwt(request_id)
    headers = get_common_headers(jwt, user_agent)

    ext = mime_type.split("/")[-1] if "/" in mime_type else "bin"
    file_name = f"upload_{int(time.time())}_{uuid.uuid4().hex[:6]}.{ext}"

    body = {
        "configId": account_manager.config.config_id,
        "additionalParams": {"token": "-"},
        "addContextFileRequest": {
            "name": session_name,
            "fileName": file_name,
            "mimeType": mime_type,
            "fileContents": base64_content,
        },
    }

    r = await http_client.post(
        f"{GEMINI_API_BASE}/locations/global/widgetAddContextFile",
        headers=headers,
        json=body,
    )

    req_tag = f"[req_{request_id}] " if request_id else ""
    if r.status_code != 200:
        logger.error(
            f"[FILE] [{account_manager.config.account_id}] {req_tag}Upload failed: {r.status_code}"
        )
        raise httpx.HTTPStatusError(
            f"Upload failed: {r.status_code}",
            request=r.request,
            response=r,
        )

    data = r.json()
    file_id = data.get("addContextFileResponse", {}).get("fileId")
    logger.info(f"[FILE] [{account_manager.config.account_id}] {req_tag}Uploaded: {mime_type}")
    return file_id


async def get_session_file_metadata(
    account_mgr: "AccountManager",
    session_name: str,
    http_client: httpx.AsyncClient,
    user_agent: str,
    request_id: str = "",
) -> dict:
    """Get file metadata for AI-generated files in a session."""
    body = {
        "configId": account_mgr.config.config_id,
        "additionalParams": {"token": "-"},
        "listSessionFileMetadataRequest": {
            "name": session_name,
            "filter": "file_origin_type = AI_GENERATED",
        },
    }

    resp = await make_request_with_jwt_retry(
        account_mgr,
        "POST",
        f"{GEMINI_API_BASE}/locations/global/widgetListSessionFileMetadata",
        http_client,
        user_agent,
        request_id,
        json=body,
    )

    if resp.status_code != 200:
        logger.warning(
            f"[IMAGE] [{account_mgr.config.account_id}] [req_{request_id}] File metadata failed: {resp.status_code}"
        )
        return {}

    data = resp.json()
    result = {}
    file_metadata_list = data.get("listSessionFileMetadataResponse", {}).get("fileMetadata", [])
    for fm in file_metadata_list:
        fid = fm.get("fileId")
        if fid:
            result[fid] = fm
    return result


def build_image_download_url(session_name: str, file_id: str) -> str:
    return f"{GEMINI_API_BASE}/{session_name}:downloadFile?fileId={file_id}&alt=media"


async def download_image_with_jwt(
    account_mgr: "AccountManager",
    session_name: str,
    file_id: str,
    http_client: httpx.AsyncClient,
    user_agent: str,
    request_id: str = "",
    max_retries: int = 3,
) -> bytes:
    """Download a file with JWT auth and retries."""
    url = build_image_download_url(session_name, file_id)
    logger.info(f"[IMAGE] [{account_mgr.config.account_id}] [req_{request_id}] Downloading: {file_id[:8]}...")

    for attempt in range(max_retries):
        try:
            resp = await asyncio.wait_for(
                make_request_with_jwt_retry(
                    account_mgr,
                    "GET",
                    url,
                    http_client,
                    user_agent,
                    request_id,
                    follow_redirects=True,
                ),
                timeout=180,
            )
            resp.raise_for_status()
            logger.info(
                f"[IMAGE] [{account_mgr.config.account_id}] [req_{request_id}] Downloaded: {file_id[:8]}... ({len(resp.content)} bytes)"
            )
            return resp.content

        except asyncio.TimeoutError:
            logger.warning(
                f"[IMAGE] [{account_mgr.config.account_id}] [req_{request_id}] Timeout ({attempt + 1}/{max_retries})"
            )
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(2**attempt)

        except httpx.HTTPError as e:
            logger.warning(
                f"[IMAGE] [{account_mgr.config.account_id}] [req_{request_id}] Failed ({attempt + 1}/{max_retries}): {type(e).__name__}"
            )
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(2**attempt)

    raise RuntimeError("Image download failed unexpectedly")


def save_media_file(
    data: bytes,
    chat_id: str,
    file_id: str,
    mime_type: str,
    base_url: str,
    output_dir: str,
    url_path: str = "images",
) -> str:
    """Save media file to disk, return public URL."""
    ext_map = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "video/mp4": ".mp4",
        "video/webm": ".webm",
        "video/quicktime": ".mov",
    }
    ext = ext_map.get(mime_type, ".png")
    filename = f"{chat_id}_{file_id}{ext}"
    save_path = os.path.join(output_dir, filename)

    os.makedirs(output_dir, exist_ok=True)
    with open(save_path, "wb") as f:
        f.write(data)

    return f"{base_url}/{url_path}/{filename}"
