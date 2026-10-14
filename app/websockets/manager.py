import asyncio
import logging
from datetime import date
from typing import Dict, List, Set, Tuple

from fastapi import WebSocket
from starlette.concurrency import run_in_threadpool

from app.database import SessionLocal
from app.models import Appointment, Doctor
from app.utils.constants import BOOKED, CHECKED_IN, IN_CONSULT

logger = logging.getLogger("ws")


def build_queue_state(doctor_id: int, user_id: int) -> dict:
    db = SessionLocal()
    try:
        doctor = db.get(Doctor, doctor_id)
        today = date.today()
        appts = (db.query(Appointment)
                 .filter(Appointment.doctor_id == doctor_id, Appointment.appointment_date == today,
                         Appointment.status.in_([BOOKED, CHECKED_IN, IN_CONSULT]))
                 .order_by(Appointment.token_number).all())
        current = next((a for a in appts if a.status == IN_CONSULT), None)
        waiting = [a for a in appts if a.status == CHECKED_IN]
        state = {"type": "queue_update", "doctor_id": doctor_id, "date": str(today),
                 "current_token": current.token_number if current else None, "waiting_count": len(waiting)}
        mine = next((a for a in appts if a.patient_id == user_id), None)
        if mine:
            ahead = len([w for w in waiting if w.token_number < mine.token_number]) + (1 if current and mine is not current else 0)
            state["my"] = {"token": mine.token_number, "status": mine.status, "position": ahead + 1 if mine is not current else 0,
                           "estimated_wait_minutes": ahead * doctor.slot_duration_minutes if mine is not current else 0}
        return state
    finally:
        db.close()


def _next_up(doctor_id: int):
    db = SessionLocal()
    try:
        today = date.today()
        busy = db.query(Appointment).filter(Appointment.doctor_id == doctor_id, Appointment.appointment_date == today,
                                            Appointment.status == IN_CONSULT).first()
        nxt = (db.query(Appointment).filter(Appointment.doctor_id == doctor_id, Appointment.appointment_date == today,
                                            Appointment.status == CHECKED_IN).order_by(Appointment.token_number).first())
        return (nxt.id, nxt.patient_id) if (busy and nxt) else None
    finally:
        db.close()


class ConnectionManager:
    def __init__(self):
        self.queue: Dict[int, List[Tuple[WebSocket, int]]] = {}
        self.personal: Dict[int, List[WebSocket]] = {}
        self.notified_next: Set[int] = set()
        self.loop = None

    async def connect_queue(self, ws: WebSocket, doctor_id: int, user_id: int):
        await ws.accept()
        self.queue.setdefault(doctor_id, []).append((ws, user_id))

    def disconnect_queue(self, ws: WebSocket, doctor_id: int):
        self.queue[doctor_id] = [c for c in self.queue.get(doctor_id, []) if c[0] is not ws]

    async def connect_personal(self, ws: WebSocket, user_id: int):
        await ws.accept()
        self.personal.setdefault(user_id, []).append(ws)

    def disconnect_personal(self, ws: WebSocket, user_id: int):
        self.personal[user_id] = [w for w in self.personal.get(user_id, []) if w is not ws]

    async def push_queue(self, doctor_id: int):
        for ws, user_id in list(self.queue.get(doctor_id, [])):
            try:
                await ws.send_json(await run_in_threadpool(build_queue_state, doctor_id, user_id))
            except Exception:  # noqa: BLE001  (dead connection)
                self.disconnect_queue(ws, doctor_id)

    async def push_user(self, user_id: int, payload: dict):
        for ws in list(self.personal.get(user_id, [])):
            try:
                await ws.send_json(payload)
            except Exception:  # noqa: BLE001
                self.disconnect_personal(ws, user_id)

    def fire(self, coro):
        """Schedule a coroutine on the main event loop from sync code (request threads / scheduler threads)."""
        if self.loop is None:
            coro.close()
            return
        asyncio.run_coroutine_threadsafe(coro, self.loop)


manager = ConnectionManager()


def notify(user_id: int, event: str, message: str):
    manager.fire(manager.push_user(user_id, {"type": "notification", "event": event, "message": message}))


def queue_changed(doctor_id: int):
    """Call AFTER the DB commit: pushes the live queue and the 'you are next' notification."""
    manager.fire(manager.push_queue(doctor_id))
    nxt = _next_up(doctor_id)
    if nxt and nxt[0] not in manager.notified_next:
        manager.notified_next.add(nxt[0])
        notify(nxt[1], "your_turn_next", "You are next, please be ready")
