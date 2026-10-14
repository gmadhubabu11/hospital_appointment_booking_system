from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth.deps import require_roles
from app.config import BASE_DIR
from app.database import get_db
from app.models import Appointment, Doctor, User
from app.routers.appointments import AppointmentOut
from app.services.appointments import set_status
from app.utils.constants import CHECKED_IN, DOCTOR, IN_CONSULT
from app.websockets.manager import notify, queue_changed

router = APIRouter(tags=["Live Queue"])


@router.put("/doctors/me/call-next", response_model=AppointmentOut)
def call_next(db: Session = Depends(get_db), user: User = Depends(require_roles(DOCTOR))):
    doctor = db.query(Doctor).filter(Doctor.user_id == user.id).first()
    if not doctor:
        raise HTTPException(404, "Doctor profile not found")
    today = date.today()
    base = db.query(Appointment).filter(Appointment.doctor_id == doctor.id, Appointment.appointment_date == today)
    if base.filter(Appointment.status == IN_CONSULT).first():
        raise HTTPException(400, "Save the current patient's consultation before calling the next patient")
    nxt = base.filter(Appointment.status == CHECKED_IN).order_by(Appointment.token_number).first()
    if not nxt:
        raise HTTPException(404, "No checked-in patients waiting")
    set_status(db, nxt, IN_CONSULT, user.id, "Called by doctor")
    db.commit()
    db.refresh(nxt)
    notify(nxt.patient_id, "your_turn", "It's your turn, please go to the doctor's room")
    queue_changed(doctor.id)
    return nxt


@router.get("/queue-test", include_in_schema=False)
def queue_test_page():
    return FileResponse(BASE_DIR / "static" / "queue_test.html")
