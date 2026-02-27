from aiogram.fsm.state import State, StatesGroup


class ImageFlow(StatesGroup):
    waiting_prompt = State()
    waiting_batch_prompts = State()


class VideoFlow(StatesGroup):
    waiting_prompt = State()


class SSOFlow(StatesGroup):
    waiting_new_key = State()


class SubsAdminFlow(StatesGroup):
    waiting_user_id = State()


class PaymentFlow(StatesGroup):
    waiting_confirm = State()     # user sees QRIS, bot is polling


class BroadcastFlow(StatesGroup):
    waiting_message = State()     # admin composing broadcast message


class AdminUserFlow(StatesGroup):
    waiting_user_id = State()     # admin entering user ID for subs assign
