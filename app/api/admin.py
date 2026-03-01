"""Admin API Routes"""

import asyncio
import json
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.core.config import settings
from app.core.logger import logger
from app.core.security import require_api_key
from app.services.cf_solver import cf_solver

# Pilih SSO manager berdasarkan konfigurasi
if settings.REDIS_ENABLED:
    from app.services.redis_sso_manager import create_sso_manager
    sso_manager = create_sso_manager(
        use_redis=True,
        redis_url=settings.REDIS_URL,
        strategy=settings.SSO_ROTATION_STRATEGY,
        daily_limit=settings.SSO_DAILY_LIMIT
    )
else:
    from app.services.sso_manager import sso_manager

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.get("/status")
async def get_status():
    """Mendapatkan status service"""
    # Versi Redis bersifat asinkron
    if hasattr(sso_manager, 'get_status') and asyncio.iscoroutinefunction(sso_manager.get_status):
        sso_status = await sso_manager.get_status()
    else:
        sso_status = sso_manager.get_status()

    # Membangun informasi konfigurasi proxy
    proxy_config = {
        "proxy_url": settings.PROXY_URL,
        "http_proxy": settings.HTTP_PROXY,
        "https_proxy": settings.HTTPS_PROXY
    }
    # Filter nilai None
    proxy_config = {k: v for k, v in proxy_config.items() if v}

    return {
        "service": "running",
        "sso": sso_status,
        "cf_solver": cf_solver.get_status(),
        "proxy": proxy_config if proxy_config else "none",
        "config": {
            "host": settings.HOST,
            "port": settings.PORT,
            "images_dir": str(settings.IMAGES_DIR),
            "videos_dir": str(settings.VIDEOS_DIR),
            "base_url": settings.get_base_url(),
            "sso_file": str(settings.SSO_FILE),
            "redis_enabled": settings.REDIS_ENABLED,
            "rotation_strategy": settings.SSO_ROTATION_STRATEGY,
            "daily_limit": settings.SSO_DAILY_LIMIT
        }
    }


@router.post("/sso/reload")
async def reload_sso():
    """Muat ulang daftar SSO"""
    count = await sso_manager.reload()
    logger.info(f"[Admin] Muat ulang SSO: {count} keys")
    return {
        "success": True,
        "count": count
    }


@router.post("/sso/reset-usage")
async def reset_sso_usage():
    """Reset manual jumlah penggunaan harian (hanya mode Redis)"""
    if hasattr(sso_manager, 'reset_daily_usage'):
        await sso_manager.reset_daily_usage()
        logger.info("[Admin] Reset manual jumlah penggunaan harian")
        return {"success": True, "message": "Jumlah penggunaan harian telah direset"}
    return {"success": False, "message": "Fitur ini hanya tersedia dalam mode Redis"}


@router.post("/cf/refresh")
async def refresh_cf_clearance():
    """Refresh cf_clearance secara manual via FlareSolverr"""
    success = await cf_solver.refresh_once()
    return {
        "success": success,
        "cf_clearance_set": bool(settings.CF_CLEARANCE),
        "cf_clearance_prefix": settings.CF_CLEARANCE[:20] + "..." if settings.CF_CLEARANCE else "",
    }


@router.get("/images/list")
async def list_images(limit: int = 50):
    """Menampilkan daftar gambar yang di-cache"""
    images = []
    if settings.IMAGES_DIR.exists():
        files = sorted(settings.IMAGES_DIR.glob("*"), key=lambda x: x.stat().st_mtime, reverse=True)
        for f in files:
            if f.suffix.lower() not in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
                continue
            images.append({
                "filename": f.name,
                "url": f"{settings.get_base_url()}/images/{f.name}",
                "size": f.stat().st_size
            })
            if len(images) >= limit:
                break
    return {"images": images, "count": len(images)}


@router.get("/videos/list")
async def list_videos(limit: int = 50):
    """Menampilkan daftar video yang di-cache"""
    videos = []
    if settings.VIDEOS_DIR.exists():
        files = sorted(settings.VIDEOS_DIR.glob("*"), key=lambda x: x.stat().st_mtime, reverse=True)
        for f in files:
            if f.suffix.lower() not in {".mp4", ".webm", ".mov", ".mkv"}:
                continue
            videos.append({
                "filename": f.name,
                "url": f"{settings.get_base_url()}/videos/{f.name}",
                "size": f.stat().st_size
            })
            if len(videos) >= limit:
                break
    return {"videos": videos, "count": len(videos)}


