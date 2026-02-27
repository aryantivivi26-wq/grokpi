from typing import Optional

from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, Message

# Keys to preserve across state.clear()
_PERSISTENT_KEYS = ("backend",)


async def clear_state(state: FSMContext) -> None:
    """Clear FSM state but preserve persistent keys like backend selection."""
    data = await state.get_data()
    preserved = {k: data[k] for k in _PERSISTENT_KEYS if k in data}
    await state.clear()
    if preserved:
        await state.update_data(**preserved)


async def get_backend(state: FSMContext) -> str:
    """Return the user's current backend choice from FSM state."""
    data = await state.get_data()
    return data.get("backend", "grok")


async def safe_edit_text(
    message: Optional[Message],
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
) -> None:
    if not message:
        return
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise
