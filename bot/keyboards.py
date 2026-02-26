from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🖼 Generate Image", callback_data="menu:image")],
            [InlineKeyboardButton(text="🎬 Generate Video", callback_data="menu:video")],
            [InlineKeyboardButton(text="📈 My Limit", callback_data="menu:limit")],
            [InlineKeyboardButton(text="🛠 Admin Panel", callback_data="menu:admin")],
            [InlineKeyboardButton(text="🔐 SSO Manager", callback_data="menu:sso")],
            [InlineKeyboardButton(text="📊 Quick Status", callback_data="menu:status")],
            [InlineKeyboardButton(text="🧹 Clean", callback_data="menu:clean")],
        ]
    )


def image_menu_keyboard(selected_aspect: str, selected_n: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Aspect Ratio", callback_data="noop")],
            [
                InlineKeyboardButton(text=f"{'✅ ' if selected_aspect == '1:1' else ''}1:1", callback_data="img:aspect:1:1"),
                InlineKeyboardButton(text=f"{'✅ ' if selected_aspect == '2:3' else ''}2:3", callback_data="img:aspect:2:3"),
                InlineKeyboardButton(text=f"{'✅ ' if selected_aspect == '3:2' else ''}3:2", callback_data="img:aspect:3:2"),
            ],
            [
                InlineKeyboardButton(text=f"{'✅ ' if selected_aspect == '9:16' else ''}9:16", callback_data="img:aspect:9:16"),
                InlineKeyboardButton(text=f"{'✅ ' if selected_aspect == '16:9' else ''}16:9", callback_data="img:aspect:16:9"),
            ],
            [InlineKeyboardButton(text="Jumlah Gambar", callback_data="noop")],
            [
                InlineKeyboardButton(text=f"{'✅ ' if selected_n == 1 else ''}1", callback_data="img:n:1"),
                InlineKeyboardButton(text=f"{'✅ ' if selected_n == 2 else ''}2", callback_data="img:n:2"),
                InlineKeyboardButton(text=f"{'✅ ' if selected_n == 3 else ''}3", callback_data="img:n:3"),
                InlineKeyboardButton(text=f"{'✅ ' if selected_n == 4 else ''}4", callback_data="img:n:4"),
            ],
            [InlineKeyboardButton(text="✍️ Enter Prompt", callback_data="img:prompt")],
            [InlineKeyboardButton(text="🧹 Clean", callback_data="menu:clean")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="menu:home")],
        ]
    )


def video_menu_keyboard(aspect: str, duration: int, resolution: str, preset: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Aspect Ratio", callback_data="noop")],
            [
                InlineKeyboardButton(text=f"{'✅ ' if aspect == '9:16' else ''}9:16", callback_data="vid:aspect:9:16"),
                InlineKeyboardButton(text=f"{'✅ ' if aspect == '16:9' else ''}16:9", callback_data="vid:aspect:16:9"),
                InlineKeyboardButton(text=f"{'✅ ' if aspect == '1:1' else ''}1:1", callback_data="vid:aspect:1:1"),
            ],
            [InlineKeyboardButton(text="Duration", callback_data="noop")],
            [
                InlineKeyboardButton(text=f"{'✅ ' if duration == 6 else ''}6s", callback_data="vid:duration:6"),
                InlineKeyboardButton(text=f"{'✅ ' if duration == 10 else ''}10s", callback_data="vid:duration:10"),
            ],
            [InlineKeyboardButton(text="Resolution", callback_data="noop")],
            [
                InlineKeyboardButton(text=f"{'✅ ' if resolution == '480p' else ''}480p", callback_data="vid:resolution:480p"),
                InlineKeyboardButton(text=f"{'✅ ' if resolution == '720p' else ''}720p", callback_data="vid:resolution:720p"),
            ],
            [InlineKeyboardButton(text="Preset", callback_data="noop")],
            [
                InlineKeyboardButton(text=f"{'✅ ' if preset == 'normal' else ''}Normal", callback_data="vid:preset:normal"),
                InlineKeyboardButton(text=f"{'✅ ' if preset == 'fun' else ''}Fun", callback_data="vid:preset:fun"),
            ],
            [
                InlineKeyboardButton(text=f"{'✅ ' if preset == 'spicy' else ''}Spicy", callback_data="vid:preset:spicy"),
                InlineKeyboardButton(text=f"{'✅ ' if preset == 'custom' else ''}Custom", callback_data="vid:preset:custom"),
            ],
            [InlineKeyboardButton(text="✍️ Enter Prompt", callback_data="vid:prompt")],
            [InlineKeyboardButton(text="🧹 Clean", callback_data="menu:clean")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="menu:home")],
        ]
    )


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Service Status", callback_data="admin:status")],
            [InlineKeyboardButton(text="➕ Add SSO Key", callback_data="admin:add_key")],
            [InlineKeyboardButton(text="🔄 Reload SSO", callback_data="admin:reload_sso")],
            [InlineKeyboardButton(text="🖼 Manage Images", callback_data="admin:images")],
            [InlineKeyboardButton(text="🎬 Manage Videos", callback_data="admin:videos")],
            [InlineKeyboardButton(text="🧹 Clean", callback_data="menu:clean")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="menu:home")],
        ]
    )


def media_list_keyboard(media_type: str, items_count: int) -> InlineKeyboardMarkup:
    rows = []
    for idx in range(items_count):
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🗑 Delete #{idx + 1}",
                    callback_data=f"admin:delete:{media_type}:{idx}",
                )
            ]
        )

    rows.append([InlineKeyboardButton(text="🔄 Refresh", callback_data=f"admin:{media_type}")])
    rows.append([InlineKeyboardButton(text="⬅️ Back Admin", callback_data="menu:admin")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def media_page_keyboard(media_type: str, start: int, end: int, total: int) -> InlineKeyboardMarkup:
    rows = []
    for idx in range(start, end):
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🗑 Delete #{idx + 1}",
                    callback_data=f"admin:deleteask:{media_type}:{idx}",
                )
            ]
        )

    nav = []
    if start > 0:
        prev_start = max(0, start - (end - start))
        nav.append(InlineKeyboardButton(text="◀️ Prev", callback_data=f"admin:page:{media_type}:{prev_start}"))
    if end < total:
        nav.append(InlineKeyboardButton(text="Next ▶️", callback_data=f"admin:page:{media_type}:{end}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton(text="🔄 Refresh", callback_data=f"admin:{media_type}")])
    rows.append([InlineKeyboardButton(text="🧹 Clean", callback_data="menu:clean")])
    rows.append([InlineKeyboardButton(text="⬅️ Back Admin", callback_data="menu:admin")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def delete_confirm_keyboard(media_type: str, idx: int, back_start: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Yes, Delete", callback_data=f"admin:deleteok:{media_type}:{idx}"),
                InlineKeyboardButton(text="❌ Cancel", callback_data=f"admin:page:{media_type}:{back_start}"),
            ]
        ]
    )


def sso_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Add SSO Key", callback_data="sso:add")],
            [InlineKeyboardButton(text="📋 List Key Summary", callback_data="sso:list")],
            [InlineKeyboardButton(text="➖ Remove Last Key", callback_data="sso:remove_last")],
            [InlineKeyboardButton(text="🔄 Reload SSO to Gateway", callback_data="sso:reload")],
            [InlineKeyboardButton(text="🧹 Clean", callback_data="menu:clean")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="menu:home")],
        ]
    )


def sso_add_input_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancel", callback_data="sso:add:cancel")],
        ]
    )
