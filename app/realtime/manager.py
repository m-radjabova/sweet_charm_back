from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import anyio
from fastapi import WebSocket


class RealtimeConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}
        self._user_connections: dict[str, set[str]] = defaultdict(set)
        self._role_connections: dict[str, set[str]] = defaultdict(set)

    async def connect(self, websocket: WebSocket, *, connection_id: str, user_id: UUID, role: str) -> None:
        await websocket.accept()
        self._connections[connection_id] = websocket
        self._user_connections[str(user_id)].add(connection_id)
        self._role_connections[role].add(connection_id)

    def disconnect(self, *, connection_id: str, user_id: UUID, role: str) -> None:
        self._connections.pop(connection_id, None)
        self._discard(self._user_connections, str(user_id), connection_id)
        self._discard(self._role_connections, role, connection_id)

    async def emit_to_user(self, user_id: UUID | str, event: str, data: Any) -> None:
        await self._emit_many(self._user_connections.get(str(user_id), set()), event, data)

    async def emit_to_role(self, role: str, event: str, data: Any) -> None:
        await self._emit_many(self._role_connections.get(role, set()), event, data)

    async def emit_to_admins(self, event: str, data: Any) -> None:
        await self.emit_to_role("admin", event, data)

    def emit_to_user_sync(self, user_id: UUID | str, event: str, data: Any) -> None:
        self._run_from_thread(self.emit_to_user, user_id, event, data)

    def emit_to_role_sync(self, role: str, event: str, data: Any) -> None:
        self._run_from_thread(self.emit_to_role, role, event, data)

    def emit_to_admins_sync(self, event: str, data: Any) -> None:
        self._run_from_thread(self.emit_to_admins, event, data)

    async def _emit_many(self, connection_ids: set[str], event: str, data: Any) -> None:
        if not connection_ids:
            return

        payload = {
            "event": event,
            "data": data,
            "created_at": datetime.now(UTC).isoformat(),
        }
        stale_ids: list[str] = []

        for connection_id in list(connection_ids):
            websocket = self._connections.get(connection_id)
            if websocket is None:
                stale_ids.append(connection_id)
                continue
            try:
                await websocket.send_json(payload)
            except Exception:
                stale_ids.append(connection_id)

        for connection_id in stale_ids:
            self._connections.pop(connection_id, None)
            self._remove_connection_everywhere(connection_id)

    @staticmethod
    def _discard(mapping: dict[str, set[str]], key: str, connection_id: str) -> None:
        bucket = mapping.get(key)
        if not bucket:
            return
        bucket.discard(connection_id)
        if not bucket:
            mapping.pop(key, None)

    def _remove_connection_everywhere(self, connection_id: str) -> None:
        for mapping in (self._user_connections, self._role_connections):
            empty_keys: list[str] = []
            for key, bucket in mapping.items():
                if connection_id in bucket:
                    bucket.discard(connection_id)
                if not bucket:
                    empty_keys.append(key)
            for key in empty_keys:
                mapping.pop(key, None)

    @staticmethod
    def _run_from_thread(fn, *args: Any) -> None:
        try:
            anyio.from_thread.run(fn, *args)
        except RuntimeError:
            return


realtime_manager = RealtimeConnectionManager()
