from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# Backend display labels
BACKEND_LABELS = {
    "grok": "Grok",
    "gemini": "Gemini",
}

BACKEND_ICONS = {
    "grok": "⚡",
    "gemini": "✦",
}


def main_menu_keyboard(backend: str = "grok") -> InlineKeyboardMarkup:
    icon = BACKEND_ICONS.get(backend, "")
    label = BACKEND_LABELS.get(backend, backend)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🖼 Image", callback_data="menu:image"),
                InlineKeyboardButton(text="🎬 Video", callback_data="menu:video"),
            ],
            [
                InlineKeyboardButton(text="💎 Langganan", callback_data="menu:subs"),
                InlineKeyboardButton(text="📊 Kuota", callback_data="menu:limit"),
            ],
            [
                InlineKeyboardButton(text="📦 Topup", callback_data="menu:topup"),
                InlineKeyboardButton(text="🏆 Ranking", callback_data="menu:leaderboard"),
            ],
            [
                InlineKeyboardButton(text="🔗 Referral", callback_data="menu:referral"),
                InlineKeyboardButton(text=f"{icon} {label}", callback_data="menu:backend"),
            ],
        ]
    )


def referral_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="↻ Refresh", callback_data="menu:referral")],
            [InlineKeyboardButton(text="← Kembali", callback_data="menu:home")],
        ]
    )


def backend_select_keyboard(current: str = "grok") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{'● ' if current == 'grok' else '○ '}⚡ Grok",
                    callback_data="backend:grok",
                ),
                InlineKeyboardButton(
                    text=f"{'● ' if current == 'gemini' else '○ '}✦ Gemini",
                    callback_data="backend:gemini",
                ),
            ],
            [InlineKeyboardButton(text="← Kembali", callback_data="menu:home")],
        ]
    )


def image_menu_keyboard(selected_aspect: str, selected_n: int, max_n: int = 4, max_batch: int = 1) -> InlineKeyboardMarkup:
    n_buttons = [
        InlineKeyboardButton(
            text=f"{'● ' if selected_n == i else '○ '}{i}",
            callback_data=f"img:n:{i}",
        )
        for i in range(1, max_n + 1)
    ]

    rows = [
        [InlineKeyboardButton(text="── Rasio ──", callback_data="noop")],
        [
            InlineKeyboardButton(text=f"{'● ' if selected_aspect == '1:1' else '○ '}1:1", callback_data="img:aspect:1:1"),
            InlineKeyboardButton(text=f"{'● ' if selected_aspect == '2:3' else '○ '}2:3", callback_data="img:aspect:2:3"),
            InlineKeyboardButton(text=f"{'● ' if selected_aspect == '3:2' else '○ '}3:2", callback_data="img:aspect:3:2"),
        ],
        [
            InlineKeyboardButton(text=f"{'● ' if selected_aspect == '9:16' else '○ '}9:16", callback_data="img:aspect:9:16"),
            InlineKeyboardButton(text=f"{'● ' if selected_aspect == '16:9' else '○ '}16:9", callback_data="img:aspect:16:9"),
        ],
        [InlineKeyboardButton(text="── Jumlah ──", callback_data="noop")],
        n_buttons,
        [InlineKeyboardButton(text="✏️ Tulis Prompt", callback_data="img:prompt")],
    ]

    if max_batch > 1:
        rows.append([InlineKeyboardButton(text=f"📝 Batch ({max_batch} prompt)", callback_data="img:batch")])

    rows.append([InlineKeyboardButton(text="← Kembali", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def video_menu_keyboard(aspect: str, duration: int, resolution: str, preset: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="── Rasio ──", callback_data="noop")],
            [
                InlineKeyboardButton(text=f"{'● ' if aspect == '9:16' else '○ '}9:16", callback_data="vid:aspect:9:16"),
                InlineKeyboardButton(text=f"{'● ' if aspect == '16:9' else '○ '}16:9", callback_data="vid:aspect:16:9"),
                InlineKeyboardButton(text=f"{'● ' if aspect == '1:1' else '○ '}1:1", callback_data="vid:aspect:1:1"),
            ],
            [InlineKeyboardButton(text="── Durasi ──", callback_data="noop")],
            [
                InlineKeyboardButton(text=f"{'● ' if duration == 6 else '○ '}6 detik", callback_data="vid:duration:6"),
                InlineKeyboardButton(text=f"{'● ' if duration == 10 else '○ '}10 detik", callback_data="vid:duration:10"),
            ],
            [InlineKeyboardButton(text="── Resolusi ──", callback_data="noop")],
            [
                InlineKeyboardButton(text=f"{'● ' if resolution == '480p' else '○ '}480p", callback_data="vid:resolution:480p"),
                InlineKeyboardButton(text=f"{'● ' if resolution == '720p' else '○ '}720p", callback_data="vid:resolution:720p"),
            ],
            [InlineKeyboardButton(text="── Preset ──", callback_data="noop")],
            [
                InlineKeyboardButton(text=f"{'● ' if preset == 'normal' else '○ '}Normal", callback_data="vid:preset:normal"),
                InlineKeyboardButton(text=f"{'● ' if preset == 'fun' else '○ '}Fun", callback_data="vid:preset:fun"),
            ],
            [
                InlineKeyboardButton(text=f"{'● ' if preset == 'spicy' else '○ '}Spicy", callback_data="vid:preset:spicy"),
                InlineKeyboardButton(text=f"{'● ' if preset == 'custom' else '○ '}Custom", callback_data="vid:preset:custom"),
            ],
            [InlineKeyboardButton(text="✏️ Tulis Prompt", callback_data="vid:prompt")],
            [InlineKeyboardButton(text="← Kembali", callback_data="menu:home")],
        ]
    )


