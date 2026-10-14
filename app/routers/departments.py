from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, require_roles
from app.database import get_db
from app.models import Department, Doctor, User
from app.schemas.hospital import DepartmentIn, DepartmentOut
from app.utils.constants import ADMIN

router = APIRouter(prefix="/departments", tags=["Departments"])


def _get(db, department_id):
    dept = db.get(Department, department_id)
    if not dept:
        raise HTTPException(404, "Department not found")
    return dept


@router.post("", response_model=DepartmentOut, status_code=201)
def create(data: DepartmentIn, db: Session = Depends(get_db), _: User = Depends(require_roles(ADMIN))):
    if db.query(Department).filter(Department.name == data.name).first():
        raise HTTPException(409, "Department name already exists")
    dept = Department(**data.model_dump())
    db.add(dept)
    db.commit()
    db.refresh(dept)
    return dept


@router.get("", response_model=List[DepartmentOut])
def list_all(skip: int = 0, limit: int = 20, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(Department).order_by(Department.name).offset(skip).limit(min(limit, 100)).all()


@router.put("/{department_id}", response_model=DepartmentOut)
def update(department_id: int, data: DepartmentIn, db: Session = Depends(get_db),
           _: User = Depends(require_roles(ADMIN))):
    dept = _get(db, department_id)
    if db.query(Department).filter(Department.name == data.name, Department.id != department_id).first():
        raise HTTPException(409, "Department name already exists")
    dept.name, dept.description = data.name, data.description
    db.commit()
    db.refresh(dept)
    return dept


@router.delete("/{department_id}")
def delete(department_id: int, db: Session = Depends(get_db), _: User = Depends(require_roles(ADMIN))):
    dept = _get(db, department_id)
    if db.query(Doctor).filter(Doctor.department_id == department_id, Doctor.is_active.is_(True)).first():
        raise HTTPException(409, "Department has active doctors and cannot be deleted")
    if db.query(Doctor).filter(Doctor.department_id == department_id).first():
        raise HTTPException(409, "Department still has inactive doctors; reassign them first")
    db.delete(dept)
    db.commit()
    return {"message": "Department deleted"}
