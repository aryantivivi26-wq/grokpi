from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🖼 Image", callback_data="menu:image"),
                InlineKeyboardButton(text="🎬 Video", callback_data="menu:video"),
            ],
            [
                InlineKeyboardButton(text="💎 Subscription", callback_data="menu:subs"),
                InlineKeyboardButton(text="📈 My Limit", callback_data="menu:limit"),
            ],
            [
                InlineKeyboardButton(text="📦 Topup Kuota", callback_data="menu:topup"),
                InlineKeyboardButton(text="🏆 Leaderboard", callback_data="menu:leaderboard"),
            ],
            [
                InlineKeyboardButton(text="🔗 Referral", callback_data="menu:referral"),
                InlineKeyboardButton(text="🧹 Clean Chat", callback_data="menu:clean"),
            ],
        ]
    )


def referral_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Refresh", callback_data="menu:referral")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="menu:home")],
        ]
    )


def image_menu_keyboard(selected_aspect: str, selected_n: int, max_n: int = 4, max_batch: int = 1) -> InlineKeyboardMarkup:
    n_buttons = []
    for i in range(1, max_n + 1):
        n_buttons.append(
            InlineKeyboardButton(
                text=f"{'✅ ' if selected_n == i else ''}{i}",
                callback_data=f"img:n:{i}",
            )
        )

    rows = [
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
        n_buttons,
        [InlineKeyboardButton(text="✍️ Enter Prompt", callback_data="img:prompt")],
    ]

    if max_batch > 1:
        rows.append(
            [InlineKeyboardButton(text=f"📝 Batch Prompt (max {max_batch})", callback_data="img:batch")]
        )

    rows.append([InlineKeyboardButton(text="🧹 Clean", callback_data="menu:clean")])
    rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data="menu:home")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


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
            [
                InlineKeyboardButton(text="👥 Users", callback_data="adm:users"),
                InlineKeyboardButton(text="💎 Subscribers", callback_data="adm:subs"),
            ],
            [
                InlineKeyboardButton(text="📢 Broadcast", callback_data="adm:broadcast"),
                InlineKeyboardButton(text="📊 Bot Stats", callback_data="adm:stats"),
            ],
            [
                InlineKeyboardButton(text="🖼 Images", callback_data="admin:images"),
                InlineKeyboardButton(text="🎬 Videos", callback_data="admin:videos"),
            ],
            [
                InlineKeyboardButton(text="📡 Gateway", callback_data="admin:status"),
                InlineKeyboardButton(text="🔄 Reload SSO", callback_data="admin:reload_sso"),
            ],
            [InlineKeyboardButton(text="➕ Add SSO Key", callback_data="admin:add_key")],
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


# ---------------------------------------------------------------------------
# Subscription keyboards
# ---------------------------------------------------------------------------

def subscription_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 My Subscription", callback_data="subs:info")],
            [InlineKeyboardButton(text="📊 Tier Comparison", callback_data="subs:tiers")],
            [InlineKeyboardButton(text="🛒 Beli Subscription", callback_data="pay:buy")],
            [InlineKeyboardButton(text="📜 Riwayat Pembayaran", callback_data="pay:history")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="menu:home")],
        ]
    )


def subscription_admin_keyboard() -> InlineKeyboardMarkup:
    """Extra admin buttons for subscription management."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 My Subscription", callback_data="subs:info")],
            [InlineKeyboardButton(text="📊 Tier Comparison", callback_data="subs:tiers")],
            [InlineKeyboardButton(text="🛒 Beli Subscription", callback_data="pay:buy")],
            [InlineKeyboardButton(text="📜 Riwayat Pembayaran", callback_data="pay:history")],
            [InlineKeyboardButton(text="➕ Grant Sub (admin)", callback_data="subs:grant")],
            [InlineKeyboardButton(text="🗑 Revoke Sub (admin)", callback_data="subs:revoke")],
            [InlineKeyboardButton(text="📃 Active Subs (admin)", callback_data="subs:list")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="menu:home")],
        ]
    )


def grant_tier_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⭐ Basic", callback_data="subs:grant:basic"),
                InlineKeyboardButton(text="💎 Premium", callback_data="subs:grant:premium"),
            ],
            [InlineKeyboardButton(text="❌ Cancel", callback_data="menu:subs")],
        ]
    )


def grant_duration_keyboard(tier: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📅 1 Hari", callback_data=f"subs:dur:{tier}:daily")],
            [InlineKeyboardButton(text="📅 7 Hari", callback_data=f"subs:dur:{tier}:weekly")],
            [InlineKeyboardButton(text="📅 30 Hari", callback_data=f"subs:dur:{tier}:monthly")],
            [InlineKeyboardButton(text="❌ Cancel", callback_data="menu:subs")],
        ]
    )


# ---------------------------------------------------------------------------
# Payment keyboards
# ---------------------------------------------------------------------------

def pay_tier_keyboard() -> InlineKeyboardMarkup:
    """Choose which tier to buy."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⭐ Basic", callback_data="pay:tier:basic")],
            [InlineKeyboardButton(text="💎 Premium", callback_data="pay:tier:premium")],
            [InlineKeyboardButton(text="❌ Batal", callback_data="menu:subs")],
        ]
    )