# ---------------------------------------------------------------------------
# Admin keyboards
# ---------------------------------------------------------------------------

def admin_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👥 Users", callback_data="adm:users"),
                InlineKeyboardButton(text="💎 Subs", callback_data="adm:subs"),
            ],
            [
                InlineKeyboardButton(text="📢 Broadcast", callback_data="adm:broadcast"),
                InlineKeyboardButton(text="📊 Stats", callback_data="adm:stats"),
            ],
            [
                InlineKeyboardButton(text="🖼 Images", callback_data="admin:images"),
                InlineKeyboardButton(text="🎬 Videos", callback_data="admin:videos"),
            ],
            [
                InlineKeyboardButton(text="📡 Gateway", callback_data="admin:status"),
                InlineKeyboardButton(text="🔑 SSO", callback_data="admin:reload_sso"),
            ],
            [
                InlineKeyboardButton(text="✦ Gemini", callback_data="menu:gemini"),
                InlineKeyboardButton(text="➕ SSO Key", callback_data="admin:add_key"),
            ],
            [InlineKeyboardButton(text="← Kembali", callback_data="menu:home")],
        ]
    )


def media_list_keyboard(media_type: str, items_count: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"✕ #{idx + 1}", callback_data=f"admin:delete:{media_type}:{idx}")]
        for idx in range(items_count)
    ]
    rows.append([InlineKeyboardButton(text="↻ Refresh", callback_data=f"admin:{media_type}")])
    rows.append([InlineKeyboardButton(text="← Admin", callback_data="menu:admin")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def media_page_keyboard(media_type: str, start: int, end: int, total: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"✕ #{idx + 1}", callback_data=f"admin:deleteask:{media_type}:{idx}")]
        for idx in range(start, end)
    ]
    nav = []
    if start > 0:
        prev_start = max(0, start - (end - start))
        nav.append(InlineKeyboardButton(text="◂ Prev", callback_data=f"admin:page:{media_type}:{prev_start}"))
    if end < total:
        nav.append(InlineKeyboardButton(text="Next ▸", callback_data=f"admin:page:{media_type}:{end}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="↻ Refresh", callback_data=f"admin:{media_type}")])
    rows.append([InlineKeyboardButton(text="← Admin", callback_data="menu:admin")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def delete_confirm_keyboard(media_type: str, idx: int, back_start: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Ya, Hapus", callback_data=f"admin:deleteok:{media_type}:{idx}"),
                InlineKeyboardButton(text="Batal", callback_data=f"admin:page:{media_type}:{back_start}"),
            ]
        ]
    )


# ---------------------------------------------------------------------------
# SSO keyboards
# ---------------------------------------------------------------------------

def sso_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➕ Tambah", callback_data="sso:add"),
                InlineKeyboardButton(text="📋 List", callback_data="sso:list"),
            ],
            [
                InlineKeyboardButton(text="✕ Hapus Terakhir", callback_data="sso:remove_last"),
                InlineKeyboardButton(text="↻ Reload", callback_data="sso:reload"),
            ],
            [InlineKeyboardButton(text="← Kembali", callback_data="menu:home")],
        ]
    )


