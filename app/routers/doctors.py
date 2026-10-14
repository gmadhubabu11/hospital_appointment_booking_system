from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, require_roles
from app.auth.security import hash_password
from app.database import get_db
from app.models import Appointment, Department, Doctor, User
from app.schemas.hospital import DoctorCreate, DoctorOut, DoctorUpdate
from app.utils.constants import ADMIN, BOOKED, CHECKED_IN, DOCTOR, IN_CONSULT

router = APIRouter(prefix="/doctors", tags=["Doctors"])


def get_doctor_or_404(db: Session, doctor_id: int) -> Doctor:
    doctor = db.get(Doctor, doctor_id)
    if not doctor:
        raise HTTPException(404, "Doctor not found")
    return doctor


def has_upcoming(db: Session, doctor_id: int) -> bool:
    now = datetime.now()
    rows = db.query(Appointment).filter(
        Appointment.doctor_id == doctor_id, Appointment.status.in_([BOOKED, CHECKED_IN, IN_CONSULT]),
        Appointment.appointment_date >= date.today()).all()
    return any(datetime.combine(a.appointment_date, a.slot_time) >= now or a.status == IN_CONSULT for a in rows)


@router.post("", response_model=DoctorOut, status_code=201)
def create(data: DoctorCreate, db: Session = Depends(get_db), _: User = Depends(require_roles(ADMIN))):
    if not db.get(Department, data.department_id):
        raise HTTPException(404, "Department not found")
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(409, "Email already registered")
    user = User(name=data.name, email=data.email, phone=data.phone, password_hash=hash_password(data.password),
                role=DOCTOR)
    db.add(user)
    db.flush()
    doctor = Doctor(user_id=user.id, **data.model_dump(exclude={"email", "phone", "password"}))
    db.add(doctor)
    db.commit()
    db.refresh(doctor)
    return doctor


@router.get("", response_model=List[DoctorOut])
def list_doctors(department_id: Optional[int] = None, specialization: Optional[str] = None, name: Optional[str] = None,
                 skip: int = 0, limit: int = 20, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Doctor)
    if user.role != ADMIN:
        q = q.filter(Doctor.is_active.is_(True))
    if department_id:
        q = q.filter(Doctor.department_id == department_id)
    if specialization:
        q = q.filter(Doctor.specialization.ilike(f"%{specialization}%"))
    if name:
        q = q.filter(Doctor.name.ilike(f"%{name}%"))
    return q.order_by(Doctor.name).offset(skip).limit(min(limit, 100)).all()


@router.get("/{doctor_id}", response_model=DoctorOut)
def get_one(doctor_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    doctor = get_doctor_or_404(db, doctor_id)
    if not doctor.is_active and user.role != ADMIN:
        raise HTTPException(404, "Doctor not found")
    return doctor


@router.put("/{doctor_id}", response_model=DoctorOut)
def update(doctor_id: int, data: DoctorUpdate, db: Session = Depends(get_db), _: User = Depends(require_roles(ADMIN))):
    doctor = get_doctor_or_404(db, doctor_id)
    changes = data.model_dump(exclude_unset=True)
    if changes.get("department_id") and not db.get(Department, changes["department_id"]):
        raise HTTPException(404, "Department not found")
    if changes.get("is_active") is False and has_upcoming(db, doctor_id):
        raise HTTPException(409, "Doctor has upcoming appointments and cannot be deactivated")
    for k, v in changes.items():
        setattr(doctor, k, v)
    if "name" in changes:
        doctor.user.name = changes["name"]
    if "is_active" in changes:
        doctor.user.is_active = changes["is_active"]
    db.commit()
    db.refresh(doctor)
    return doctor


@router.delete("/{doctor_id}")
def soft_delete(doctor_id: int, db: Session = Depends(get_db), _: User = Depends(require_roles(ADMIN))):
    doctor = get_doctor_or_404(db, doctor_id)
    if has_upcoming(db, doctor_id):
        raise HTTPException(409, "Doctor has upcoming appointments and cannot be deactivated")
    doctor.is_active = False
    doctor.user.is_active = False
    db.commit()
    return {"message": "Doctor deactivated"}
