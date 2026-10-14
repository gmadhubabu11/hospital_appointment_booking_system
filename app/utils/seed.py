"""Creates demo data: python -m app.utils.seed"""
import os
from datetime import time

from app.auth.security import hash_password
from app.database import SessionLocal
from app.models import Department, Doctor, Schedule, User
from app.utils.constants import ADMIN, DAYS, DOCTOR, PATIENT


def get_or_create_user(db, name, email, role, password):
    u = db.query(User).filter(User.email == email).first()
    if not u:
        u = User(name=name, email=email, phone="9999999999", password_hash=hash_password(password), role=role)
        db.add(u)
        db.flush()
    return u


def main():
    db = SessionLocal()
    get_or_create_user(db, "Admin", os.getenv("ADMIN_EMAIL", "admin@hospital.com"), ADMIN, os.getenv("ADMIN_PASSWORD", "Admin@123"))
    get_or_create_user(db, "Test Patient", "patient@hospital.com", PATIENT, "Patient@123")
    duser = get_or_create_user(db, "Ravi Kumar", "doctor@hospital.com", DOCTOR, "Doctor@123")
    dept = db.query(Department).filter(Department.name == "Cardiology").first() or Department(name="Cardiology", description="Heart care")
    db.add(dept)
    db.flush()
    if not db.query(Doctor).filter(Doctor.user_id == duser.id).first():
        doc = Doctor(user_id=duser.id, name="Ravi Kumar", department_id=dept.id, specialization="Cardiologist",
                     qualification="MBBS, MD", experience_years=10, consultation_fee=500, slot_duration_minutes=15)
        db.add(doc)
        db.flush()
        for day in DAYS:
            db.add(Schedule(doctor_id=doc.id, day_of_week=day, start_time=time(9), end_time=time(17),
                            break_start=time(13), break_end=time(14)))
    db.commit()
    db.close()
    print("Seeded: admin@hospital.com / Admin@123, doctor@hospital.com / Doctor@123, patient@hospital.com / Patient@123")


if __name__ == "__main__":
    main()
