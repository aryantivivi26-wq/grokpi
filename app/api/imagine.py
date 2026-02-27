"""Imagine API Routes - Format kompatibel OpenAI, mendukung preview streaming"""

import time
import json
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.security import require_api_key
from app.core.logger import logger
from app.backends.router import backend_router


router = APIRouter()


# ============== Model Request/Response ==============

class OpenAIImageRequest(BaseModel):
    """Request pembuatan gambar yang kompatibel dengan OpenAI"""
    prompt: str = Field(..., description="Prompt deskripsi gambar", min_length=1)
    model: Optional[str] = Field("grok-2-image", description="Nama model")
    n: Optional[int] = Field(None, description="Jumlah yang dihasilkan, jika tidak ditentukan gunakan konfigurasi default", ge=1, le=4)
    size: Optional[str] = Field("1024x1536", description="Ukuran gambar")
    aspect_ratio: Optional[str] = Field(None, description="Rasio aspek langsung (1:1, 2:3, 3:2, 9:16, 16:9)")
    response_format: Optional[str] = Field("url", description="Format response: url atau b64_json")
    stream: Optional[bool] = Field(False, description="Apakah mengembalikan progress secara streaming")

    class Config:
        json_schema_extra = {
            "example": {
                "prompt": "a beautiful sunset over the ocean",
                "n": 2,
                "size": "1024x1536"
            }
        }


class OpenAIImageData(BaseModel):
    """Data gambar dengan format OpenAI"""
    url: Optional[str] = None
    b64_json: Optional[str] = None


class OpenAIImageResponse(BaseModel):
    """Response gambar yang kompatibel dengan OpenAI"""
    created: int
    data: List[OpenAIImageData]


class OpenAIVideoRequest(BaseModel):
    """Request pembuatan video (eksperimental)"""
    prompt: str = Field(..., description="Prompt deskripsi video", min_length=1)
    model: Optional[str] = Field("grok-2-video", description="Nama model")
    size: Optional[str] = Field("1792x1024", description="Ukuran video")
    aspect_ratio: Optional[str] = Field(None, description="Rasio aspek langsung (1:1, 2:3, 3:2, 9:16, 16:9)")
    duration_seconds: Optional[int] = Field(6, description="Durasi video (6 atau 10 detik)")
    resolution: Optional[str] = Field("480p", description="Resolusi video (480p atau 720p)")
    preset: Optional[str] = Field("normal", description="Preset video (fun, normal, spicy, custom)")
    response_format: Optional[str] = Field("url", description="Format response: url atau b64_json")


class OpenAIVideoData(BaseModel):
    """Data video"""
    url: Optional[str] = None
    b64_json: Optional[str] = None


class OpenAIVideoResponse(BaseModel):
    """Response video"""
    created: int
    data: List[OpenAIVideoData]


# ============== Fungsi Helper ==============


def size_to_aspect_ratio(size: str) -> str:
    """Konversi size OpenAI ke aspect_ratio"""
    size_map = {
        "1024x1024": "1:1",
        "1024x1536": "2:3",
        "1536x1024": "3:2",
        "1024x1792": "9:16",
        "1792x1024": "16:9",
        "512x512": "1:1",
        "256x256": "1:1",
    }
    return size_map.get(size, "2:3")


ALLOWED_ASPECT_RATIOS = {"1:1", "2:3", "3:2", "9:16", "16:9"}


def resolve_aspect_ratio(request: OpenAIImageRequest) -> str:
    """Menentukan aspect ratio final dari request"""
    if request.aspect_ratio:
        if request.aspect_ratio not in ALLOWED_ASPECT_RATIOS:
            raise HTTPException(
                status_code=400,
                detail="Invalid aspect_ratio. Gunakan salah satu: 1:1, 2:3, 3:2, 9:16, 16:9"
            )
        return request.aspect_ratio

    return size_to_aspect_ratio(request.size)


