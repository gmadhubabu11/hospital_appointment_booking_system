from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.auth.security import decode_token
from app.database import SessionLocal
from app.models import Doctor, User
from app.websockets.manager import build_queue_state, manager
from starlette.concurrency import run_in_threadpool

router = APIRouter()


def _auth(token: str):
    from fastapi import HTTPException
    try:
        payload = decode_token(token, "access")
    except HTTPException:
        return None
    db = SessionLocal()
    try:
        user = db.get(User, int(payload["sub"]))
        return user.id if user and user.is_active else None
    finally:
        db.close()


def _doctor_exists(doctor_id: int) -> bool:
    db = SessionLocal()
    try:
        return db.get(Doctor, doctor_id) is not None
    finally:
        db.close()


@router.websocket("/ws/queue/{doctor_id}")
async def queue_ws(ws: WebSocket, doctor_id: int, token: str = Query("")):
    user_id = await run_in_threadpool(_auth, token)
    if user_id is None or not await run_in_threadpool(_doctor_exists, doctor_id):
        await ws.accept()
        await ws.close(code=1008)
        return
    await manager.connect_queue(ws, doctor_id, user_id)
    try:
        await ws.send_json(await run_in_threadpool(build_queue_state, doctor_id, user_id))
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect_queue(ws, doctor_id)


@router.websocket("/ws/notifications")
async def notifications_ws(ws: WebSocket, token: str = Query("")):
    user_id = await run_in_threadpool(_auth, token)
    if user_id is None:
        await ws.accept()
        await ws.close(code=1008)
        return
    await manager.connect_personal(ws, user_id)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect_personal(ws, user_id)
