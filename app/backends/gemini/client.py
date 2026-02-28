"""Gemini Business backend client.

Wraps Google Gemini Business API as a BackendClient, providing OpenAI-compatible
chat completions, image generation, and video generation.

Adapted from g2pi-main/main.py (chat_impl, stream_chat_generator, etc.)
"""

import asyncio
import base64
import json
import logging
import os
import re
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from app.backends.base import BackendClient
from app.core.config import settings

from .account import (
    AccountConfig,
    AccountManager,
    CooldownConfig,
    MultiAccountManager,
    RetryPolicy,
    load_gemini_accounts,
)
from .google_api import (
    create_google_session,
    download_image_with_jwt,
    get_common_headers,
    get_session_file_metadata,
    save_media_file,
    upload_context_file,
)
from .message import (
    build_full_context_text,
    extract_text_from_content,
    get_conversation_key,
    parse_last_message,
)
from .streaming_parser import parse_json_array_stream_async

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)
TIMEOUT_SECONDS = 600

# Model mapping: API name -> upstream model ID (None = auto)
MODEL_MAPPING = {
    "gemini-auto": None,
    "gemini-2.5-flash": "gemini-2.5-flash",
    "gemini-2.5-pro": "gemini-2.5-pro",
    "gemini-3-flash-preview": "gemini-3-flash-preview",
    "gemini-3.1-pro-preview": "gemini-3.1-pro-preview",
}

# Virtual models (image/video generation)
VIRTUAL_MODELS = {
    "gemini-imagen": {"imageGenerationSpec": {}},
    "gemini-veo": {"videoGenerationSpec": {}},
}

MODEL_TO_QUOTA_TYPE = {
    "gemini-imagen": "images",
    "gemini-veo": "videos",
}

# Image generation models (models that can also generate images inline)
IMAGE_GENERATION_MODELS = {"gemini-2.5-flash", "gemini-2.5-pro", "gemini-3-flash-preview", "gemini-3.1-pro-preview"}


def _get_tools_spec(model_name: str) -> dict:
    """Return tool config for a given model."""
    if model_name in VIRTUAL_MODELS:
        return VIRTUAL_MODELS[model_name]

    tools_spec: dict = {
        "webGroundingSpec": {},
        "toolRegistry": "default_tool_registry",
    }

    if model_name in IMAGE_GENERATION_MODELS:
        tools_spec["imageGenerationSpec"] = {}

    return tools_spec


def _get_required_quota_types(model_name: str) -> List[str]:
    required = ["text"]
    qt = MODEL_TO_QUOTA_TYPE.get(model_name)
    if qt and qt != "text":
        required.append(qt)
    elif model_name in IMAGE_GENERATION_MODELS:
        required.append("images")
    return required


def _create_chunk(id: str, created: int, model: str, delta: dict, finish_reason: Optional[str]) -> str:
    chunk = {
        "id": id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "logprobs": None,
                "finish_reason": finish_reason,
            }
        ],
        "system_fingerprint": None,
    }
    return json.dumps(chunk)


def _parse_images_from_response(data_list: list) -> tuple:
    """Parse image file IDs from streaming response objects."""
    file_ids = []
    session_name = ""
    seen = set()

    for data in data_list:
        sar = data.get("streamAssistResponse")
        if not sar:
            continue

        session_info = sar.get("sessionInfo", {})
        if session_info.get("session"):
            session_name = session_info["session"]

        answer = sar.get("answer") or {}
        replies = answer.get("replies") or []

        for reply in replies:
            gc = reply.get("groundedContent", {})
            content = gc.get("content", {})
            file_info = content.get("file")
            if file_info and file_info.get("fileId"):
                fid = file_info["fileId"]
                if fid in seen:
                    continue
                seen.add(fid)
                mime_type = file_info.get("mimeType", "image/png")
                file_ids.append({"fileId": fid, "mimeType": mime_type})

    return file_ids, session_name


