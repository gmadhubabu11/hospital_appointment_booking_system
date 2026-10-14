import logging
from datetime import date, datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from app.database import SessionLocal
from app.models import Appointment, Consultation
from app.services import email_service as mail
from app.services.appointments import set_status
from app.utils.constants import BOOKED, NO_SHOW
from app.websockets.manager import notify, queue_changed

logger = logging.getLogger("jobs")
scheduler = BackgroundScheduler()


def reminder_job():
    db = SessionLocal()
    try:
        now = datetime.now()
        rows = db.query(Appointment).filter(
            Appointment.status == BOOKED, Appointment.reminder_sent.is_(False),
            Appointment.appointment_date.in_([now.date(), (now + timedelta(hours=24)).date()])).all()
        for a in rows:
            if now < datetime.combine(a.appointment_date, a.slot_time) <= now + timedelta(hours=24):
                to, subject, body = mail.reminder_mail(a)
                if mail.send_email(to, subject, body):  # flag set only on success so a failed mail retries next hour
                    a.reminder_sent = True
        db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("reminder_job failed")
        db.rollback()
    finally:
        db.close()


def no_show_job():
    db = SessionLocal()
    try:
        cutoff = datetime.now() - timedelta(minutes=30)
        rows = db.query(Appointment).filter(Appointment.status == BOOKED, Appointment.appointment_date <= date.today()).all()
        doctors = set()
        for a in rows:
            if datetime.combine(a.appointment_date, a.slot_time) < cutoff:
                set_status(db, a, NO_SHOW, None, "Auto: not checked in within 30 minutes")
                doctors.add((a.doctor_id, a.appointment_date, a.patient_id, a.appointment_number))
        db.commit()
        for doctor_id, d, patient_id, number in doctors:
            notify(patient_id, "no_show", f"Appointment {number} marked as No-Show")
            if d == date.today():
                queue_changed(doctor_id)
    except Exception:  # noqa: BLE001
        logger.exception("no_show_job failed")
        db.rollback()
    finally:
        db.close()


def followup_job():
    db = SessionLocal()
    try:
        tomorrow = date.today() + timedelta(days=1)
        rows = db.query(Consultation).filter(Consultation.follow_up_date == tomorrow,
                                             Consultation.follow_up_sent.is_(False)).all()
        for c in rows:
            to, subject, body = mail.followup_mail(c.appointment, c.follow_up_date)
            if mail.send_email(to, subject, body):
                c.follow_up_sent = True
        db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("followup_job failed")
        db.rollback()
    finally:
        db.close()


def start_scheduler():
    if scheduler.running:
        return
    scheduler.add_job(reminder_job, "interval", hours=1, id="reminder", replace_existing=True)
    scheduler.add_job(no_show_job, "interval", minutes=15, id="no_show", replace_existing=True)
    scheduler.add_job(followup_job, "cron", hour=9, minute=0, id="followup", replace_existing=True)
    scheduler.start()


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