def resolve_video_aspect_ratio(request: OpenAIVideoRequest) -> str:
    """Menentukan aspect ratio final untuk request video"""
    if request.aspect_ratio:
        if request.aspect_ratio not in ALLOWED_ASPECT_RATIOS:
            raise HTTPException(
                status_code=400,
                detail="Invalid aspect_ratio. Gunakan salah satu: 1:1, 2:3, 3:2, 9:16, 16:9"
            )
        return request.aspect_ratio

    return size_to_aspect_ratio(request.size)


def validate_video_options(request: OpenAIVideoRequest):
    """Validasi opsi video berdasarkan opsi UI Grok saat ini"""
    if request.duration_seconds not in [6, 10]:
        raise HTTPException(status_code=400, detail="Invalid duration_seconds. Gunakan 6 atau 10")

    if request.resolution not in ["480p", "720p"]:
        raise HTTPException(status_code=400, detail="Invalid resolution. Gunakan 480p atau 720p")

    if request.preset not in ["fun", "normal", "spicy", "custom"]:
        raise HTTPException(status_code=400, detail="Invalid preset. Gunakan fun, normal, spicy, atau custom")


# ============== API Routes ==============

@router.post("/images/generations", response_model=OpenAIImageResponse)
async def generate_image(
    request: OpenAIImageRequest,
    fastapi_request: Request,
    _: bool = Depends(require_api_key)
):
    """
    Generate gambar (API kompatibel OpenAI)

    Routes to appropriate backend based on model name:
    - grok-* models -> Grok backend
    - gemini-* models -> Gemini backend
    """
    model = request.model or "grok-2-image"
    logger.info(f"[Imagine] Request generate: {request.prompt[:50]}... model={model} stream={request.stream}")

    aspect_ratio = resolve_aspect_ratio(request)

    backend = backend_router.get_backend(model)
    if backend is None:
        raise HTTPException(
            status_code=404,
            detail=f"Model '{model}' not found for image generation.",
        )

    # Get base_url for media file URLs
    from app.core.config import settings
    if settings.BASE_URL:
        base_url = settings.BASE_URL.rstrip("/")
    else:
        forwarded_proto = fastapi_request.headers.get("x-forwarded-proto", fastapi_request.url.scheme)
        forwarded_host = fastapi_request.headers.get("x-forwarded-host", fastapi_request.headers.get("host", "localhost"))
        base_url = f"{forwarded_proto}://{forwarded_host}"

    # Mode streaming (Grok only)
    if request.stream and backend.name == "grok":
        return StreamingResponse(
            stream_generate(
                prompt=request.prompt,
                aspect_ratio=aspect_ratio,
                n=request.n
            ),
            media_type="text/event-stream"
        )

    try:
        result = await backend.generate_image(
            prompt=request.prompt,
            model=model,
            n=request.n,
            aspect_ratio=aspect_ratio,
            response_format=request.response_format,
            base_url=base_url,
        )

        # Backend returns {"created": ..., "data": [{"url": ...}]} on success
        # or raises RuntimeError on failure
        result_data = result.get("data", [])
        data = []
        for item in result_data:
            if item.get("b64_json"):
                data.append(OpenAIImageData(b64_json=item["b64_json"]))
            elif item.get("url"):
                data.append(OpenAIImageData(url=item["url"]))

        if not data:
            raise HTTPException(status_code=500, detail="No images generated")

        return OpenAIImageResponse(created=result.get("created", int(time.time())), data=data)

    except HTTPException:
        raise
    except RuntimeError as e:
        err = str(e)
        if "rate_limit" in err.lower() or "429" in err:
            raise HTTPException(status_code=429, detail=err)
        raise HTTPException(status_code=500, detail=err)
    except Exception as e:
        logger.error(f"[Imagine] Error: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def stream_generate(prompt: str, aspect_ratio: str, n: int):
    """
    Generate gambar secara streaming (Grok backend only)
    """
    from app.services.grok_client import grok_client
    try:
        async for item in grok_client.generate_stream(
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            n=n,
            enable_nsfw=True
        ):
            if item.get("type") == "progress":
                # Update progress
                event_data = {
                    "image_id": item["image_id"],
                    "stage": item["stage"],
                    "is_final": item["is_final"],
                    "completed": item["completed"],
                    "total": item["total"],
                    "progress": f"{item['completed']}/{item['total']}"
                }
                yield f"event: progress\ndata: {json.dumps(event_data)}\n\n"

            elif item.get("type") == "result":
                # Hasil akhir
                if item.get("success"):
                    result_data = {
                        "created": int(time.time()),
                        "data": [{"url": url} for url in item.get("urls", [])]
                    }
                    yield f"event: complete\ndata: {json.dumps(result_data)}\n\n"
                else:
                    error_data = {"error": item.get("error", "Generation failed")}
                    yield f"event: error\ndata: {json.dumps(error_data)}\n\n"
                break

    except Exception as e:
        logger.error(f"[API] Error generate streaming: {e}")
        yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"


@router.get("/models/imagine")
async def list_imagine_models():
    """Menampilkan daftar model pembuatan gambar/video dari semua backend"""
    all_models = backend_router.list_all_models()
    image_video_models = [
        m for m in all_models
        if "image" in m["id"] or "imagine" in m["id"] or "video" in m["id"]
        or "imagen" in m["id"] or "veo" in m["id"]
    ]
    return {
        "object": "list",
        "data": image_video_models
    }


@router.post("/videos/generations", response_model=OpenAIVideoResponse)
async def generate_video(
    request: OpenAIVideoRequest,
    fastapi_request: Request,
    _: bool = Depends(require_api_key)
):
    """Generate video - routes to appropriate backend"""
    model = request.model or "grok-2-video"
    logger.info(f"[Video] Request: {request.prompt[:50]}... model={model}")

    validate_video_options(request)
    aspect_ratio = resolve_video_aspect_ratio(request)

    backend = backend_router.get_backend(model)
    if backend is None:
        raise HTTPException(
            status_code=404,
            detail=f"Model '{model}' not found for video generation.",
        )

    # Get base_url
    from app.core.config import settings
    if settings.BASE_URL:
        base_url = settings.BASE_URL.rstrip("/")
    else:
        forwarded_proto = fastapi_request.headers.get("x-forwarded-proto", fastapi_request.url.scheme)
        forwarded_host = fastapi_request.headers.get("x-forwarded-host", fastapi_request.headers.get("host", "localhost"))
        base_url = f"{forwarded_proto}://{forwarded_host}"

    try:
        result = await backend.generate_video(
            prompt=request.prompt,
            model=model,
            aspect_ratio=aspect_ratio,
            duration_seconds=request.duration_seconds,
            resolution=request.resolution,
            preset=request.preset,
            response_format=request.response_format,
            base_url=base_url,
        )

        # Backend returns {"created": ..., "data": [{"url": ...}]} on success
        result_data = result.get("data", [])
        data = []
        for item in result_data:
            if item.get("b64_json"):
                data.append(OpenAIVideoData(b64_json=item["b64_json"]))
            elif item.get("url"):
                data.append(OpenAIVideoData(url=item["url"]))

        if not data:
            raise HTTPException(status_code=500, detail="No video generated")

        return OpenAIVideoResponse(created=result.get("created", int(time.time())), data=data)

    except HTTPException:
        raise
    except RuntimeError as e:
        err = str(e)
        if "rate_limit" in err.lower() or "429" in err:
            raise HTTPException(status_code=429, detail=err)
        if "video_not_supported" in err.lower():
            raise HTTPException(status_code=501, detail=err)
        raise HTTPException(status_code=500, detail=err)
    except Exception as e:
        logger.error(f"[Video] Error: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