class GeminiBackendClient(BackendClient):
    """Gemini Business API backend."""

    def __init__(self) -> None:
        self._http_client: Optional[httpx.AsyncClient] = None
        self._http_client_chat: Optional[httpx.AsyncClient] = None
        self._multi_account_mgr: Optional[MultiAccountManager] = None
        self._max_account_switch_tries = 3
        self._cleanup_task: Optional[asyncio.Task] = None

    @property
    def name(self) -> str:
        return "gemini"

    async def initialize(self) -> None:
        """Initialize HTTP clients and load accounts."""
        proxy = getattr(settings, "GEMINI_PROXY_URL", None) or None

        self._http_client = httpx.AsyncClient(
            proxy=proxy,
            verify=False,
            http2=False,
            timeout=httpx.Timeout(TIMEOUT_SECONDS, connect=60.0),
            limits=httpx.Limits(max_keepalive_connections=100, max_connections=200),
        )
        self._http_client_chat = httpx.AsyncClient(
            proxy=proxy,
            verify=False,
            http2=False,
            timeout=httpx.Timeout(TIMEOUT_SECONDS, connect=60.0),
            limits=httpx.Limits(max_keepalive_connections=100, max_connections=200),
        )

        accounts_config = getattr(settings, "GEMINI_ACCOUNTS_CONFIG", "") or os.environ.get("GEMINI_ACCOUNTS_CONFIG", "")
        cooldown_text = int(getattr(settings, "GEMINI_COOLDOWN_TEXT", 60))
        cooldown_images = int(getattr(settings, "GEMINI_COOLDOWN_IMAGES", 60))
        cooldown_videos = int(getattr(settings, "GEMINI_COOLDOWN_VIDEOS", 60))
        session_ttl = int(getattr(settings, "GEMINI_SESSION_CACHE_TTL", 1800))

        retry_policy = RetryPolicy(
            cooldowns=CooldownConfig(
                text=cooldown_text,
                images=cooldown_images,
                videos=cooldown_videos,
            )
        )

        self._multi_account_mgr = load_gemini_accounts(
            accounts_config,
            self._http_client,
            USER_AGENT,
            retry_policy,
            session_ttl,
        )

        if self._multi_account_mgr.accounts:
            self._cleanup_task = asyncio.create_task(
                self._multi_account_mgr.start_background_cleanup()
            )

        logger.info(f"[GEMINI] Backend initialized with {len(self._multi_account_mgr.accounts)} accounts")

    async def shutdown(self) -> None:
        if self._cleanup_task:
            self._cleanup_task.cancel()
        if self._http_client:
            await self._http_client.aclose()
        if self._http_client_chat:
            await self._http_client_chat.aclose()

    def list_models(self) -> List[Dict[str, Any]]:
        models = []
        all_model_ids = list(MODEL_MAPPING.keys()) + list(VIRTUAL_MODELS.keys())
        for mid in all_model_ids:
            models.append(
                {
                    "id": mid,
                    "object": "model",
                    "created": 1700000000,
                    "owned_by": "google",
                    "permission": [],
                    "root": mid,
                    "parent": None,
                }
            )
        return models

    def _all_model_ids(self) -> List[str]:
        return list(MODEL_MAPPING.keys()) + list(VIRTUAL_MODELS.keys())

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
        """Handle Gemini chat completion request."""
        if not request_id:
            request_id = str(uuid.uuid4())[:6]

        if model not in MODEL_MAPPING and model not in VIRTUAL_MODELS:
            raise ValueError(f"Model '{model}' not found. Available: {self._all_model_ids()}")

        if not self._multi_account_mgr or not self._multi_account_mgr.accounts:
            raise RuntimeError("No Gemini accounts configured")

        required_quota_types = _get_required_quota_types(model)

        # Get client IP / conversation key
        conv_key = get_conversation_key(messages)
        session_lock = await self._multi_account_mgr.acquire_session_lock(conv_key)

        account_manager: Optional[AccountManager] = None
        google_session: Optional[str] = None
        is_new_conversation = False

        # Session acquisition (under lock)
        async with session_lock:
            cached = self._multi_account_mgr.global_session_cache.get(conv_key)

            if cached:
                try:
                    account_manager = await self._multi_account_mgr.get_account(
                        cached["account_id"], request_id, required_quota_types
                    )
                    google_session = cached["session_id"]
                    is_new_conversation = False
                    logger.info(
                        f"[GEMINI] [{cached['account_id']}] [req_{request_id}] Resuming session"
                    )
                except Exception:
                    self._multi_account_mgr.global_session_cache.pop(conv_key, None)
                    cached = None

            if not cached:
                available = self._multi_account_mgr.get_available_accounts(required_quota_types)
                max_retries = min(self._max_account_switch_tries, max(len(available), 1))
                last_error = None

                for retry_idx in range(max_retries):
                    try:
                        account_manager = await self._multi_account_mgr.get_account(
                            None, request_id, required_quota_types
                        )
                        google_session = await create_google_session(
                            account_manager, self._http_client, USER_AGENT, request_id
                        )
                        await self._multi_account_mgr.set_session_cache(
                            conv_key, account_manager.config.account_id, google_session
                        )
                        is_new_conversation = True
                        break
                    except Exception as e:
                        last_error = e
                        acc_id = account_manager.config.account_id if account_manager else "unknown"
                        logger.error(
                            f"[GEMINI] [req_{request_id}] Account {acc_id} session failed "
                            f"(try {retry_idx + 1}/{max_retries}): {e}"
                        )
                        if account_manager:
                            qt = MODEL_TO_QUOTA_TYPE.get(model, "text")
                            account_manager.handle_error("session create failed", request_id, qt)
                        if retry_idx == max_retries - 1:
                            raise RuntimeError(
                                f"All Gemini accounts unavailable: {last_error}"
                            ) from last_error

        if account_manager is None or google_session is None:
            raise RuntimeError("No available Gemini accounts")

        # Parse messages
        last_text, current_images = await parse_last_message(
            messages, self._http_client, request_id
        )

        text_to_send = last_text
        is_retry_mode = is_new_conversation

        chat_id = f"chatcmpl-{uuid.uuid4()}"
        created_time = int(time.time())

        # Build the response wrapper with retry logic
        async def response_wrapper():
            nonlocal account_manager, google_session

            available = self._multi_account_mgr.get_available_accounts(required_quota_types)
            max_retries = min(self._max_account_switch_tries, max(len(available), 1))

            current_text = text_to_send
            current_retry_mode = is_retry_mode
            current_file_ids: List[str] = []

            for retry_idx in range(max_retries):
                try:
                    cached = self._multi_account_mgr.global_session_cache.get(conv_key)
                    if not cached:
                        new_sess = await create_google_session(
                            account_manager, self._http_client, USER_AGENT, request_id
                        )
                        await self._multi_account_mgr.set_session_cache(
                            conv_key, account_manager.config.account_id, new_sess
                        )
                        current_session = new_sess
                        current_retry_mode = True
                        current_file_ids = []
                    else:
                        current_session = cached["session_id"]

                    # Upload images if needed
                    if current_images and not current_file_ids:
                        for img in current_images:
                            fid = await upload_context_file(
                                current_session, img["mime"], img["data"],
                                account_manager, self._http_client, USER_AGENT, request_id
                            )
                            current_file_ids.append(fid)

                    # Build full context on retry
                    if current_retry_mode:
                        current_text = build_full_context_text(messages)

                    async for chunk in self._stream_chat(
                        session=current_session,
                        text_content=current_text,
                        file_ids=current_file_ids,
                        model_name=model,
                        chat_id=chat_id,
                        created_time=created_time,
                        account_manager=account_manager,
                        is_stream=stream,
                        request_id=request_id,
                        base_url=base_url,
                    ):
                        yield chunk

                    break  # Success

                except Exception as e:
                    qt = MODEL_TO_QUOTA_TYPE.get(model, "text")
                    account_manager.handle_error("chat request failed", request_id, qt)

                    if retry_idx < max_retries - 1:
                        logger.warning(
                            f"[GEMINI] [{account_manager.config.account_id}] [req_{request_id}] "
                            f"Switching account ({retry_idx + 1}/{max_retries})"
                        )
                        try:
                            new_account = await self._multi_account_mgr.get_account(
                                None, request_id, required_quota_types
                            )
                            new_sess = await create_google_session(
                                new_account, self._http_client, USER_AGENT, request_id
                            )
                            await self._multi_account_mgr.set_session_cache(
                                conv_key, new_account.config.account_id, new_sess
                            )
                            account_manager = new_account
                            current_retry_mode = True
                            current_file_ids = []
                        except Exception as switch_err:
                            logger.error(
                                f"[GEMINI] [req_{request_id}] Account switch failed: {switch_err}"
                            )
                            if stream:
                                yield f"data: {json.dumps({'error': {'message': 'Account Failover Failed'}})}\n\n"
                            return
                    else:
                        logger.error(
                            f"[GEMINI] [req_{request_id}] Max retries ({max_retries}) exceeded"
                        )
                        if stream:
                            yield f"data: {json.dumps({'error': {'message': str(e)[:200]}})}\n\n"
                        return

        if stream:
            return response_wrapper()

        # Non-streaming: collect all chunks
        full_content = ""
        full_reasoning = ""
        async for chunk_str in response_wrapper():
            if chunk_str.startswith("data: [DONE]"):
                break
            if chunk_str.startswith("data: "):
                try:
                    data = json.loads(chunk_str[6:])
                    delta = data.get("choices", [{}])[0].get("delta", {})
                    if "content" in delta:
                        full_content += delta["content"]
                    if "reasoning_content" in delta:
                        full_reasoning += delta["reasoning_content"]
                except (json.JSONDecodeError, KeyError, IndexError):
                    pass

        message_dict: Dict[str, Any] = {"role": "assistant", "content": full_content}
        if full_reasoning:
            message_dict["reasoning_content"] = full_reasoning

        return {
            "id": chat_id,
            "object": "chat.completion",
            "created": created_time,
            "model": model,
            "choices": [{"index": 0, "message": message_dict, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }

    async def _stream_chat(
        self,
        *,
        session: str,
        text_content: str,
        file_ids: List[str],
        model_name: str,
        chat_id: str,
        created_time: int,
        account_manager: AccountManager,
        is_stream: bool,
        request_id: str,
        base_url: str,
    ) -> AsyncIterator[str]:
        """Core streaming chat generator against Google Discovery Engine."""
        start_time = time.time()
        full_content = ""
        first_response = False

        jwt = await account_manager.get_jwt(request_id)
        headers = get_common_headers(jwt, USER_AGENT)

        tools_spec = _get_tools_spec(model_name)

        body: dict = {
            "configId": account_manager.config.config_id,
            "additionalParams": {"token": "-"},
            "streamAssistRequest": {
                "session": session,
                "query": {"parts": [{"text": text_content}]},
                "filter": "",
                "fileIds": file_ids,
                "answerGenerationMode": "NORMAL",
                "toolsSpec": tools_spec,
                "languageCode": "zh-CN",
                "userMetadata": {"timeZone": "Asia/Shanghai"},
                "assistSkippingMode": "REQUEST_ASSIST",
            },
        }

        target_model_id = MODEL_MAPPING.get(model_name)
        if target_model_id:
            body["streamAssistRequest"]["assistGenerationConfig"] = {
                "modelId": target_model_id
            }

        if is_stream:
            chunk = _create_chunk(chat_id, created_time, model_name, {"role": "assistant"}, None)
            yield f"data: {chunk}\n\n"

        json_objects: list = []
        file_ids_info = None

        async with self._http_client_chat.stream(
            "POST",
            "https://biz-discoveryengine.googleapis.com/v1alpha/locations/global/widgetStreamAssist",
            headers=headers,
            json=body,
        ) as r:
            if r.status_code != 200:
                error_text = await r.aread()
                raise httpx.HTTPStatusError(
                    f"Upstream error: {error_text.decode()[:200]}",
                    request=r.request,
                    response=r,
                )

            try:
                async for json_obj in parse_json_array_stream_async(r.aiter_lines()):
                    json_objects.append(json_obj)

                    stream_response = json_obj.get("streamAssistResponse", {})
                    answer = stream_response.get("answer", {})

                    # Check for skipped answers (content policy)
                    answer_state = answer.get("state", "")
                    if answer_state == "SKIPPED":
                        skip_reasons = answer.get("assistSkippedReasons", [])
                        if "CUSTOMER_POLICY_VIOLATION" in skip_reasons:
                            error_text = "\n⚠️ Content filtered by Google safety policy.\n"
                        else:
                            error_text = f"\n⚠️ Response skipped: {', '.join(skip_reasons)}\n"

                        first_response = True
                        full_content += error_text
                        chunk = _create_chunk(chat_id, created_time, model_name, {"content": error_text}, None)
                        yield f"data: {chunk}\n\n"
                        continue

                    replies = answer.get("replies", [])

                    for reply in replies:
                        content_obj = reply.get("groundedContent", {}).get("content", {})
                        text = content_obj.get("text", "")
                        if not text:
                            continue

                        if content_obj.get("thought"):
                            # Reasoning content (like OpenAI o1)
                            first_response = True
                            chunk = _create_chunk(
                                chat_id, created_time, model_name,
                                {"reasoning_content": text}, None
                            )
                            yield f"data: {chunk}\n\n"
                        else:
                            if not first_response:
                                first_response = True
                                account_manager.conversation_count += 1
                            full_content += text
                            chunk = _create_chunk(
                                chat_id, created_time, model_name,
                                {"content": text}, None
                            )
                            yield f"data: {chunk}\n\n"

                # Extract image info
                if json_objects:
                    fids, sess_name = _parse_images_from_response(json_objects)
                    if fids and sess_name:
                        file_ids_info = (fids, sess_name)

            except ValueError as e:
                logger.error(f"[GEMINI] [{account_manager.config.account_id}] [req_{request_id}] JSON parse error: {e}")
            except Exception as e:
                logger.error(f"[GEMINI] [{account_manager.config.account_id}] [req_{request_id}] Stream error: {e}")
                raise

        # Process downloaded images/videos
        if file_ids_info:
            fids_list, sess_name = file_ids_info
            try:
                file_metadata = await get_session_file_metadata(
                    account_manager, sess_name, self._http_client, USER_AGENT, request_id
                )

                tasks = []
                for fi in fids_list:
                    fid = fi["fileId"]
                    mime = fi["mimeType"]
                    meta = file_metadata.get(fid, {})
                    mime = meta.get("mimeType", mime)
                    correct_session = meta.get("session") or sess_name
                    task = download_image_with_jwt(
                        account_manager, correct_session, fid,
                        self._http_client, USER_AGENT, request_id
                    )
                    tasks.append((fid, mime, task))

                results = await asyncio.gather(*[t for _, _, t in tasks], return_exceptions=True)

                image_dir = str(settings.IMAGES_DIR)
                video_dir = str(settings.VIDEOS_DIR)

                for idx, ((fid, mime, _), result) in enumerate(zip(tasks, results), 1):
                    if isinstance(result, Exception):
                        error_msg = f"\n\n⚠️ Media {idx} download failed\n\n"
                        chunk = _create_chunk(chat_id, created_time, model_name, {"content": error_msg}, None)
                        yield f"data: {chunk}\n\n"
                        continue

                    try:
                        if mime.startswith("video/"):
                            url = save_media_file(result, chat_id, fid, mime, base_url, video_dir, "videos")
                            markdown = f'\n\n<video controls width="100%"><source src="{url}" type="{mime}"></video>\n\n'
                        else:
                            url = save_media_file(result, chat_id, fid, mime, base_url, image_dir, "images")
                            markdown = f"\n\n![Generated image]({url})\n\n"

                        chunk = _create_chunk(chat_id, created_time, model_name, {"content": markdown}, None)
                        yield f"data: {chunk}\n\n"
                    except Exception as e:
                        logger.error(f"[GEMINI] [req_{request_id}] Media {idx} save error: {e}")
                        error_msg = f"\n\n⚠️ Media {idx} processing failed\n\n"
                        chunk = _create_chunk(chat_id, created_time, model_name, {"content": error_msg}, None)
                        yield f"data: {chunk}\n\n"

            except Exception as e:
                logger.error(f"[GEMINI] [req_{request_id}] Image processing failed: {e}")

        total_time = time.time() - start_time
        logger.info(f"[GEMINI] [{account_manager.config.account_id}] [req_{request_id}] Done: {total_time:.2f}s")

        if is_stream:
            final_chunk = _create_chunk(chat_id, created_time, model_name, {}, "stop")
            yield f"data: {final_chunk}\n\n"
            yield "data: [DONE]\n\n"

    async def generate_image(
        self,
        *,
        prompt: str,
        model: str = "gemini-imagen",
        n: int = 1,
        aspect_ratio: str = "1:1",
        response_format: str = "url",
        base_url: str = "",
        request_id: str = "",
    ) -> Dict[str, Any]:
        """Generate images via Gemini chat (routes through chat_impl)."""
        if not request_id:
            request_id = str(uuid.uuid4())[:6]

        # Gemini tidak support aspect_ratio sebagai parameter API,
        # jadi kita sematkan instruksi rasio ke dalam prompt
        ASPECT_LABELS = {
            "1:1": "square (1:1)",
            "2:3": "portrait (2:3)",
            "3:2": "landscape (3:2)",
            "9:16": "tall portrait (9:16)",
            "16:9": "wide landscape (16:9)",
        }
        ratio_hint = ASPECT_LABELS.get(aspect_ratio, "")
        if ratio_hint:
            enhanced_prompt = f"{prompt}. Generate this image in {ratio_hint} aspect ratio."
        else:
            enhanced_prompt = prompt

        messages = [{"role": "user", "content": enhanced_prompt}]
        result = await self.chat(
            model=model,
            messages=messages,
            stream=False,
            request_id=request_id,
            base_url=base_url,
        )

        # Extract images from chat response
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

        # Parse markdown images
        b64_pattern = r"!\[.*?\]\(data:([^;]+);base64,([^\)]+)\)"
        b64_matches = re.findall(b64_pattern, content)
        url_pattern = r"!\[.*?\]\((https?://[^\)]+)\)"
        url_matches = re.findall(url_pattern, content)

        data_list = []
        if response_format == "b64_json":
            for mime, b64_data in b64_matches[:n]:
                data_list.append({"b64_json": b64_data, "revised_prompt": prompt})
            if not data_list and url_matches:
                for url in url_matches[:n]:
                    try:
                        resp = await self._http_client.get(url)
                        if resp.status_code == 200:
                            b64_data = base64.b64encode(resp.content).decode()
                            data_list.append({"b64_json": b64_data, "revised_prompt": prompt})
                    except Exception:
                        pass
        else:
            for url in url_matches[:n]:
                data_list.append({"url": url, "revised_prompt": prompt})
            if not data_list and b64_matches:
                chat_img_id = f"img-{uuid.uuid4()}"
                image_dir = str(settings.IMAGES_DIR)
                for idx, (mime, b64_data) in enumerate(b64_matches[:n], 1):
                    try:
                        img_data = base64.b64decode(b64_data)
                        fid = f"gen-{uuid.uuid4()}"
                        url = save_media_file(img_data, chat_img_id, fid, mime, base_url, image_dir, "images")
                        data_list.append({"url": url, "revised_prompt": prompt})
                    except Exception:
                        pass

        return {"created": int(time.time()), "data": data_list}

    async def generate_video(
        self,
        *,
        prompt: str,
        model: str = "gemini-veo",
        aspect_ratio: str = "16:9",
        duration_seconds: int = 6,
        resolution: str = "480p",
        preset: str = "normal",
        response_format: str = "url",
        base_url: str = "",
        request_id: str = "",
    ) -> Dict[str, Any]:
        """Generate video via Gemini veo model."""
        if not request_id:
            request_id = str(uuid.uuid4())[:6]

        messages = [{"role": "user", "content": prompt}]
        result = await self.chat(
            model=model,
            messages=messages,
            stream=False,
            request_id=request_id,
            base_url=base_url,
        )

        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

        # Extract video URLs
        url_pattern = r"(?:src=\"|!\[.*?\]\()(https?://[^\"\)]+)"
        url_matches = re.findall(url_pattern, content)

        data_list = []
        for url in url_matches[:1]:
            data_list.append({"url": url, "revised_prompt": prompt})

        return {"created": int(time.time()), "data": data_list}

    async def get_status(self) -> Dict[str, Any]:
        if not self._multi_account_mgr:
            return {"status": "not_initialized", "accounts": 0}

        total = len(self._multi_account_mgr.accounts)
        available = len(self._multi_account_mgr.get_available_accounts())
        cached_sessions = len(self._multi_account_mgr.global_session_cache)

        return {
            "status": "ok" if available > 0 else "no_accounts_available",
            "total_accounts": total,
            "available_accounts": available,
            "cached_sessions": cached_sessions,
            "models": self._all_model_ids(),
        }
