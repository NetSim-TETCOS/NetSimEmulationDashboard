from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from time import monotonic
from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self.participants: dict[str, WebSocket] = {}
        self._rates: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def connect(self, client_id: str, websocket: WebSocket) -> WebSocket | None:
        await websocket.accept()
        async with self._lock:
            previous = self.participants.get(client_id)
            self.participants[client_id] = websocket
        return previous

    async def disconnect(self, client_id: str, websocket: WebSocket) -> bool:
        async with self._lock:
            if self.participants.get(client_id) is websocket:
                self.participants.pop(client_id, None)
                return True
        return False

    def allowed(self, client_id: str, category: str, limit: int, window_seconds: float = 1.0) -> bool:
        now = monotonic()
        events = self._rates[(client_id, category)]
        while events and events[0] <= now - window_seconds:
            events.popleft()
        if len(events) >= limit:
            return False
        events.append(now)
        return True

    async def send(self, client_id: str, payload: dict[str, Any]) -> None:
        websocket = self.participants.get(client_id)
        if websocket:
            await websocket.send_json(payload)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        for client_id, websocket in list(self.participants.items()):
            try:
                await websocket.send_json(payload)
            except Exception:
                await self.disconnect(client_id, websocket)

    async def close(self, client_id: str, code: int = 1000) -> bool:
        websocket = self.participants.get(client_id)
        if not websocket:
            return False
        await websocket.close(code=code)
        await self.disconnect(client_id, websocket)
        return True
