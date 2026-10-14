from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.auth.deps import require_roles
from app.database import get_db
from app.models import Appointment, Department, Doctor, User
from app.utils.constants import ADMIN, CANCELLED, CHECKED_IN, COMPLETED, NO_SHOW

router = APIRouter(prefix="/reports", tags=["Reports"], dependencies=[Depends(require_roles(ADMIN))])


def _range(date_from: Optional[date], date_to: Optional[date]):
    return date_from or date.today() - timedelta(days=30), date_to or date.today()


def _count(status):
    return func.coalesce(func.sum(case((Appointment.status == status, 1), else_=0)), 0)


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    r = db.query(func.count(Appointment.id), _count(CHECKED_IN), _count(COMPLETED), _count(CANCELLED), _count(NO_SHOW),
                 func.coalesce(func.sum(case((Appointment.status == COMPLETED, Appointment.consultation_fee), else_=0)), 0)
                 ).filter(Appointment.appointment_date == date.today()).one()
    return {"date": str(date.today()), "total_appointments": r[0], "checked_in": int(r[1]), "completed": int(r[2]),
            "cancelled": int(r[3]), "no_shows": int(r[4]), "consultation_revenue": float(r[5])}


@router.get("/doctor-performance")
def doctor_performance(date_from: Optional[date] = None, date_to: Optional[date] = None, db: Session = Depends(get_db)):
    d1, d2 = _range(date_from, date_to)
    rows = (db.query(Doctor.id, Doctor.name, func.count(Appointment.id), _count(COMPLETED), _count(NO_SHOW),
                     func.coalesce(func.sum(case((Appointment.status == COMPLETED, Appointment.consultation_fee), else_=0)), 0))
            .join(Appointment, Appointment.doctor_id == Doctor.id)
            .filter(Appointment.appointment_date.between(d1, d2)).group_by(Doctor.id, Doctor.name).all())
    return [{"doctor_id": i, "doctor_name": n, "appointments": t, "completed_consultations": int(c),
             "no_show_percentage": round(int(ns) * 100 / t, 2) if t else 0, "revenue": float(rev)}
            for i, n, t, c, ns, rev in rows]


@router.get("/department-summary")
def department_summary(date_from: Optional[date] = None, date_to: Optional[date] = None, db: Session = Depends(get_db)):
    d1, d2 = _range(date_from, date_to)
    rows = (db.query(Department.id, Department.name, func.count(Appointment.id))
            .join(Doctor, Doctor.department_id == Department.id).join(Appointment, Appointment.doctor_id == Doctor.id)
            .filter(Appointment.appointment_date.between(d1, d2)).group_by(Department.id, Department.name).all())
    return [{"department_id": i, "department": n, "appointment_count": c} for i, n, c in rows]


@router.get("/peak-hours")
def peak_hours(db: Session = Depends(get_db)):
    rows = dict(db.query(func.hour(Appointment.slot_time), func.count(Appointment.id)).group_by(func.hour(Appointment.slot_time)).all())
    return [{"hour": h, "appointments": rows.get(h, 0)} for h in range(24)]


@router.get("/frequent-no-shows")
def frequent_no_shows(db: Session = Depends(get_db)):
    since = date.today() - timedelta(days=90)
    rows = (db.query(User.id, User.name, User.email, func.count(Appointment.id))
            .join(Appointment, Appointment.patient_id == User.id)
            .filter(Appointment.status == NO_SHOW, Appointment.appointment_date >= since)
            .group_by(User.id, User.name, User.email).having(func.count(Appointment.id) >= 3).all())
    return [{"patient_id": i, "name": n, "email": e, "no_show_count": c} for i, n, e, c in rows]
