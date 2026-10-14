import uuid
from datetime import date
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, require_roles
from app.config import MAX_FILE_SIZE, UPLOAD_DIR
from app.database import get_db
from app.models import Appointment, Consultation, UploadedFile, User
from app.routers.appointments import assert_view, get_appt
from app.schemas.appointment import ConsultationIn, ConsultationOut, FileOut, HistoryItem
from app.services import email_service as mail
from app.services.appointments import set_status
from app.utils.constants import ADMIN, ALLOWED_EXT, COMPLETED, DOCTOR, FILE_TYPES, IN_CONSULT, PATIENT
from app.websockets.manager import notify, queue_changed

router = APIRouter(tags=["Consultation & Files"])


@router.post("/appointments/{appointment_id}/consultation", response_model=ConsultationOut, status_code=201)
def write_consultation(appointment_id: int, data: ConsultationIn, background: BackgroundTasks,
                       db: Session = Depends(get_db), user: User = Depends(require_roles(DOCTOR))):
    a = get_appt(db, appointment_id)
    if a.doctor.user_id != user.id:
        raise HTTPException(403, "Only the doctor of this appointment can write the consultation")
    if a.status != IN_CONSULT:
        raise HTTPException(400, "Consultation can be written only when the status is In Consultation")
    if db.query(Consultation).filter(Consultation.appointment_id == a.id).first():
        raise HTTPException(409, "Consultation already exists")
    if data.follow_up_date and data.follow_up_date <= date.today():
        raise HTTPException(400, "Follow-up date must be in the future")
    c = Consultation(appointment_id=a.id, symptoms=data.symptoms, diagnosis=data.diagnosis,
                     prescription=[p.model_dump() for p in data.prescription], advice=data.advice,
                     follow_up_date=data.follow_up_date)
    db.add(c)
    set_status(db, a, COMPLETED, user.id, "Consultation saved")
    db.commit()
    db.refresh(c)
    db.refresh(a)
    to, subject, body = mail.completed_mail(a, data.follow_up_date)
    background.add_task(mail.send_email, to, subject, body)
    notify(a.patient_id, "consultation_completed", "Your consultation is completed")
    queue_changed(a.doctor_id)
    return c


@router.get("/appointments/{appointment_id}/consultation", response_model=ConsultationOut)
def get_consultation(appointment_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    a = get_appt(db, appointment_id)
    assert_view(user, a)
    if not a.consultation:
        raise HTTPException(404, "Consultation not found")
    return a.consultation


@router.post("/appointments/{appointment_id}/files", response_model=FileOut, status_code=201)
async def upload_file(appointment_id: int, file: UploadFile = File(...), file_type: str = Form(None),
                      db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    a = get_appt(db, appointment_id)
    if user.role == ADMIN:
        raise HTTPException(403, "Admins cannot upload files")
    assert_view(user, a)
    if user.role == PATIENT:
        file_type = "Lab Report"
    elif file_type not in ("Prescription", "Scan"):
        raise HTTPException(422, "Doctors must set file_type to Prescription or Scan")
    ext = "." + (file.filename or "").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else ""
    if ext not in ALLOWED_EXT or file.content_type not in set(ALLOWED_EXT.values()):
        raise HTTPException(415, "Only PDF, JPG and PNG files are allowed")
    content = await file.read(MAX_FILE_SIZE + 1)
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(413, "File is larger than 5 MB")
    stored = f"{uuid.uuid4().hex}{ext}"
    UPLOAD_DIR.mkdir(exist_ok=True)
    (UPLOAD_DIR / stored).write_bytes(content)
    rec = UploadedFile(appointment_id=a.id, uploaded_by=user.id, file_type=file_type, original_name=file.filename,
                       stored_name=stored, size_kb=max(1, len(content) // 1024))
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


@router.get("/appointments/{appointment_id}/files", response_model=List[FileOut])
def list_files(appointment_id: int, skip: int = 0, limit: int = 20, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    a = get_appt(db, appointment_id)
    assert_view(user, a)
    return db.query(UploadedFile).filter(UploadedFile.appointment_id == a.id).offset(skip).limit(min(limit, 100)).all()


@router.get("/files/{file_id}/download")
def download(file_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rec = db.get(UploadedFile, file_id)
    if not rec:
        raise HTTPException(404, "File not found")
    assert_view(user, rec.appointment)
    path = UPLOAD_DIR / rec.stored_name
    if not path.exists():
        raise HTTPException(404, "File missing on server")
    return FileResponse(path, filename=rec.original_name)


@router.get("/patients/me/history", response_model=List[HistoryItem])
def my_history(skip: int = 0, limit: int = 20, db: Session = Depends(get_db), user: User = Depends(require_roles(PATIENT))):
    appts = (db.query(Appointment).filter(Appointment.patient_id == user.id)
             .order_by(Appointment.appointment_date.desc(), Appointment.slot_time.desc())
             .offset(skip).limit(min(limit, 100)).all())
    return [HistoryItem(appointment=a, consultation=a.consultation, files=a.files) for a in appts]
