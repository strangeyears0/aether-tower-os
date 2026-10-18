"""Aether Tower OS – user-notification-service.

Mikrousługa przyjmuje zdarzenia z reservation-service i wysyła powiadomienia
(e-mail przez SMTP, gdy ustawiono ``SMTP_HOST``; w przeciwnym razie kanał ``log``).
Historia ostatnich powiadomień jest przechowywana w pamięci (serwis bezstanowy).
"""
from __future__ import annotations

import asyncio
import logging
import os
import smtplib
import uuid
from collections import deque
from datetime import date, datetime, timezone
from email.message import EmailMessage
from typing import Literal

from fastapi import FastAPI, Query
from pydantic import BaseModel, Field

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("user-notification-service")

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_STARTTLS = os.getenv("SMTP_STARTTLS", "true").lower() == "true"
MAIL_FROM = os.getenv("MAIL_FROM", "no-reply@aether-tower.io")
HISTORY_SIZE = int(os.getenv("HISTORY_SIZE", "500"))

app = FastAPI(
    title="Aether Tower OS – User Notification Service",
    description="Wysyłanie powiadomień o rezerwacjach stanowisk.",
    version="1.0.0",
)

NotificationType = Literal["reservation_confirmed", "reservation_cancelled"]


class NotificationIn(BaseModel):
    type: NotificationType
    user_id: str
    full_name: str
    email: str
    resource_id: str = Field(examples=["F042-D114"])
    coordinate: str | None = Field(default=None, examples=["FL-42.ZONE-DELTA.DESK-114"])
    reservation_id: int | None = None
    reservation_date: date


class NotificationOut(BaseModel):
    id: str
    type: NotificationType
    channel: Literal["email", "log"]
    status: Literal["sent", "failed"]
    recipient: str
    subject: str
    body: str
    created_at: datetime
    error: str | None = None


HISTORY: deque[NotificationOut] = deque(maxlen=HISTORY_SIZE)


def render_message(n: NotificationIn) -> tuple[str, str]:
    desk = n.coordinate or n.resource_id
    if n.type == "reservation_confirmed":
        subject = f"[Aether Tower] Potwierdzenie rezerwacji {n.resource_id}"
        body = (
            f"Cześć {n.full_name},\n\n"
            f"Twoje stanowisko {desk} ({n.resource_id}) zostało zarezerwowane na {n.reservation_date:%Y-%m-%d}.\n"
            "Miłej pracy w Aether Tower!\n"
        )
    else:
        subject = f"[Aether Tower] Anulowano rezerwację {n.resource_id}"
        body = (
            f"Cześć {n.full_name},\n\n"
            f"Rezerwacja stanowiska {desk} ({n.resource_id}) na {n.reservation_date:%Y-%m-%d} została anulowana.\n"
        )
    return subject, body


def _send_smtp(recipient: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = MAIL_FROM, recipient, subject
    msg.set_content(body)
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as smtp:
        if SMTP_STARTTLS:
            smtp.starttls()
        if SMTP_USER and SMTP_PASSWORD:
            smtp.login(SMTP_USER, SMTP_PASSWORD)
        smtp.send_message(msg)


@app.get("/health", tags=["ops"], summary="Liveness probe")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "user-notification-service"}


@app.get("/ready", tags=["ops"], summary="Readiness probe")
async def ready() -> dict[str, str]:
    return {"status": "ok", "channel": "email" if SMTP_HOST else "log"}


@app.post("/api/notifications", response_model=NotificationOut, status_code=202, tags=["notifications"])
async def send_notification(payload: NotificationIn) -> NotificationOut:
    subject, body = render_message(payload)
    channel: Literal["email", "log"] = "email" if SMTP_HOST else "log"
    status: Literal["sent", "failed"] = "sent"
    error: str | None = None

    if channel == "email":
        try:
            await asyncio.to_thread(_send_smtp, payload.email, subject, body)
        except Exception as exc:  # noqa: BLE001
            status, error = "failed", str(exc)
            logger.error("SMTP delivery to %s failed: %s", payload.email, exc)
    else:
        logger.info("NOTIFY [%s] to=%s subject=%r", payload.type, payload.email, subject)

    record = NotificationOut(
        id=str(uuid.uuid4()),
        type=payload.type,
        channel=channel,
        status=status,
        recipient=payload.email,
        subject=subject,
        body=body,
        created_at=datetime.now(timezone.utc),
        error=error,
    )
    HISTORY.appendleft(record)
    return record


@app.get("/api/notifications", response_model=list[NotificationOut], tags=["notifications"])
async def list_notifications(
    limit: int = Query(50, ge=1, le=500),
    user_email: str | None = Query(None, description="Filtruj po adresie odbiorcy"),
) -> list[NotificationOut]:
    items = [n for n in HISTORY if user_email is None or n.recipient == user_email]
    return items[:limit]