def sso_add_input_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✕ Batal", callback_data="sso:add:cancel")],
        ]
    )


# ---------------------------------------------------------------------------
# Gemini keyboards
# ---------------------------------------------------------------------------

def gemini_menu_keyboard(server_data: list | None = None) -> InlineKeyboardMarkup:
    """Gemini manager menu with server status."""
    rows = []

    if server_data:
        for srv in server_data:
            idx = srv["index"]
            label = srv["label"]
            rows.append([
                InlineKeyboardButton(text=label, callback_data=f"gem:info:{idx}"),
                InlineKeyboardButton(text="✕", callback_data=f"gem:rm:{idx}"),
            ])
    else:
        rows.append([InlineKeyboardButton(text="📋 Status Server", callback_data="gem:list")])

    rows.extend([
        [
            InlineKeyboardButton(text="➕ Manual", callback_data="gem:add"),
            InlineKeyboardButton(text="⚡ Auto-Register", callback_data="gem:autoreg"),
        ],
        [
            InlineKeyboardButton(text="↻ Reload", callback_data="gem:reload"),
            InlineKeyboardButton(text="🔍 Health", callback_data="gem:health"),
        ],
        [InlineKeyboardButton(text="← Admin", callback_data="menu:admin")],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def gemini_input_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✕ Batal", callback_data="gem:add:cancel")],
        ]
    )


def gemini_skip_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="» Skip", callback_data="gem:skip"),
                InlineKeyboardButton(text="✕ Batal", callback_data="gem:add:cancel"),
            ],
        ]
    )


# ---------------------------------------------------------------------------
# Subscription keyboards
# ---------------------------------------------------------------------------

def subscription_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📋 Info", callback_data="subs:info"),
                InlineKeyboardButton(text="📊 Tiers", callback_data="subs:tiers"),
            ],
            [InlineKeyboardButton(text="🛒 Beli Langganan", callback_data="pay:buy")],
            [InlineKeyboardButton(text="📜 Riwayat", callback_data="pay:history")],
            [InlineKeyboardButton(text="← Kembali", callback_data="menu:home")],
        ]
    )


def subscription_admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📋 Info", callback_data="subs:info"),
                InlineKeyboardButton(text="📊 Tiers", callback_data="subs:tiers"),
            ],
            [InlineKeyboardButton(text="🛒 Beli Langganan", callback_data="pay:buy")],
            [InlineKeyboardButton(text="📜 Riwayat", callback_data="pay:history")],
            [
                InlineKeyboardButton(text="➕ Grant", callback_data="subs:grant"),
                InlineKeyboardButton(text="✕ Revoke", callback_data="subs:revoke"),
            ],
            [InlineKeyboardButton(text="📃 Active Subs", callback_data="subs:list")],
            [InlineKeyboardButton(text="← Kembali", callback_data="menu:home")],
        ]
    )


def grant_tier_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⭐ Basic", callback_data="subs:grant:basic"),
                InlineKeyboardButton(text="💎 Premium", callback_data="subs:grant:premium"),
            ],
            [InlineKeyboardButton(text="✕ Batal", callback_data="menu:subs")],
        ]
    )


