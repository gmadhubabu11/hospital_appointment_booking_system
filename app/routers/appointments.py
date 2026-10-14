from datetime import date, datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, require_roles
from app.database import get_db
from app.models import Appointment, Doctor, User
from app.schemas.appointment import AppointmentCreate, AppointmentOut, RescheduleIn
from app.services import email_service as mail
from app.services.appointments import make_number, resequence_tokens, set_status, validate_slot, log_history
from app.utils.constants import ADMIN, BOOKED, CHECKED_IN, DOCTOR, PATIENT
from app.websockets.manager import notify, queue_changed

router = APIRouter(prefix="/appointments", tags=["Appointments"])


def get_appt(db: Session, appt_id: int) -> Appointment:
    a = db.get(Appointment, appt_id)
    if not a:
        raise HTTPException(404, "Appointment not found")
    return a


def can_view(user: User, a: Appointment) -> bool:
    if user.role == ADMIN:
        return True
    if user.role == PATIENT:
        return a.patient_id == user.id
    return a.doctor.user_id == user.id


def assert_view(user: User, a: Appointment):
    if not can_view(user, a):
        raise HTTPException(403, "You cannot access this appointment")


def _slot_dt(a: Appointment) -> datetime:
    return datetime.combine(a.appointment_date, a.slot_time)


@router.post("", response_model=AppointmentOut, status_code=201)
def book(data: AppointmentCreate, background: BackgroundTasks, db: Session = Depends(get_db),
         user: User = Depends(require_roles(PATIENT))):
    # Row lock on the doctor serialises all bookings for that doctor, so two patients can't take the same slot.
    doctor = db.query(Doctor).filter(Doctor.id == data.doctor_id).with_for_update().first()
    if not doctor:
        raise HTTPException(404, "Doctor not found")
    validate_slot(db, doctor, data.appointment_date, data.slot_time, user.id)
    appt = Appointment(appointment_number="TEMP-" + datetime.now().strftime("%f%S%M"), patient_id=user.id,
                       doctor_id=doctor.id, appointment_date=data.appointment_date, slot_time=data.slot_time,
                       token_number=0, reason=data.reason, status=BOOKED,
                       consultation_fee=doctor.consultation_fee, slot_held=True)
    db.add(appt)
    try:
        db.flush()
        appt.appointment_number = make_number(db, appt)
        log_history(db, appt, None, BOOKED, user.id, "Appointment booked")
        resequence_tokens(db, doctor.id, data.appointment_date)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Slot was just booked by someone else, please pick another slot")
    db.refresh(appt)
    to, subject, body = mail.booked_mail(appt)
    background.add_task(mail.send_email, to, subject, body)
    notify(user.id, "appointment_booked", f"Appointment {appt.appointment_number} booked (token {appt.token_number})")
    if appt.appointment_date == date.today():
        queue_changed(doctor.id)
    return appt


@router.get("", response_model=List[AppointmentOut])
def list_appointments(status: Optional[str] = None, doctor_id: Optional[int] = None, date_from: Optional[date] = None,
                      date_to: Optional[date] = None, appointment_number: Optional[str] = None, skip: int = 0,
                      limit: int = 20, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Appointment)
    if user.role == PATIENT:
        q = q.filter(Appointment.patient_id == user.id)
    elif user.role == DOCTOR:
        q = q.join(Doctor, Doctor.id == Appointment.doctor_id).filter(Doctor.user_id == user.id)
    if status:
        q = q.filter(Appointment.status == status)
    if doctor_id:
        q = q.filter(Appointment.doctor_id == doctor_id)
    if date_from:
        q = q.filter(Appointment.appointment_date >= date_from)
    if date_to:
        q = q.filter(Appointment.appointment_date <= date_to)
    if appointment_number:
        q = q.filter(Appointment.appointment_number.ilike(f"%{appointment_number}%"))
    return q.order_by(Appointment.appointment_date.desc(), Appointment.slot_time).offset(skip).limit(min(limit, 100)).all()


