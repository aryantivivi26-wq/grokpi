"""Abstract base class for AI backend clients"""

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List, Optional


class BackendClient(ABC):
    """Base class that all backend clients must implement."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Backend name (e.g. 'grok', 'gemini')"""
        ...

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the backend (called during app lifespan startup)."""
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        """Cleanup resources (called during app lifespan shutdown)."""
        ...

    @abstractmethod
    def list_models(self) -> List[Dict[str, Any]]:
        """Return list of available models in OpenAI format."""
        ...

    @abstractmethod
    async def chat(
        self,
        *,
        model: str,
        messages: List[Dict[str, Any]],
        stream: bool = False,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        request_id: str = "",
        base_url: str = "",
    ) -> Any:
        """
        Handle chat completion request.

        For stream=True, return an async generator yielding SSE lines (str).
        For stream=False, return a dict in OpenAI chat completion format.
        """
        ...

    @abstractmethod
    async def generate_image(
        self,
        *,
        prompt: str,
        model: str = "",
        n: int = 1,
        aspect_ratio: str = "1:1",
        response_format: str = "url",
        base_url: str = "",
        request_id: str = "",
    ) -> Dict[str, Any]:
        """Generate images. Return OpenAI /v1/images/generations format."""
        ...

    @abstractmethod
    async def generate_video(
        self,
        *,
        prompt: str,
        model: str = "",
        aspect_ratio: str = "16:9",
        duration_seconds: int = 6,
        resolution: str = "480p",
        preset: str = "normal",
        response_format: str = "url",
        base_url: str = "",
        request_id: str = "",
    ) -> Dict[str, Any]:
        """Generate video. Return OpenAI-like /v1/videos/generations format."""
        ...

    @abstractmethod
    async def get_status(self) -> Dict[str, Any]:
        """Return backend health/status info."""
        ...
