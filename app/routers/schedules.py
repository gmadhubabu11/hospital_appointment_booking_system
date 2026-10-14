from datetime import date
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.database import get_db
from app.models import Appointment, Leave, Schedule, User
from app.routers.doctors import get_doctor_or_404
from app.schemas.hospital import LeaveIn, LeaveOut, ScheduleIn, ScheduleOut, SlotsOut
from app.services import email_service as mail
from app.services import slots as slot_service
from app.services.appointments import set_status
from app.utils.constants import ADMIN, BOOKED, CHECKED_IN
from app.websockets.manager import notify, queue_changed

router = APIRouter(tags=["Schedules & Leave"])


def assert_manage(user: User, doctor):
    if user.role == ADMIN or (user.role == "Doctor" and doctor.user_id == user.id):
        return
    raise HTTPException(403, "You can manage only your own schedule and leave")


def _overlap(db, doctor_id, data: ScheduleIn, exclude_id=None):
    q = db.query(Schedule).filter(Schedule.doctor_id == doctor_id, Schedule.day_of_week == data.day_of_week)
    if exclude_id:
        q = q.filter(Schedule.id != exclude_id)
    for s in q.all():
        if data.start_time < s.end_time and data.end_time > s.start_time:
            raise HTTPException(409, f"Schedule overlaps with existing schedule {s.start_time}-{s.end_time}")


@router.post("/doctors/{doctor_id}/schedules", response_model=ScheduleOut, status_code=201)
def add_schedule(doctor_id: int, data: ScheduleIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    doctor = get_doctor_or_404(db, doctor_id)
    assert_manage(user, doctor)
    _overlap(db, doctor_id, data)
    s = Schedule(doctor_id=doctor_id, **data.model_dump())
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@router.get("/doctors/{doctor_id}/schedules", response_model=List[ScheduleOut])
def list_schedules(doctor_id: int, skip: int = 0, limit: int = 50, db: Session = Depends(get_db),
                   _: User = Depends(get_current_user)):
    get_doctor_or_404(db, doctor_id)
    return db.query(Schedule).filter(Schedule.doctor_id == doctor_id).order_by(Schedule.day_of_week, Schedule.start_time) \
        .offset(skip).limit(min(limit, 100)).all()


@router.put("/schedules/{schedule_id}", response_model=ScheduleOut)
def update_schedule(schedule_id: int, data: ScheduleIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    s = db.get(Schedule, schedule_id)
    if not s:
        raise HTTPException(404, "Schedule not found")
    assert_manage(user, s.doctor)
    _overlap(db, s.doctor_id, data, exclude_id=schedule_id)
    for k, v in data.model_dump().items():
        setattr(s, k, v)
    db.commit()
    db.refresh(s)
    return s


@router.delete("/schedules/{schedule_id}")
def delete_schedule(schedule_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    s = db.get(Schedule, schedule_id)
    if not s:
        raise HTTPException(404, "Schedule not found")
    assert_manage(user, s.doctor)
    db.delete(s)
    db.commit()
    return {"message": "Schedule deleted"}


@router.post("/doctors/{doctor_id}/leaves", response_model=LeaveOut, status_code=201)
def add_leave(doctor_id: int, data: LeaveIn, background: BackgroundTasks, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    doctor = get_doctor_or_404(db, doctor_id)
    assert_manage(user, doctor)
    if data.leave_date < date.today():
        raise HTTPException(400, "Leave date cannot be in the past")
    if db.query(Leave).filter(Leave.doctor_id == doctor_id, Leave.leave_date == data.leave_date).first():
        raise HTTPException(409, "Leave already exists for this date")
    leave = Leave(doctor_id=doctor_id, **data.model_dump())
    db.add(leave)

    affected = db.query(Appointment).filter(
        Appointment.doctor_id == doctor_id, Appointment.appointment_date == data.leave_date,
        Appointment.status.in_([BOOKED, CHECKED_IN])).all()
    emails, notes = [], []
    for a in affected:
        set_status(db, a, "Cancelled", user.id, "Doctor on leave")
        emails.append(mail.leave_cancel_mail(a))
        notes.append((a.patient_id, f"Appointment {a.appointment_number} cancelled: doctor is on leave"))
    db.commit()
    db.refresh(leave)
    for to, subject, body in emails:
        background.add_task(mail.send_email, to, subject, body)
    for uid, msg in notes:
        notify(uid, "appointment_cancelled", msg)
    if affected:
        queue_changed(doctor_id)
    return leave


@router.get("/doctors/{doctor_id}/leaves", response_model=List[LeaveOut])
def list_leaves(doctor_id: int, skip: int = 0, limit: int = 50, db: Session = Depends(get_db),
                _: User = Depends(get_current_user)):
    get_doctor_or_404(db, doctor_id)
    return db.query(Leave).filter(Leave.doctor_id == doctor_id).order_by(Leave.leave_date).offset(skip) \
        .limit(min(limit, 100)).all()


@router.get("/doctors/{doctor_id}/available-slots", response_model=SlotsOut)
def available(doctor_id: int, date: date, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    doctor = get_doctor_or_404(db, doctor_id)
    slots = slot_service.available_slots(db, doctor, date)
    return SlotsOut(doctor_id=doctor_id, date=date, slot_duration_minutes=doctor.slot_duration_minutes,
                    slots=[t.strftime("%H:%M") for t in slots])