@router.delete("/images/clear")
async def clear_images():
    """Menghapus cache gambar"""
    count = 0
    if settings.IMAGES_DIR.exists():
        for f in settings.IMAGES_DIR.glob("*"):
            if f.is_file():
                f.unlink()
                count += 1

    logger.info(f"[Admin] Telah menghapus {count} gambar")
    return {"success": True, "deleted": count}


@router.delete("/videos/clear")
async def clear_videos():
    """Menghapus cache video"""
    count = 0
    if settings.VIDEOS_DIR.exists():
        for f in settings.VIDEOS_DIR.glob("*"):
            if f.is_file():
                f.unlink()
                count += 1

    logger.info(f"[Admin] Telah menghapus {count} video")
    return {"success": True, "deleted": count}


@router.delete("/media/image/{filename}")
async def delete_image(filename: str):
    """Hapus satu file gambar"""
    safe_name = Path(filename).name
    target = settings.IMAGES_DIR / safe_name

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File gambar tidak ditemukan")

    target.unlink()
    logger.info(f"[Admin] Hapus gambar: {safe_name}")
    return {"success": True, "deleted": safe_name}


@router.delete("/media/video/{filename}")
async def delete_video(filename: str):
    """Hapus satu file video"""
    safe_name = Path(filename).name
    target = settings.VIDEOS_DIR / safe_name

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File video tidak ditemukan")

    target.unlink()
    logger.info(f"[Admin] Hapus video: {safe_name}")
    return {"success": True, "deleted": safe_name}


class GeminiReloadRequest(BaseModel):
    accounts_config: Optional[str] = None


@router.post("/gemini/reload")
async def reload_gemini(body: GeminiReloadRequest = GeminiReloadRequest()):
    """Reload Gemini backend with new accounts config."""
    from app.backends.router import backend_router

    gemini = backend_router.get_backend_by_name("gemini")
    if gemini is None:
        raise HTTPException(status_code=404, detail="Gemini backend not registered")

    # If new config is provided, update the env/settings
    new_config = body.accounts_config
    if new_config:
        try:
            # Validate JSON
            parsed = json.loads(new_config)
            if not isinstance(parsed, list):
                raise ValueError("Expected JSON array")
            settings.GEMINI_ACCOUNTS_CONFIG = new_config
            import os
            os.environ["GEMINI_ACCOUNTS_CONFIG"] = new_config
        except (json.JSONDecodeError, ValueError) as e:
            raise HTTPException(status_code=400, detail=f"Invalid accounts_config JSON: {e}")

    # Re-initialize the Gemini backend
    try:
        await gemini.shutdown()
        await gemini.initialize()
        account_count = len(gemini._multi_account_mgr.accounts) if gemini._multi_account_mgr else 0
        logger.info(f"[Admin] Gemini reloaded with {account_count} accounts")
        return {"success": True, "accounts": account_count}
    except Exception as e:
        logger.error(f"[Admin] Gemini reload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Gemini reload failed: {e}")


@router.get("/gemini/health")
async def gemini_health():
    """Health check for all Gemini accounts. Tests JWT auth for each."""
    from app.backends.router import backend_router

    gemini = backend_router.get_backend_by_name("gemini")
    if gemini is None:
        raise HTTPException(status_code=404, detail="Gemini backend not registered")

    mgr = gemini._multi_account_mgr
    if not mgr:
        return {"accounts": []}

    results = []
    for acc_id, account in mgr.accounts.items():
        entry = {
            "id": acc_id,
            "status": "unknown",
            "disabled": account.config.disabled,
            "expired": account.config.is_expired(),
        }

        if account.config.disabled:
            entry["status"] = "disabled"
            results.append(entry)
            continue

        if account.config.is_expired():
            entry["status"] = "expired"
            results.append(entry)
            continue

        # Try getting JWT to test if cookies are still valid
        try:
            await account.get_jwt(request_id="health")
            entry["status"] = "active"
        except Exception as e:
            entry["status"] = "dead"
            entry["error"] = str(e)[:100]

        results.append(entry)

    return {"accounts": results}
