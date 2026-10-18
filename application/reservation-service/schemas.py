"""Aether Tower OS – schematy Pydantic (kontrakt REST API)."""
from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

DeskStatus = Literal["free", "occupied", "maintenance"]


class Meta(BaseModel):
    today: dt.date
    max_date: dt.date
    timezone: str
    total_floors: int
    desks_per_floor: int


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    full_name: str
    email: str


class FloorSummary(BaseModel):
    floor_id: int
    total: int
    reserved: int
    maintenance: int
    available: int
    occupancy_pct: float = Field(description="Odsetek zajętych stanowisk (0-100)")


class ResourceStatus(BaseModel):
    id: str
    floor_id: int
    desk_number: int
    zone: str
    name: str
    type: str
    svg_element_id: str
    coordinate: str
    equipment: dict[str, Any]
    status: DeskStatus
    reservation_id: int | None = None
    reserved_by_id: str | None = None
    reserved_by: str | None = None


class FloorMap(BaseModel):
    floor_id: int
    reservation_date: dt.date
    summary: FloorSummary
    resources: list[ResourceStatus]


class ReservationCreate(BaseModel):
    user_id: str = Field(min_length=1, max_length=32, examples=["U-0300"])
    resource_id: str = Field(pattern=r"^F\d{3}-D\d{3}$", examples=["F042-D114"])
    reservation_date: dt.date


class ReservationOut(BaseModel):
    id: int
    user_id: str
    resource_id: str
    reservation_date: dt.date
    created_at: dt.datetime
    floor_id: int
    zone: str
    coordinate: str


class HealthOut(BaseModel):
    status: Literal["ok", "degraded"]
    service: str = "reservation-service"
    database: Literal["up", "down"]
