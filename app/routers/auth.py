from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, require_roles
from app.auth.security import (create_access_token, create_refresh_token, decode_token, find_refresh_row,
                               hash_password, verify_password)
from app.database import get_db
from app.models import User
from app.schemas.auth import AccessOut, LoginIn, RefreshIn, RegisterIn, TokenOut, UserOut
from app.utils.constants import ADMIN, PATIENT

router = APIRouter(prefix="/auth", tags=["Auth"])


def _create_user(db: Session, data: RegisterIn, role: str) -> User:
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(409, "Email already registered")
    user = User(name=data.name, email=data.email, phone=data.phone, password_hash=hash_password(data.password), role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/register", response_model=UserOut, status_code=201)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    """Public registration always creates a Patient."""
    return _create_user(db, data, PATIENT)


@router.post("/admin-users", response_model=UserOut, status_code=201)
def create_admin(data: RegisterIn, db: Session = Depends(get_db), _: User = Depends(require_roles(ADMIN))):
    return _create_user(db, data, ADMIN)


@router.post("/login", response_model=TokenOut)
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")
    if not user.is_active:
        raise HTTPException(403, "Account is inactive")
    access = create_access_token(user)
    refresh = create_refresh_token(user, db)
    db.commit()
    return TokenOut(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=AccessOut)
def refresh(data: RefreshIn, db: Session = Depends(get_db)):
    payload = decode_token(data.refresh_token, "refresh")
    row = find_refresh_row(db, data.refresh_token)
    if row is None or row.revoked or row.expires_at < datetime.utcnow():
        raise HTTPException(401, "Refresh token is revoked or expired")
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(401, "User not found or inactive")
    return AccessOut(access_token=create_access_token(user))


@router.post("/logout")
def logout(data: RefreshIn, db: Session = Depends(get_db)):
    decode_token(data.refresh_token, "refresh")
    row = find_refresh_row(db, data.refresh_token)
    if row is None or row.revoked:
        raise HTTPException(401, "Refresh token is already revoked or unknown")
    row.revoked = True
    db.commit()
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
