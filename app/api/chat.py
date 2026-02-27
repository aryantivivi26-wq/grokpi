"""Chat Completions API - Multi-backend LLM gateway (Grok + Gemini), compatible with OpenAI"""

import time
import json
import uuid
from typing import Optional, List, Dict, Any, Union
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.security import require_api_key
from app.core.logger import logger
from app.backends.router import backend_router


router = APIRouter()


# ============== Model Request/Response ==============

class ChatMessage(BaseModel):
    """Pesan chat"""
    role: str = Field(..., description="Peran: user/assistant/system")
    content: Union[str, List[Dict[str, Any]]] = Field(..., description="Konten pesan")


class ChatCompletionRequest(BaseModel):
    """Request OpenAI Chat Completion"""
    model: str = Field("grok-imagine", description="Nama model")
    messages: List[ChatMessage] = Field(..., description="Daftar pesan")
    stream: bool = Field(True, description="Apakah mengembalikan stream")
    max_tokens: Optional[int] = Field(4096, description="Jumlah token maksimal")
    temperature: Optional[float] = Field(1.0, description="Temperature")
    top_p: Optional[float] = Field(1.0, description="Top-p")
    n: Optional[int] = Field(4, description="Jumlah gambar yang dihasilkan (Grok)", ge=1, le=4)

    class Config:
        json_schema_extra = {
            "example": {
                "model": "grok-imagine",
                "messages": [{"role": "user", "content": "A cute cat"}],
                "stream": True
            }
        }


# ============== Fungsi Helper ==============


def extract_prompt(messages: List[ChatMessage]) -> str:
    """Ekstrak prompt pembuatan gambar dari daftar pesan"""
    for msg in reversed(messages):
        if msg.role == "user":
            content = msg.content
            if isinstance(content, str) and content.strip():
                return content.strip()
            elif isinstance(content, list):
                text = "".join(p.get("text", "") for p in content if p.get("type") == "text")
                if text.strip():
                    return text.strip()
    return ""


def _get_base_url(request: Request) -> str:
    """Get base URL from request (for media file URLs)."""
    from app.core.config import settings
    if settings.BASE_URL:
        return settings.BASE_URL.rstrip("/")
    forwarded_proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    forwarded_host = request.headers.get("x-forwarded-host", request.headers.get("host", "localhost"))
    return f"{forwarded_proto}://{forwarded_host}"


# ============== API Routes ==============

@router.post("/chat/completions")
async def chat_completions(
    request_data: ChatCompletionRequest,
    request: Request,
    _: bool = Depends(require_api_key),
):
    """
    Chat Completions API yang kompatibel dengan OpenAI

    Routes to the appropriate backend based on model name:
    - grok-* models -> Grok backend (image generation)
    - gemini-* models -> Gemini backend (chat, image, video)
    """
    model = request_data.model
    request_id = str(uuid.uuid4())[:6]

    # Find backend for this model
    backend = backend_router.get_backend(model)
    if backend is None:
        all_models = [m["id"] for m in backend_router.list_all_models()]
        raise HTTPException(
            status_code=404,
            detail=f"Model '{model}' not found. Available: {all_models}",
        )

    logger.info(f"[Chat] [{backend.name}] [req_{request_id}] model={model} stream={request_data.stream}")

    base_url = _get_base_url(request)
    messages = [m.model_dump() for m in request_data.messages]

    try:
        result = await backend.chat(
            model=model,
            messages=messages,
            stream=request_data.stream,
            temperature=request_data.temperature,
            top_p=request_data.top_p,
            request_id=request_id,
            base_url=base_url,
        )

        if request_data.stream:
            # result is an async generator
            return StreamingResponse(result, media_type="text/event-stream")

        # Non-streaming result is a dict
        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        err = str(e)
        if "rate_limit" in err.lower() or "429" in err:
            raise HTTPException(status_code=429, detail=err)
        if "unavailable" in err.lower() or "503" in err:
            raise HTTPException(status_code=503, detail=err)
        raise HTTPException(status_code=500, detail=err)
    except Exception as e:
        logger.error(f"[Chat] [req_{request_id}] Error: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models")
async def list_models():
    """Menampilkan daftar semua model yang tersedia dari semua backend"""
    return {
        "object": "list",
        "data": backend_router.list_all_models(),
    }
