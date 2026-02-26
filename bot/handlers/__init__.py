from .admin import router as admin_router
from .common import router as common_router
from .image import router as image_router
from .sso import router as sso_router
from .video import router as video_router


def get_routers():
    return [common_router, image_router, video_router, admin_router, sso_router]
