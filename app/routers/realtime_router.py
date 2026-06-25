from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.jwt import decode_token
from app.models.user import User
from app.realtime.manager import realtime_manager

router = APIRouter(tags=["Realtime"])


def _resolve_socket_user(token: str, db: Session) -> User | None:
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    try:
        user_uuid = UUID(str(user_id))
    except ValueError:
        return None

    user = db.get(User, user_uuid)
    if not user or not user.is_active:
        return None
    return user


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(..., min_length=1)) -> None:
    db = SessionLocal()
    connection_id = str(uuid4())
    user: User | None = None
    try:
        user = _resolve_socket_user(token, db)
        if user is None:
            await websocket.close(code=4401, reason="Unauthorized")
            return

        await realtime_manager.connect(
            websocket,
            connection_id=connection_id,
            user_id=user.id,
            role=user.role.value,
        )

        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        return
    finally:
        db.close()
        if user is not None:
            realtime_manager.disconnect(
                connection_id=connection_id,
                user_id=user.id,
                role=user.role.value,
            )
