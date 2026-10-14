from datetime import date, time, datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class AppointmentCreate(BaseModel):
    doctor_id: int
    appointment_date: date
    slot_time: time
    reason: str = Field(min_length=3, max_length=255)


class RescheduleIn(BaseModel):
    appointment_date: date
    slot_time: time


class AppointmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    appointment_number: str
    patient_id: int
    doctor_id: int
    appointment_date: date
    slot_time: time
    token_number: int
    reason: str
    status: str
    consultation_fee: Decimal
    reschedule_count: int


class PrescriptionItem(BaseModel):
    medicine: str = Field(min_length=1, max_length=100)
    dosage: str = Field(min_length=1, max_length=100)
    days: int = Field(gt=0, le=365)


class ConsultationIn(BaseModel):
    symptoms: str = Field(min_length=2)
    diagnosis: str = Field(min_length=2)
    prescription: list[PrescriptionItem] = Field(min_length=1)
    advice: Optional[str] = None
    follow_up_date: Optional[date] = None


class ConsultationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    appointment_id: int
    symptoms: str
    diagnosis: str
    prescription: list[PrescriptionItem]
    advice: Optional[str]
    follow_up_date: Optional[date]


class FileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    appointment_id: int
    uploaded_by: int
    file_type: str
    original_name: str
    stored_name: str
    size_kb: int
    created_at: datetime


class HistoryItem(BaseModel):
    appointment: AppointmentOut
    consultation: Optional[ConsultationOut] = None
    files: list[FileOut] = []
