"""Gemini browser automation — headless Chrome login and cookie extraction."""

from .browser_login import GeminiAutomation, TaskCancelledError

__all__ = ["GeminiAutomation", "TaskCancelledError"]
