from .config import settings


def is_admin(user_id: int) -> bool:
    admins = settings.admin_ids
    if not admins:
        return True
    return user_id in admins
