"""Envío del email vía Resend (API transaccional).

Requiere RESEND_API_KEY. El remitente (MAIL_FROM) debe usar un dominio
verificado en Resend, salvo el sandbox onboarding@resend.dev para pruebas.
"""
from __future__ import annotations

import datetime as dt
import os

from config import MAIL_FROM, MAIL_TO, MAIL_SUBJECT_PREFIX


def send_email(html_body: str, text_body: str) -> dict:
    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        raise RuntimeError("Falta RESEND_API_KEY en el entorno.")

    import resend

    resend.api_key = api_key
    subject = f"{MAIL_SUBJECT_PREFIX} — {dt.date.today().strftime('%d/%m/%Y')}"

    return resend.Emails.send(
        {
            "from": MAIL_FROM,
            "to": [MAIL_TO],
            "subject": subject,
            "html": html_body,
            "text": text_body,
        }
    )
