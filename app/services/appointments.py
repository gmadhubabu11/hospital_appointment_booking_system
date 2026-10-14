from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Appointment, AppointmentHistory, Doctor
from app.services import slots as slot_service
from app.utils.constants import CANCELLED


def log_history(db: Session, appt: Appointment, old: Optional[str], new: str, changed_by: Optional[int], note=None):
    db.add(AppointmentHistory(appointment_id=appt.id, old_status=old, new_status=new, changed_by=changed_by, note=note))


def set_status(db: Session, appt: Appointment, new: str, changed_by: Optional[int], note=None):
    old = appt.status
    appt.status = new
    if new == CANCELLED:
        appt.slot_held = None  # free the slot for others
    log_history(db, appt, old, new, changed_by, note)


def validate_slot(db: Session, doctor: Doctor, d: date, t, patient_id: int, exclude_id: Optional[int] = None):
    """All Level 5 booking rules. Caller must already hold the doctor row lock."""
    if not doctor.is_active:
        raise HTTPException(400, "Doctor is not active")
    now = datetime.now()
    if datetime.combine(d, t) <= now:
        raise HTTPException(400, "Appointments can be booked only for future slots")
    if d > date.today() + timedelta(days=30):
        raise HTTPException(400, "Appointments can be booked at most 30 days in advance")
    if slot_service.on_leave(db, doctor.id, d):
        raise HTTPException(400, "Doctor is on leave on this date")
    if t not in slot_service.all_slots(db, doctor, d):
        raise HTTPException(400, "Slot is outside the doctor's schedule, in break time, or not a valid slot start")

    def q(*conds):
        query = db.query(Appointment).filter(*conds)
        if exclude_id:
            query = query.filter(Appointment.id != exclude_id)
        return query

    if q(Appointment.doctor_id == doctor.id, Appointment.appointment_date == d, Appointment.slot_time == t,
         Appointment.slot_held.is_(True)).first():
        raise HTTPException(409, "Slot is already booked")
    if q(Appointment.patient_id == patient_id, Appointment.appointment_date == d, Appointment.slot_time == t,
         Appointment.status != CANCELLED).first():
        raise HTTPException(409, "You already have an appointment at this date and time")
    if q(Appointment.patient_id == patient_id, Appointment.doctor_id == doctor.id, Appointment.appointment_date == d,
         Appointment.status != CANCELLED).first():
        raise HTTPException(409, "You already have an appointment with this doctor on this day")


def resequence_tokens(db: Session, doctor_id: int, d: date):
    """Tokens start from 1 per doctor per day and follow slot-time order (cancelled appointments are skipped)."""
    appts = (db.query(Appointment)
             .filter(Appointment.doctor_id == doctor_id, Appointment.appointment_date == d,
                     Appointment.status != CANCELLED)
             .order_by(Appointment.slot_time).all())
    for i, a in enumerate(appts, start=1):
        a.token_number = i
    db.flush()


def make_number(db: Session, appt: Appointment) -> str:
    seq = db.query(func.count(Appointment.id)).filter(
        Appointment.appointment_date == appt.appointment_date, Appointment.id <= appt.id).scalar()
    return f"APT-{appt.appointment_date.strftime('%Y%m%d')}-{seq:04d}"
