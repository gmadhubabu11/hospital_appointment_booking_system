from datetime import date, time, datetime
from decimal import Decimal
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

DayName = Literal["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
SlotMinutes = Literal[10, 15, 20, 30]


class DepartmentIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: Optional[str] = Field(default=None, max_length=255)


class DepartmentOut(DepartmentIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class DoctorCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    phone: str = Field(pattern=r"^\d{10}$")
    password: str = Field(min_length=8, max_length=64)
    department_id: int
    specialization: str = Field(min_length=2, max_length=100)
    qualification: str = Field(min_length=2, max_length=150)
    experience_years: int = Field(ge=0)
    consultation_fee: Decimal = Field(gt=0)
    slot_duration_minutes: SlotMinutes = 15


class DoctorUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    department_id: Optional[int] = None
    specialization: Optional[str] = Field(default=None, min_length=2, max_length=100)
    qualification: Optional[str] = Field(default=None, min_length=2, max_length=150)
    experience_years: Optional[int] = Field(default=None, ge=0)
    consultation_fee: Optional[Decimal] = Field(default=None, gt=0)
    slot_duration_minutes: Optional[SlotMinutes] = None
    is_active: Optional[bool] = None


class DoctorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    name: str
    department_id: int
    specialization: str
    qualification: str
    experience_years: int
    consultation_fee: Decimal
    slot_duration_minutes: int
    is_active: bool


class ScheduleIn(BaseModel):
    day_of_week: DayName
    start_time: time
    end_time: time
    break_start: Optional[time] = None
    break_end: Optional[time] = None

    @model_validator(mode="after")
    def check_times(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        if (self.break_start is None) != (self.break_end is None):
            raise ValueError("break_start and break_end must be given together")
        if self.break_start is not None:
            if self.break_end <= self.break_start:
                raise ValueError("break_end must be after break_start")
            if self.break_start < self.start_time or self.break_end > self.end_time:
                raise ValueError("break must be inside working hours")
        return self


class ScheduleOut(ScheduleIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    doctor_id: int


class LeaveIn(BaseModel):
    leave_date: date
    reason: Optional[str] = Field(default=None, max_length=255)


class LeaveOut(LeaveIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    doctor_id: int


class SlotsOut(BaseModel):
    doctor_id: int
    date: date
    slot_duration_minutes: int
    slots: list[str]
