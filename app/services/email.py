import json
import logging
import smtplib
from email.message import EmailMessage
from urllib.request import Request, urlopen

from app.core.config import settings


logger = logging.getLogger(__name__)


class EmailConfigurationError(RuntimeError):
    pass


def _log_dev_email(to_email: str, name: str, code: str, reason: str) -> None:
    """Write a reset email to the log instead of sending it.

    Only used when EMAIL_DEV_MODE is enabled, so a developer can exercise the
    password reset flow without an EmailJS or SMTP account.
    """
    logger.warning(
        "EMAIL_DEV_MODE is on (%s). No email was sent.\n"
        "    To: %s\n"
        "    Name: %s\n"
        "    Reset code: %s (expires in 10 minutes)",
        reason,
        to_email,
        name,
        code,
    )


def send_password_reset_email(to_email: str, name: str, code: str) -> None:
    if settings.SMTP_HOST and settings.SMTP_FROM_EMAIL:
        if bool(settings.SMTP_USERNAME) != bool(settings.SMTP_PASSWORD):
            raise EmailConfigurationError(
                "Set both SMTP_USERNAME and SMTP_PASSWORD, or leave both empty, "
                "in the backend .env file."
            )

        message = EmailMessage()
        message["Subject"] = "TECHNOVA password reset code"
        message["From"] = settings.SMTP_FROM_EMAIL
        message["To"] = to_email
        message.set_content(
            f"Hello {name},\n\n"
            f"Your TECHNOVA password reset code is {code}.\n"
            "It expires in 10 minutes. If you did not request this, ignore this email."
        )

        smtp_class = smtplib.SMTP_SSL if settings.SMTP_USE_SSL else smtplib.SMTP
        with smtp_class(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as smtp:
            if settings.SMTP_USE_TLS and not settings.SMTP_USE_SSL:
                smtp.starttls()
            if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            smtp.send_message(message)
        return

    emailjs_config = (
        settings.EMAILJS_SERVICE_ID,
        settings.EMAILJS_TEMPLATE_ID,
        settings.EMAILJS_PUBLIC_KEY,
    )
    if not all(emailjs_config):
        if settings.EMAIL_DEV_MODE:
            _log_dev_email(to_email, name, code, "no email provider configured")
            return
        raise EmailConfigurationError(
            "Password reset email is not configured. Set EMAILJS_SERVICE_ID, "
            "EMAILJS_TEMPLATE_ID, and EMAILJS_PUBLIC_KEY in the backend "
            "environment, or configure SMTP."
        )

    payload = {
        "service_id": settings.EMAILJS_SERVICE_ID,
        "template_id": settings.EMAILJS_TEMPLATE_ID,
        "user_id": settings.EMAILJS_PUBLIC_KEY,
        "template_params": {
            "to_email": to_email,
            "to_name": name or "Customer",
            "name": name or "Customer",
            "verification_code": code,
            "expiry_minutes": "10",
        },
    }
    request = Request(
        "https://api.emailjs.com/api/v1.0/email/send",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        if not 200 <= response.status < 300:
            raise RuntimeError(f"EmailJS returned HTTP {response.status}")