@router.get("/{appointment_id}", response_model=AppointmentOut)
def get_one(appointment_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    a = get_appt(db, appointment_id)
    assert_view(user, a)
    return a


@router.put("/{appointment_id}/reschedule", response_model=AppointmentOut)
def reschedule(appointment_id: int, data: RescheduleIn, background: BackgroundTasks, db: Session = Depends(get_db),
               user: User = Depends(require_roles(PATIENT))):
    a = get_appt(db, appointment_id)
    if a.patient_id != user.id:
        raise HTTPException(403, "You can reschedule only your own appointments")
    doctor = db.query(Doctor).filter(Doctor.id == a.doctor_id).with_for_update().first()
    db.refresh(a)
    if a.status != BOOKED:
        raise HTTPException(400, "Only Booked appointments can be rescheduled")
    if _slot_dt(a) - datetime.now() < timedelta(hours=2):
        raise HTTPException(400, "Appointments can be rescheduled only up to 2 hours before the slot time")
    if a.reschedule_count >= 2:
        raise HTTPException(400, "Reschedule limit (2) reached; please cancel and book again")
    validate_slot(db, doctor, data.appointment_date, data.slot_time, user.id, exclude_id=a.id)
    old_date = a.appointment_date
    a.appointment_date, a.slot_time = data.appointment_date, data.slot_time
    a.reschedule_count += 1
    log_history(db, a, BOOKED, BOOKED, user.id, "Rescheduled")
    try:
        db.flush()
        resequence_tokens(db, doctor.id, old_date)
        resequence_tokens(db, doctor.id, a.appointment_date)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Slot was just booked by someone else, please pick another slot")
    db.refresh(a)
    to, subject, body = mail.rescheduled_mail(a)
    background.add_task(mail.send_email, to, subject, body)
    notify(user.id, "appointment_rescheduled", f"Appointment {a.appointment_number} rescheduled to {a.appointment_date} {a.slot_time}")
    for d in {old_date, a.appointment_date}:
        if d == date.today():
            queue_changed(doctor.id)
    return a


@router.put("/{appointment_id}/cancel", response_model=AppointmentOut)
def cancel(appointment_id: int, background: BackgroundTasks, db: Session = Depends(get_db),
           user: User = Depends(require_roles(PATIENT))):
    a = get_appt(db, appointment_id)
    if a.patient_id != user.id:
        raise HTTPException(403, "You can cancel only your own appointments")
    if a.status != BOOKED:
        raise HTTPException(400, "Only Booked appointments can be cancelled")
    if _slot_dt(a) - datetime.now() < timedelta(hours=2):
        raise HTTPException(400, "Appointments can be cancelled only up to 2 hours before the slot time")
    set_status(db, a, "Cancelled", user.id, "Cancelled by patient")
    db.commit()
    db.refresh(a)
    to, subject, body = mail.cancelled_mail(a)
    background.add_task(mail.send_email, to, subject, body)
    notify(user.id, "appointment_cancelled", f"Appointment {a.appointment_number} cancelled")
    if a.appointment_date == date.today():
        queue_changed(a.doctor_id)
    return a


@router.put("/{appointment_id}/check-in", response_model=AppointmentOut)
def check_in(appointment_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles(ADMIN))):
    a = get_appt(db, appointment_id)
    if a.status != BOOKED:
        raise HTTPException(400, "Only Booked appointments can be checked in")
    if a.appointment_date != date.today():
        raise HTTPException(400, "Check-in is allowed only on the appointment date")
    now, slot = datetime.now(), _slot_dt(a)
    if now < slot - timedelta(minutes=30):
        raise HTTPException(400, "Check-in opens 30 minutes before the slot time")
    if now > slot + timedelta(minutes=30):
        raise HTTPException(400, "Check-in window closed (30 minutes after slot time); appointment will be No-Show")
    set_status(db, a, CHECKED_IN, user.id, "Checked in at front desk")
    db.commit()
    db.refresh(a)
    notify(a.patient_id, "checked_in", f"You are checked in. Your token is {a.token_number}")
    queue_changed(a.doctor_id)
    return a