def pay_duration_keyboard(tier: str, prices: dict) -> InlineKeyboardMarkup:
    """Choose duration+see price."""
    rows = []
    for dur_key, label in [("daily", "1 Hari"), ("weekly", "7 Hari"), ("monthly", "30 Hari")]:
        price = prices.get(f"{tier}_{dur_key}", 0)
        rows.append([
            InlineKeyboardButton(
                text=f"📅 {label} — Rp {price:,}".replace(",", "."),
                callback_data=f"pay:dur:{tier}:{dur_key}",
            )
        ])
    rows.append([InlineKeyboardButton(text="⬅️ Kembali", callback_data="pay:buy")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def pay_confirm_keyboard(tier: str, duration: str, amount: int) -> InlineKeyboardMarkup:
    """Confirm before creating QRIS."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=f"✅ Bayar Rp {amount:,}".replace(",", "."),
                callback_data=f"pay:confirm:{tier}:{duration}",
            )],
            [InlineKeyboardButton(text="❌ Batal", callback_data="pay:buy")],
        ]
    )


def pay_waiting_keyboard(transaction_id: str) -> InlineKeyboardMarkup:
    """Shown while waiting for payment — manual check + cancel."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Cek Status Pembayaran", callback_data=f"pay:check:{transaction_id}")],
            [InlineKeyboardButton(text="❌ Batalkan", callback_data=f"pay:cancel:{transaction_id}")],
        ]
    )


def pay_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Kembali", callback_data="menu:subs")],
        ]
    )


# ---------------------------------------------------------------------------
# Admin user management keyboards
# ---------------------------------------------------------------------------

def admin_users_keyboard(page: int, total_pages: int) -> InlineKeyboardMarkup:
    """Paginated user list keyboard."""
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️ Prev", callback_data=f"adm:users:p:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="Next ▶️", callback_data=f"adm:users:p:{page + 1}"))

    rows = []
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="🔍 Cari User (ID)", callback_data="adm:user:search")])
    rows.append([InlineKeyboardButton(text="⬅️ Back Admin", callback_data="menu:admin")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_user_detail_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Actions for a specific user."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➕ Assign Sub", callback_data=f"adm:usub:grant:{user_id}"),
                InlineKeyboardButton(text="🗑 Revoke Sub", callback_data=f"adm:usub:revoke:{user_id}"),
            ],
            [InlineKeyboardButton(text="🗑 Hapus User", callback_data=f"adm:user:del:{user_id}")],
            [InlineKeyboardButton(text="⬅️ Back Users", callback_data="adm:users")],
        ]
    )


def admin_user_del_confirm_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Ya, Hapus", callback_data=f"adm:user:delok:{user_id}"),
                InlineKeyboardButton(text="❌ Batal", callback_data=f"adm:user:view:{user_id}"),
            ],
        ]
    )


def broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Kirim", callback_data="adm:bc:send"),
                InlineKeyboardButton(text="❌ Batal", callback_data="menu:admin"),
            ],
        ]
    )


def admin_assign_tier_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⭐ Basic", callback_data=f"adm:usub:t:{user_id}:basic"),
                InlineKeyboardButton(text="💎 Premium", callback_data=f"adm:usub:t:{user_id}:premium"),
            ],
            [InlineKeyboardButton(text="❌ Batal", callback_data=f"adm:user:view:{user_id}")],
        ]
    )


def admin_assign_dur_keyboard(user_id: int, tier: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📅 1 Hari", callback_data=f"adm:usub:d:{user_id}:{tier}:daily")],
            [InlineKeyboardButton(text="📅 7 Hari", callback_data=f"adm:usub:d:{user_id}:{tier}:weekly")],
            [InlineKeyboardButton(text="📅 30 Hari", callback_data=f"adm:usub:d:{user_id}:{tier}:monthly")],
            [InlineKeyboardButton(text="❌ Batal", callback_data=f"adm:user:view:{user_id}")],
        ]
    )
