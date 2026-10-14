from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field

Phone = Field(pattern=r"^\d{10}$", description="10 digit phone number")


class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    phone: str = Phone
    password: str = Field(min_length=8, max_length=64)
     

class LoginIn(BaseModel):
    email: EmailStr
    password: str


class RefreshIn(BaseModel):
    refresh_token: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AccessOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    email: EmailStr
    phone: str
    role: str
    is_active: bool
    created_at: datetime
