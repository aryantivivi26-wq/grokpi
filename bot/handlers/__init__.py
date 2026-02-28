from .admin import router as admin_router
from .admin_users import router as admin_users_router
from .common import router as common_router
from .gemini import router as gemini_router
from .image import router as image_router
from .leaderboard import router as leaderboard_router
from .payment import router as payment_router
from .referral import router as referral_router
from .sso import router as sso_router
from .subscription import router as subscription_router
from .topup import router as topup_router
from .video import router as video_router


def get_routers():
    return [
        common_router,
        image_router,
        video_router,
        subscription_router,
        payment_router,
        topup_router,
        leaderboard_router,
        referral_router,
        admin_router,
        admin_users_router,
        sso_router,
        gemini_router,
    ]
