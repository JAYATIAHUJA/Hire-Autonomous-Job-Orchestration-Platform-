"""Pluggable delivery for login codes: the console in dev, SMTP in production."""

import logging
import smtplib
from email.message import EmailMessage
from typing import Protocol

from ..config import settings

logger = logging.getLogger("hire.auth.mailer")


class OtpSender(Protocol):
    def send(self, to: str, code: str) -> None: ...


def _body(code: str) -> str:
    return (
        f"Your Hire login code is {code}.\n\n"
        "It expires in 10 minutes. If you did not ask for it, ignore this email."
    )


class ConsoleSender:
    """Dev only: prints the code to the API log instead of emailing it."""

    def send(self, to: str, code: str) -> None:
        logger.warning("DEV login code for %s: %s", to, code)


class SmtpSender:
    def send(self, to: str, code: str) -> None:
        if not (settings.smtp_host and settings.smtp_from):
            raise RuntimeError("SMTP_HOST and SMTP_FROM must be set to email login codes.")
        msg = EmailMessage()
        msg["From"] = settings.smtp_from
        msg["To"] = to
        msg["Subject"] = f"{code} is your Hire login code"
        msg.set_content(_body(code))
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            if settings.smtp_starttls:
                smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)


def get_sender() -> OtpSender:
    choice = (settings.otp_sender or "").strip().lower() or ("console" if settings.env == "dev" else "smtp")
    if choice == "console":
        if settings.env != "dev":
            # Printing codes to a production log would let anyone with log access log in.
            raise RuntimeError("OTP_SENDER=console is only allowed when ENV=dev.")
        return ConsoleSender()
    return SmtpSender()
