"""Backend router - dispatches requests to the correct backend by model name."""

import logging
from typing import Any, Dict, List, Optional

from .base import BackendClient

logger = logging.getLogger(__name__)


class BackendRouter:
    """Routes model requests to the appropriate backend client."""

    def __init__(self) -> None:
        self._backends: Dict[str, BackendClient] = {}
        # prefix -> backend name mapping
        self._prefix_map: Dict[str, str] = {}

    def register(self, backend: BackendClient, prefixes: List[str]) -> None:
        """Register a backend with its model prefixes."""
        self._backends[backend.name] = backend
        for prefix in prefixes:
            self._prefix_map[prefix] = backend.name
        logger.info(f"[Router] Registered backend '{backend.name}' for prefixes: {prefixes}")

    def get_backend(self, model: str) -> Optional[BackendClient]:
        """Get the backend for a given model name."""
        # Exact model prefix match (longest prefix first)
        for prefix in sorted(self._prefix_map.keys(), key=len, reverse=True):
            if model.startswith(prefix):
                name = self._prefix_map[prefix]
                return self._backends.get(name)
        return None

    def get_backend_by_name(self, name: str) -> Optional[BackendClient]:
        """Get backend by its name."""
        return self._backends.get(name)

    def list_all_models(self) -> List[Dict[str, Any]]:
        """Aggregate models from all backends."""
        models = []
        for backend in self._backends.values():
            models.extend(backend.list_models())
        return models

    async def initialize_all(self) -> None:
        """Initialize all registered backends."""
        for backend in self._backends.values():
            try:
                await backend.initialize()
                logger.info(f"[Router] Backend '{backend.name}' initialized")
            except Exception as e:
                logger.error(f"[Router] Failed to initialize '{backend.name}': {e}")

    async def shutdown_all(self) -> None:
        """Shutdown all registered backends."""
        for backend in self._backends.values():
            try:
                await backend.shutdown()
            except Exception as e:
                logger.error(f"[Router] Error shutting down '{backend.name}': {e}")

    async def get_all_status(self) -> Dict[str, Any]:
        """Get status from all backends."""
        status = {}
        for name, backend in self._backends.items():
            try:
                status[name] = await backend.get_status()
            except Exception as e:
                status[name] = {"error": str(e)}
        return status


# Global router instance
backend_router = BackendRouter()
