from sqlalchemy import Boolean, Column, Date, ForeignKey, Integer, Numeric, String, Time, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.base import TimestampMixin


class Department(Base, TimestampMixin):
    __tablename__ = "departments"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(String(255))

    doctors = relationship("Doctor", back_populates="department")


class Doctor(Base, TimestampMixin):
    __tablename__ = "doctors"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    specialization = Column(String(100), nullable=False)
    qualification = Column(String(150), nullable=False)
    experience_years = Column(Integer, nullable=False)
    consultation_fee = Column(Numeric(10, 2), nullable=False)
    slot_duration_minutes = Column(Integer, nullable=False, default=15)
    is_active = Column(Boolean, default=True, nullable=False)

    user = relationship("User", back_populates="doctor_profile")
    department = relationship("Department", back_populates="doctors")
    schedules = relationship("Schedule", back_populates="doctor", cascade="all, delete-orphan")
    leaves = relationship("Leave", back_populates="doctor", cascade="all, delete-orphan")
    appointments = relationship("Appointment", back_populates="doctor")


class Schedule(Base, TimestampMixin):
    __tablename__ = "schedules"
    id = Column(Integer, primary_key=True)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=False)
    day_of_week = Column(String(10), nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    break_start = Column(Time)
    break_end = Column(Time)

    doctor = relationship("Doctor", back_populates="schedules")


class Leave(Base, TimestampMixin):
    __tablename__ = "leaves"
    __table_args__ = (UniqueConstraint("doctor_id", "leave_date", name="uq_doctor_leave"),)
    id = Column(Integer, primary_key=True)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=False)
    leave_date = Column(Date, nullable=False)
    reason = Column(String(255))

    doctor = relationship("Doctor", back_populates="leaves")
