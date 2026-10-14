import logging
import smtplib
from email.message import EmailMessage

from app import config

logger = logging.getLogger("email")


def send_email(to: str, subject: str, body: str) -> bool:
    """Send an email. Never raises: failures are logged so the main action still succeeds."""
    try:
        if not config.SMTP_HOST or not config.SMTP_USER:
            raise RuntimeError("SMTP is not configured")
        msg = EmailMessage()
        msg["From"] = config.SMTP_FROM or config.SMTP_USER
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as server:
            server.starttls()
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("Email to %s failed: %s", to, exc)
        return False


def _fmt(appt):
    return (f"Appointment No : {appt.appointment_number}\nDoctor         : Dr. {appt.doctor.name}\n"
            f"Date           : {appt.appointment_date}\nTime           : {appt.slot_time.strftime('%H:%M')}\n"
            f"Token          : {appt.token_number}")


def booked_mail(appt):
    return appt.patient.email, "Appointment Confirmed", f"Hi {appt.patient.name},\n\nYour appointment is booked.\n\n{_fmt(appt)}"


def rescheduled_mail(appt):
    return appt.patient.email, "Appointment Rescheduled", f"Hi {appt.patient.name},\n\nYour appointment was rescheduled.\n\n{_fmt(appt)}"


def cancelled_mail(appt):
    return appt.patient.email, "Appointment Cancelled", f"Hi {appt.patient.name},\n\nYour appointment was cancelled.\n\n{_fmt(appt)}"


def leave_cancel_mail(appt):
    return (appt.patient.email, "Appointment Cancelled - Doctor on Leave",
            f"Hi {appt.patient.name},\n\nDr. {appt.doctor.name} is on leave, so your appointment was cancelled. "
            f"Please book a new slot.\n\n{_fmt(appt)}")


def completed_mail(appt, follow_up):
    extra = f"\nFollow-up date: {follow_up}" if follow_up else ""
    return (appt.patient.email, "Consultation Completed",
            f"Hi {appt.patient.name},\n\nYour consultation with Dr. {appt.doctor.name} is completed.{extra}\n\n{_fmt(appt)}")


def reminder_mail(appt):
    return appt.patient.email, "Appointment Reminder", f"Hi {appt.patient.name},\n\nReminder: appointment within 24 hours.\n\n{_fmt(appt)}"


def followup_mail(appt, follow_up):
    return (appt.patient.email, "Follow-up Reminder",
            f"Hi {appt.patient.name},\n\nYour follow-up with Dr. {appt.doctor.name} is due tomorrow ({follow_up}).")
