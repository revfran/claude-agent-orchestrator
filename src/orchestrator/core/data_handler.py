import asyncio
from typing import Any


class DataHandler:
    """Async key-value store for shared data between agents."""

    def __init__(self):
        self._store: dict[str, Any] = {}
        self._lock = asyncio.Lock()

    async def write(self, key: str, value: Any):
        async with self._lock:
            self._store[key] = value

    async def read(self, key: str, default: Any = None) -> Any:
        async with self._lock:
            return self._store.get(key, default)

    async def delete(self, key: str):
        async with self._lock:
            self._store.pop(key, None)

    async def keys(self) -> list[str]:
        async with self._lock:
            return list(self._store.keys())
