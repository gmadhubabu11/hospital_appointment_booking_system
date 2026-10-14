from sqlalchemy import (JSON, Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, Time,
                        UniqueConstraint, func)
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.base import TimestampMixin


class Appointment(Base, TimestampMixin):
    __tablename__ = "appointments"
    # slot_held is True while the slot is taken and NULL once cancelled. MySQL unique indexes allow many NULLs,
    # so a cancelled slot can be booked again while an active duplicate is blocked by the database itself.
    __table_args__ = (UniqueConstraint("doctor_id", "appointment_date", "slot_time", "slot_held", name="uq_doctor_slot"),)
    id = Column(Integer, primary_key=True)
    appointment_number = Column(String(30), unique=True, nullable=False)
    patient_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=False)
    appointment_date = Column(Date, nullable=False, index=True)
    slot_time = Column(Time, nullable=False)
    token_number = Column(Integer, nullable=False)
    reason = Column(String(255), nullable=False)
    status = Column(String(20), nullable=False, default="Booked")
    consultation_fee = Column(Numeric(10, 2), nullable=False)
    reschedule_count = Column(Integer, default=0, nullable=False)
    reminder_sent = Column(Boolean, default=False, nullable=False)
    slot_held = Column(Boolean, nullable=True, default=True)

    patient = relationship("User", back_populates="appointments")
    doctor = relationship("Doctor", back_populates="appointments")
    consultation = relationship("Consultation", back_populates="appointment", uselist=False)
    files = relationship("UploadedFile", back_populates="appointment")
    history = relationship("AppointmentHistory", back_populates="appointment")


class AppointmentHistory(Base, TimestampMixin):
    __tablename__ = "appointment_history"
    id = Column(Integer, primary_key=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), nullable=False)
    old_status = Column(String(20))
    new_status = Column(String(20), nullable=False)
    changed_by = Column(Integer, ForeignKey("users.id"))  # NULL = system job
    note = Column(String(255))
    changed_at = Column(DateTime, server_default=func.now(), nullable=False)

    appointment = relationship("Appointment", back_populates="history")


class Consultation(Base, TimestampMixin):
    __tablename__ = "consultations"
    id = Column(Integer, primary_key=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), unique=True, nullable=False)
    symptoms = Column(Text, nullable=False)
    diagnosis = Column(Text, nullable=False)
    prescription = Column(JSON, nullable=False)
    advice = Column(Text)
    follow_up_date = Column(Date)
    follow_up_sent = Column(Boolean, default=False, nullable=False)

    appointment = relationship("Appointment", back_populates="consultation")


class UploadedFile(Base, TimestampMixin):
    __tablename__ = "uploaded_files"
    id = Column(Integer, primary_key=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), nullable=False)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    file_type = Column(String(20), nullable=False)
    original_name = Column(String(255), nullable=False)
    stored_name = Column(String(255), unique=True, nullable=False)
    size_kb = Column(Integer, nullable=False)

    appointment = relationship("Appointment", back_populates="files")
