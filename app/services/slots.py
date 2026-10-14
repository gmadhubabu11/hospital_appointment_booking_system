from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app.models import Appointment, Doctor, Leave, Schedule
from app.utils.constants import DAYS


def day_name(d: date) -> str:
    return DAYS[d.weekday()]


def schedule_slots(schedule: Schedule, minutes: int) -> list:
    base = date(2000, 1, 1)
    step = timedelta(minutes=minutes)
    cur = datetime.combine(base, schedule.start_time)
    end = datetime.combine(base, schedule.end_time)
    bs = datetime.combine(base, schedule.break_start) if schedule.break_start else None
    be = datetime.combine(base, schedule.break_end) if schedule.break_end else None
    out = []
    while cur + step <= end:
        slot_end = cur + step
        if not (bs and cur < be and slot_end > bs):  # skip anything overlapping the break
            out.append(cur.time())
        cur = slot_end
    return out


def all_slots(db: Session, doctor: Doctor, d: date) -> list:
    schedules = db.query(Schedule).filter(Schedule.doctor_id == doctor.id, Schedule.day_of_week == day_name(d)).all()
    slots = set()
    for s in schedules:
        slots.update(schedule_slots(s, doctor.slot_duration_minutes))
    return sorted(slots)


def on_leave(db: Session, doctor_id: int, d: date) -> bool:
    return db.query(Leave).filter(Leave.doctor_id == doctor_id, Leave.leave_date == d).first() is not None


def booked_times(db: Session, doctor_id: int, d: date) -> set:
    rows = db.query(Appointment.slot_time).filter(
        Appointment.doctor_id == doctor_id, Appointment.appointment_date == d, Appointment.slot_held.is_(True)).all()
    return {r[0] for r in rows}


def available_slots(db: Session, doctor: Doctor, d: date) -> list:
    if on_leave(db, doctor.id, d):
        return []
    booked = booked_times(db, doctor.id, d)
    now = datetime.now()
    return [t for t in all_slots(db, doctor, d) if t not in booked and datetime.combine(d, t) > now]
