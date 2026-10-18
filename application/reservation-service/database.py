"""Aether Tower OS – konfiguracja połączenia z bazą danych.

Silnik jest wybierany dynamicznie na podstawie zmiennych środowiskowych:

* ``DB_HOST`` (+ ``DB_PORT``, ``DB_NAME``, ``DB_USER``, ``DB_PASSWORD``)
  -> PostgreSQL (asyncpg) – środowisko Docker Compose / Kubernetes (AWS EKS / RDS),
* brak ``DB_HOST`` -> SQLite (aiosqlite) – lokalne środowisko deweloperskie.
"""
from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import event, text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger("reservation-service.db")

SQLITE_DEFAULT_PATH = Path(__file__).resolve().parent / "aether_local.db"
# Dowolna stała liczba całkowita – klucz blokady doradczej PostgreSQL dla init_db().
_SCHEMA_LOCK_KEY = 727_274


class Base(DeclarativeBase):
    """Bazowa klasa modeli ORM."""


def is_postgres() -> bool:
    return bool(os.getenv("DB_HOST"))


def build_database_url() -> URL:
    """Buduje URL połączenia na podstawie zmiennych środowiskowych."""
    host = os.getenv("DB_HOST")
    if host:
        return URL.create(
            drivername="postgresql+asyncpg",
            username=os.getenv("DB_USER", "aether"),
            password=os.getenv("DB_PASSWORD", ""),
            host=host,
            port=int(os.getenv("DB_PORT", "5432")),
            database=os.getenv("DB_NAME", "aether_tower"),
        )
    sqlite_path = Path(os.getenv("SQLITE_PATH", str(SQLITE_DEFAULT_PATH)))
    return URL.create(drivername="sqlite+aiosqlite", database=str(sqlite_path))


def _create_engine():
    url = build_database_url()
    if url.drivername.startswith("postgresql"):
        return create_async_engine(
            url,
            pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
            max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
            pool_pre_ping=True,
            pool_recycle=1800,
        )
    eng = create_async_engine(url)

    @event.listens_for(eng.sync_engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - zależne od sterownika
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return eng


engine = _create_engine()
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Zależność FastAPI – jedna sesja na żądanie."""
    async with SessionLocal() as session:
        yield session


async def init_db(retries: int = 30, delay: float = 2.0) -> None:
    """Tworzy tabele (jeśli nie istnieją). Czeka na gotowość bazy danych."""
    from models import Base as _Base  # noqa: F401  (rejestracja modeli w metadanych)

    for attempt in range(1, retries + 1):
        try:
            async with engine.begin() as conn:
                if is_postgres():
                    # Serializuje równoległy start wielu replik (HPA / rolling update).
                    await conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _SCHEMA_LOCK_KEY})
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Database ready (%s)", engine.url.render_as_string(hide_password=True))
            return
        except Exception as exc:  # noqa: BLE001
            if attempt == retries:
                raise
            logger.warning("Database not ready (%s/%s): %s", attempt, retries, exc)
            await asyncio.sleep(delay)


def office_today() -> date:
    """Dzisiejsza data w strefie czasowej biura (``OFFICE_TIMEZONE``)."""
    tz_name = os.getenv("OFFICE_TIMEZONE", "Europe/Warsaw")
    try:
        return datetime.now(ZoneInfo(tz_name)).date()
    except ZoneInfoNotFoundError:
        return datetime.utcnow().date()
