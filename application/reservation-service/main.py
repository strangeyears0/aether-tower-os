"""Aether Tower OS – reservation-service (FastAPI + SQLAlchemy async)."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import Any

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Path, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import and_, case, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database import engine, get_session, init_db, office_today
from models import (
    DESKS_PER_FLOOR,
    TOTAL_FLOORS,
    Reservation,
    Resource,
    User,
    make_coordinate,
)
from schemas import (
    FloorMap,
    FloorSummary,
    HealthOut,
    Meta,
    ReservationCreate,
    ReservationOut,
    ResourceStatus,
    UserOut,
)

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("reservation-service")

NOTIFICATION_SERVICE_URL = os.getenv("NOTIFICATION_SERVICE_URL", "http://localhost:8001").rstrip("/")
MAX_RESERVATIONS_PER_USER_PER_DAY = int(os.getenv("MAX_RESERVATIONS_PER_USER_PER_DAY", "1"))
BOOKING_HORIZON_DAYS = int(os.getenv("BOOKING_HORIZON_DAYS", "30"))
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    app.state.http = httpx.AsyncClient(timeout=httpx.Timeout(3.0))
    try:
        yield
    finally:
        await app.state.http.aclose()
        await engine.dispose()


app = FastAPI(
    title="Aether Tower OS – Reservation Service",
    description="REST API rezerwacji stanowisk pracy w Aether Tower (100 pięter x 150 biurek).",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helpery
# ---------------------------------------------------------------------------
def api_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _summary(floor_id: int, total: int, reserved: int, maintenance: int) -> FloorSummary:
    reserved, maintenance = int(reserved or 0), int(maintenance or 0)
    return FloorSummary(
        floor_id=floor_id,
        total=total,
        reserved=reserved,
        maintenance=maintenance,
        available=max(total - reserved - maintenance, 0),
        occupancy_pct=round(reserved / total * 100, 1) if total else 0.0,
    )


def _resource_status_query(day: date):
    """Zasób + (opcjonalna) rezerwacja na dany dzień + nazwa użytkownika."""
    return (
        select(
            Resource,
            Reservation.id.label("reservation_id"),
            Reservation.user_id.label("reserved_by_id"),
            User.full_name.label("reserved_by"),
        )
        .outerjoin(
            Reservation,
            and_(Reservation.resource_id == Resource.id, Reservation.reservation_date == day),
        )
        .outerjoin(User, User.id == Reservation.user_id)
    )


def _to_resource_status(row: Any) -> ResourceStatus:
    res: Resource = row.Resource
    desk_number = int(res.id[-3:])
    if res.status == "maintenance":
        status = "maintenance"
    elif row.reservation_id is not None:
        status = "occupied"
    else:
        status = "free"
    return ResourceStatus(
        id=res.id,
        floor_id=res.floor_id,
        desk_number=desk_number,
        zone=res.zone,
        name=res.name,
        type=res.type,
        svg_element_id=res.svg_element_id,
        coordinate=make_coordinate(res.floor_id, res.zone, desk_number),
        equipment=res.equipment or {},
        status=status,
        reservation_id=row.reservation_id,
        reserved_by_id=row.reserved_by_id,
        reserved_by=row.reserved_by,
    )


def _to_reservation_out(reservation: Reservation, resource: Resource) -> ReservationOut:
    return ReservationOut(
        id=reservation.id,
        user_id=reservation.user_id,
        resource_id=reservation.resource_id,
        reservation_date=reservation.reservation_date,
        created_at=reservation.created_at,
        floor_id=resource.floor_id,
        zone=resource.zone,
        coordinate=make_coordinate(resource.floor_id, resource.zone, int(resource.id[-3:])),
    )


def _validate_booking_date(day: date) -> None:
    today = office_today()
    if day < today:
        raise api_error(422, "date_in_past", "Nie można rezerwować stanowisk na datę z przeszłości.")
    if day > today + timedelta(days=BOOKING_HORIZON_DAYS):
        raise api_error(422, "date_too_far", f"Rezerwacje są dostępne maksymalnie {BOOKING_HORIZON_DAYS} dni naprzód.")


async def _notify(app: FastAPI, kind: str, user: User, resource: Resource, reservation: Reservation) -> None:
    """Best-effort powiadomienie – awaria user-notification-service nie blokuje rezerwacji."""
    payload = {
        "type": kind,
        "user_id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "resource_id": resource.id,
        "coordinate": make_coordinate(resource.floor_id, resource.zone, int(resource.id[-3:])),
        "reservation_id": reservation.id,
        "reservation_date": reservation.reservation_date.isoformat(),
    }
    try:
        response = await app.state.http.post(f"{NOTIFICATION_SERVICE_URL}/api/notifications", json=payload)
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Notification dispatch failed (%s): %s", kind, exc)


# ---------------------------------------------------------------------------
# Health / meta
# ---------------------------------------------------------------------------
@app.get("/health", tags=["ops"], summary="Liveness probe")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "reservation-service"}


async def _readiness(session: AsyncSession) -> HealthOut:
    try:
        await session.execute(text("SELECT 1"))
        return HealthOut(status="ok", database="up")
    except Exception as exc:  # noqa: BLE001
        logger.error("Readiness check failed: %s", exc)
        return HealthOut(status="degraded", database="down")


@app.get("/ready", response_model=HealthOut, tags=["ops"], summary="Readiness probe (sprawdza bazę danych)")
async def ready(session: AsyncSession = Depends(get_session)) -> HealthOut:
    result = await _readiness(session)
    if result.database == "down":
        raise HTTPException(status_code=503, detail=result.model_dump())
    return result


@app.get("/api/health", response_model=HealthOut, tags=["ops"], include_in_schema=False)
async def api_health(session: AsyncSession = Depends(get_session)) -> HealthOut:
    return await ready(session)


@app.get("/api/meta", response_model=Meta, tags=["meta"])
async def meta() -> Meta:
    today = office_today()
    return Meta(
        today=today,
        max_date=today + timedelta(days=BOOKING_HORIZON_DAYS),
        timezone=os.getenv("OFFICE_TIMEZONE", "Europe/Warsaw"),
        total_floors=TOTAL_FLOORS,
        desks_per_floor=DESKS_PER_FLOOR,
    )


# ---------------------------------------------------------------------------
# Piętra i zasoby
# ---------------------------------------------------------------------------
@app.get("/api/floors", response_model=list[FloorSummary], tags=["floors"])
async def list_floors(
    day: date | None = Query(None, alias="date", description="Data (domyślnie dziś)"),
    session: AsyncSession = Depends(get_session),
) -> list[FloorSummary]:
    """Zagregowana zajętość wszystkich pięter (lewy panel UI) – jedno zapytanie SQL."""
    day = day or office_today()
    stmt = (
        select(
            Resource.floor_id,
            func.count(func.distinct(Resource.id)).label("total"),
            func.coalesce(func.sum(case((Resource.status == "maintenance", 1), else_=0)), 0).label("maintenance"),
            func.count(Reservation.id).label("reserved"),
        )
        .select_from(Resource)
        .outerjoin(
            Reservation,
            and_(Reservation.resource_id == Resource.id, Reservation.reservation_date == day),
        )
        .group_by(Resource.floor_id)
        .order_by(Resource.floor_id)
    )
    rows = (await session.execute(stmt)).all()
    return [_summary(r.floor_id, r.total, r.reserved, r.maintenance) for r in rows]


@app.get("/api/floors/{floor_id}/resources", response_model=FloorMap, tags=["floors"])
async def floor_resources(
    floor_id: int = Path(ge=1, le=TOTAL_FLOORS),
    day: date | None = Query(None, alias="date", description="Data (domyślnie dziś)"),
    session: AsyncSession = Depends(get_session),
) -> FloorMap:
    """Mapa piętra: 150 stanowisk wraz ze statusem na dany dzień (lazy loading po wyborze piętra)."""
    day = day or office_today()
    rows = (
        await session.execute(
            _resource_status_query(day).where(Resource.floor_id == floor_id).order_by(Resource.id)
        )
    ).all()
    if not rows:
        raise api_error(404, "floor_not_found", f"Piętro {floor_id} nie istnieje lub nie zostało zasilone danymi.")
    resources = [_to_resource_status(r) for r in rows]
    reserved = sum(1 for r in resources if r.status == "occupied")
    maintenance = sum(1 for r in resources if r.status == "maintenance")
    return FloorMap(
        floor_id=floor_id,
        reservation_date=day,
        summary=_summary(floor_id, len(resources), reserved, maintenance),
        resources=resources,
    )


@app.get("/api/resources/{resource_id}", response_model=ResourceStatus, tags=["resources"])
async def get_resource(
    resource_id: str = Path(pattern=r"^F\d{3}-D\d{3}$"),
    day: date | None = Query(None, alias="date"),
    session: AsyncSession = Depends(get_session),
) -> ResourceStatus:
    day = day or office_today()
    row = (await session.execute(_resource_status_query(day).where(Resource.id == resource_id))).first()
    if row is None:
        raise api_error(404, "resource_not_found", f"Zasób {resource_id} nie istnieje.")
    return _to_resource_status(row)


# ---------------------------------------------------------------------------
# Użytkownicy
# ---------------------------------------------------------------------------
@app.get("/api/users", response_model=list[UserOut], tags=["users"])
async def list_users(
    limit: int = Query(500, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[User]:
    return list((await session.scalars(select(User).order_by(User.id).limit(limit).offset(offset))).all())


@app.get("/api/users/{user_id}", response_model=UserOut, tags=["users"])
async def get_user(user_id: str, session: AsyncSession = Depends(get_session)) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise api_error(404, "user_not_found", f"Użytkownik {user_id} nie istnieje.")
    return user


@app.get("/api/users/{user_id}/reservations", response_model=list[ReservationOut], tags=["users"])
async def user_reservations(
    user_id: str,
    from_date: date | None = Query(None, description="Domyślnie dziś (rezerwacje nadchodzące)"),
    session: AsyncSession = Depends(get_session),
) -> list[ReservationOut]:
    from_date = from_date or office_today()
    rows = (
        await session.execute(
            select(Reservation, Resource)
            .join(Resource, Resource.id == Reservation.resource_id)
            .where(Reservation.user_id == user_id, Reservation.reservation_date >= from_date)
            .order_by(Reservation.reservation_date, Reservation.resource_id)
        )
    ).all()
    return [_to_reservation_out(r, res) for r, res in rows]


# ---------------------------------------------------------------------------
# Rezerwacje
# ---------------------------------------------------------------------------
@app.post("/api/reservations", response_model=ReservationOut, status_code=201, tags=["reservations"])
async def create_reservation(
    payload: ReservationCreate,
    background: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> ReservationOut:
    _validate_booking_date(payload.reservation_date)

    user = await session.get(User, payload.user_id)
    if user is None:
        raise api_error(404, "user_not_found", f"Użytkownik {payload.user_id} nie istnieje.")
    resource = await session.get(Resource, payload.resource_id)
    if resource is None:
        raise api_error(404, "resource_not_found", f"Zasób {payload.resource_id} nie istnieje.")
    if resource.status == "maintenance":
        raise api_error(409, "resource_maintenance", "Stanowisko jest w trakcie konserwacji.")

    user_count = await session.scalar(
        select(func.count())
        .select_from(Reservation)
        .where(Reservation.user_id == user.id, Reservation.reservation_date == payload.reservation_date)
    )
    if (user_count or 0) >= MAX_RESERVATIONS_PER_USER_PER_DAY:
        raise api_error(409, "user_limit_reached", "Masz już rezerwację na wybrany dzień.")

    reservation = Reservation(
        user_id=user.id, resource_id=resource.id, reservation_date=payload.reservation_date
    )
    session.add(reservation)
    try:
        await session.commit()
    except IntegrityError:
        # Naruszenie unique_resource_reservation_per_day – ktoś był szybszy.
        await session.rollback()
        raise api_error(409, "resource_already_reserved", "To stanowisko zostało już zarezerwowane na wybrany dzień.")
    await session.refresh(reservation)

    background.add_task(_notify, app, "reservation_confirmed", user, resource, reservation)
    return _to_reservation_out(reservation, resource)


@app.delete("/api/reservations/{reservation_id}", status_code=204, response_class=Response, tags=["reservations"])
async def cancel_reservation(
    reservation_id: int,
    background: BackgroundTasks,
    user_id: str = Query(..., description="Właściciel rezerwacji"),
    session: AsyncSession = Depends(get_session),
) -> Response:
    reservation = await session.get(Reservation, reservation_id)
    if reservation is None:
        raise api_error(404, "reservation_not_found", f"Rezerwacja {reservation_id} nie istnieje.")
    if reservation.user_id != user_id:
        raise api_error(403, "not_owner", "Możesz anulować tylko własne rezerwacje.")
    user = await session.get(User, reservation.user_id)
    resource = await session.get(Resource, reservation.resource_id)
    await session.delete(reservation)
    await session.commit()
    if user is not None and resource is not None:
        background.add_task(_notify, app, "reservation_cancelled", user, resource, reservation)
    return Response(status_code=204)