def grant_duration_keyboard(tier: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="1 Hari", callback_data=f"subs:dur:{tier}:daily"),
                InlineKeyboardButton(text="7 Hari", callback_data=f"subs:dur:{tier}:weekly"),
            ],
            [InlineKeyboardButton(text="30 Hari", callback_data=f"subs:dur:{tier}:monthly")],
            [InlineKeyboardButton(text="✕ Batal", callback_data="menu:subs")],
        ]
    )


# ---------------------------------------------------------------------------
# Payment keyboards
# ---------------------------------------------------------------------------

def pay_tier_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⭐ Basic", callback_data="pay:tier:basic"),
                InlineKeyboardButton(text="💎 Premium", callback_data="pay:tier:premium"),
            ],
            [InlineKeyboardButton(text="← Kembali", callback_data="menu:subs")],
        ]
    )


def pay_duration_keyboard(tier: str, prices: dict) -> InlineKeyboardMarkup:
    rows = []
    for dur_key, label in [("daily", "1 Hari"), ("weekly", "7 Hari"), ("monthly", "30 Hari")]:
        price = prices.get(f"{tier}_{dur_key}", 0)
        rows.append([
            InlineKeyboardButton(
                text=f"{label} · Rp {price:,}".replace(",", "."),
                callback_data=f"pay:dur:{tier}:{dur_key}",
            )
        ])
    rows.append([InlineKeyboardButton(text="← Kembali", callback_data="pay:buy")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def pay_confirm_keyboard(tier: str, duration: str, amount: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=f"Bayar Rp {amount:,}".replace(",", "."),
                callback_data=f"pay:confirm:{tier}:{duration}",
            )],
            [InlineKeyboardButton(text="← Kembali", callback_data="pay:buy")],
        ]
    )


def pay_waiting_keyboard(transaction_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="↻ Cek Pembayaran", callback_data=f"pay:check:{transaction_id}")],
            [InlineKeyboardButton(text="✕ Batalkan", callback_data=f"pay:cancel:{transaction_id}")],
        ]
    )


def pay_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="← Kembali", callback_data="menu:subs")],
        ]
    )


# ---------------------------------------------------------------------------
# Admin user management keyboards
# ---------------------------------------------------------------------------

def admin_users_keyboard(page: int, total_pages: int) -> InlineKeyboardMarkup:
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◂ Prev", callback_data=f"adm:users:p:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="Next ▸", callback_data=f"adm:users:p:{page + 1}"))

    rows = []
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="🔍 Cari User", callback_data="adm:user:search")])
    rows.append([InlineKeyboardButton(text="← Admin", callback_data="menu:admin")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_user_detail_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➕ Grant Sub", callback_data=f"adm:usub:grant:{user_id}"),
                InlineKeyboardButton(text="✕ Revoke", callback_data=f"adm:usub:revoke:{user_id}"),
            ],
            [InlineKeyboardButton(text="✕ Hapus User", callback_data=f"adm:user:del:{user_id}")],
            [InlineKeyboardButton(text="← Users", callback_data="adm:users")],
        ]
    )


def admin_user_del_confirm_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Ya, Hapus", callback_data=f"adm:user:delok:{user_id}"),
                InlineKeyboardButton(text="Batal", callback_data=f"adm:user:view:{user_id}"),
            ],
        ]
    )


def broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Kirim", callback_data="adm:bc:send"),
                InlineKeyboardButton(text="Batal", callback_data="menu:admin"),
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
            [InlineKeyboardButton(text="✕ Batal", callback_data=f"adm:user:view:{user_id}")],
        ]
    )


def admin_assign_dur_keyboard(user_id: int, tier: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="1 Hari", callback_data=f"adm:usub:d:{user_id}:{tier}:daily"),
                InlineKeyboardButton(text="7 Hari", callback_data=f"adm:usub:d:{user_id}:{tier}:weekly"),
            ],
            [InlineKeyboardButton(text="30 Hari", callback_data=f"adm:usub:d:{user_id}:{tier}:monthly")],
            [InlineKeyboardButton(text="✕ Batal", callback_data=f"adm:user:view:{user_id}")],
        ]
    )
