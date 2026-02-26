from aiogram.fsm.state import State, StatesGroup


class ImageFlow(StatesGroup):
    waiting_prompt = State()


class VideoFlow(StatesGroup):
    waiting_prompt = State()


class SSOFlow(StatesGroup):
    waiting_new_key = State()
