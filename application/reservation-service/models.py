"""Aether Tower OS – modele ORM (resources, users, reservations)."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database import Base

# JSONB w PostgreSQL, zwykły JSON (TEXT) w SQLite.
JSONType = JSON().with_variant(JSONB(), "postgresql")

TOTAL_FLOORS = 100
DESKS_PER_FLOOR = 150

# ---------------------------------------------------------------------------
# Układ stref piętra (150 stanowisk): Alpha 30 + Beta 40 + Gamma 40 + Delta 40.
# ---------------------------------------------------------------------------
_BASE_EQUIPMENT = {
    "monitors": "2x Monitor 4K",
    "chair": "Fotel Aeron (Herman Miller)",
    "desk": "Sit-Stand (biurko elektryczne)",
}

ZONE_LAYOUT: tuple[dict, ...] = (
    {
        "zone": "Alpha",
        "label": "Focus & Deep Work",
        "type": "focus_pod",
        "desks": range(1, 31),
        "equipment": {
            **_BASE_EQUIPMENT,
            "computer": "Workstation i9 / 64 GB RAM",
            "network": "10 GbE",
            "extras": ["Akustyczna kabina", "Słuchawki ANC", "Lampa Focus"],
        },
    },
    {
        "zone": "Beta",
        "label": "Collaboration & Project",
        "type": "collab_station",
        "desks": range(31, 71),
        "equipment": {
            **_BASE_EQUIPMENT,
            "computer": "Workstation i7 / 32 GB RAM",
            "network": "2.5 GbE",
            "extras": ["Tablica interaktywna", "Kamera 4K", "Zestaw wideokonferencyjny"],
        },
    },
    {
        "zone": "Gamma",
        "label": "Agile Teams",
        "type": "agile_desk",
        "desks": range(71, 111),
        "equipment": {
            **_BASE_EQUIPMENT,
            "computer": "Laptop dock i7 / 32 GB RAM",
            "network": "2.5 GbE",
            "extras": ["Kanban wall", "Strefa stand-up"],
        },
    },
    {
        "zone": "Delta",
        "label": "Hot Desks & Dual 4K",
        "type": "hot_desk",
        "desks": range(111, 151),
        "equipment": {
            **_BASE_EQUIPMENT,
            "monitors": "2x Monitor 4K (Dual)",
            "computer": "Thin client / 32 GB RAM",
            "network": "1 GbE",
            "extras": ["Stacja USB-C 100 W", "Szafka na rzeczy (locker)"],
        },
    },
)


def zone_for_desk(desk_number: int) -> dict:
    for cfg in ZONE_LAYOUT:
        if desk_number in cfg["desks"]:
            return cfg
    raise ValueError(f"Desk number out of range: {desk_number}")


def make_resource_id(floor_id: int, desk_number: int) -> str:
    """np. floor 42, desk 114 -> 'F042-D114'."""
    return f"F{floor_id:03d}-D{desk_number:03d}"


def make_coordinate(floor_id: int, zone: str, desk_number: int) -> str:
    """np. 'FL-42.ZONE-DELTA.DESK-114'."""
    return f"FL-{floor_id:02d}.ZONE-{zone.upper()}.DESK-{desk_number:03d}"


# ---------------------------------------------------------------------------
# Modele
# ---------------------------------------------------------------------------
class Resource(Base):
    """Stanowisko pracy (15 000 rekordów: 100 pięter x 150 biurek)."""

    __tablename__ = "resources"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    floor_id: Mapped[int] = mapped_column(Integer, nullable=False)
    zone: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    svg_element_id: Mapped[str] = mapped_column(String(32), nullable=False)
    # Rozszerzenie względem minimalnego DDL: 'active' | 'maintenance' (Amber Telemetry).
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", server_default="active")
    equipment: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)

    __table_args__ = (
        CheckConstraint("status IN ('active', 'maintenance')", name="ck_resources_status"),
        CheckConstraint("floor_id BETWEEN 1 AND 100", name="ck_resources_floor"),
        Index("ix_resources_floor_zone", "floor_id", "zone"),
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False)

    __table_args__ = (UniqueConstraint("email", name="users_email_key"),)


class Reservation(Base):
    __tablename__ = "reservations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # SERIAL
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    resource_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("resources.id", ondelete="CASCADE"), nullable=False
    )
    reservation_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        # Gwarancja braku podwójnej rezerwacji – egzekwowana przez bazę danych.
        UniqueConstraint("resource_id", "reservation_date", name="unique_resource_reservation_per_day"),
        Index("ix_reservations_date", "reservation_date"),
        Index("ix_reservations_user_date", "user_id", "reservation_date"),
    )
