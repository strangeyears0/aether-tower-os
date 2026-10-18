#!/usr/bin/env python3
"""Aether Tower OS – skrypt zasilający bazę danych.

Tworzy:
  * 15 000 stanowisk (100 pięter x 150 biurek, strefy Alpha-Delta),
  * 300 użytkowników (U-0001 … U-0299 + konto demo U-0300),
  * 200-300 rezerwacji na DZISIEJSZY dzień (domyślnie 280) – nierównomiernie
    rozłożonych, tak by część pięter miała wyraźną zajętość (Piętro 42 ≈ 40 %),
    a mapa wybranego piętra pokazywała zarówno zielone, jak i czerwone biurka.

Skrypt jest idempotentny. Użycie:
    python scripts/seed.py                 # zasila brakujące dane
    python scripts/seed.py --reset         # czyści tabele i zasila od nowa
    python scripts/seed.py --reservations 250 --seed 7

Połączenie z bazą wynika ze zmiennych DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD
(brak DB_HOST => lokalny plik SQLite), identycznie jak w reservation-service.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import random
import sys
import time
from collections import defaultdict
from pathlib import Path


def _bootstrap_path() -> None:
    """Dodaje do sys.path katalog z modelami reservation-service (repo lub kontener)."""
    here = Path(__file__).resolve().parent
    candidates = [
        os.getenv("RESERVATION_SERVICE_PATH"),
        here.parent / "application" / "reservation-service",
        Path("/app"),
        Path.cwd(),
    ]
    for candidate in candidates:
        if candidate and (Path(candidate) / "models.py").is_file():
            sys.path.insert(0, str(candidate))
            return
    raise SystemExit("Nie znaleziono models.py – ustaw RESERVATION_SERVICE_PATH.")


_bootstrap_path()

from sqlalchemy import delete, func, insert, select  # noqa: E402

from database import SessionLocal, engine, init_db, office_today  # noqa: E402
from models import (  # noqa: E402
    DESKS_PER_FLOOR,
    TOTAL_FLOORS,
    ZONE_LAYOUT,
    Reservation,
    Resource,
    User,
    make_resource_id,
    zone_for_desk,
)

CHUNK = 1000
USER_COUNT = 300
DEMO_USER_ID = "U-0300"
SHOWCASE_FLOOR = 42
MAINTENANCE_RATE = 0.012
SHOWCASE_MAINTENANCE_DESKS = {7, 58, 129}  # gwarantuje bursztynowe stanowiska na piętrze-pokazie

FIRST_NAMES = [
    "Jan", "Anna", "Piotr", "Katarzyna", "Marek", "Magdalena", "Tomasz", "Agnieszka", "Pawel", "Ewa",
    "Michal", "Joanna", "Krzysztof", "Monika", "Lukasz", "Natalia", "Adam", "Karolina", "Bartosz", "Zofia",
]
LAST_NAMES = [
    "Nowak", "Kowalski", "Wisniewski", "Wojcik", "Kaminski", "Lewandowski", "Zielinski", "Szymanski",
    "Wozniak", "Dabrowski", "Kozlowski", "Jankowski", "Mazur", "Kwiatkowski", "Krawczyk",
]


def chunks(items: list, size: int = CHUNK):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def build_resource_rows(rng: random.Random) -> list[dict]:
    rows: list[dict] = []
    for floor in range(1, TOTAL_FLOORS + 1):
        for desk in range(1, DESKS_PER_FLOOR + 1):
            cfg = zone_for_desk(desk)
            rid = make_resource_id(floor, desk)
            rows.append(
                {
                    "id": rid,
                    "floor_id": floor,
                    "zone": cfg["zone"],
                    "name": f"{cfg['zone']} Desk {desk:03d}",
                    "type": cfg["type"],
                    "svg_element_id": f"svg-{rid}",
                    "status": (
                        "maintenance"
                        if rng.random() < MAINTENANCE_RATE
                        or (floor == SHOWCASE_FLOOR and desk in SHOWCASE_MAINTENANCE_DESKS)
                        else "active"
                    ),
                    "equipment": cfg["equipment"],
                }
            )
    return rows


def build_user_rows() -> list[dict]:
    rows = []
    for i in range(1, USER_COUNT):
        first = FIRST_NAMES[i % len(FIRST_NAMES)]
        last = LAST_NAMES[(i // len(FIRST_NAMES)) % len(LAST_NAMES)]
        rows.append(
            {
                "id": f"U-{i:04d}",
                "full_name": f"{first} {last}",
                "email": f"{first.lower()}.{last.lower()}.{i:04d}@aether-tower.io",
            }
        )
    rows.append({"id": DEMO_USER_ID, "full_name": "Demo Operator", "email": "demo.operator@aether-tower.io"})
    return rows


async def seed_table(session, model, rows: list[dict], label: str) -> int:
    existing = set((await session.scalars(select(model.id))).all())
    missing = [r for r in rows if r["id"] not in existing]
    for part in chunks(missing):
        await session.execute(insert(model), part)
    await session.commit()
    print(f"  • {label}: +{len(missing)} nowych (łącznie {len(existing) + len(missing)})")
    return len(missing)


async def seed_reservations(session, rng: random.Random, wanted: int) -> None:
    today = office_today()
    existing = await session.scalar(
        select(func.count()).select_from(Reservation).where(Reservation.reservation_date == today)
    )
    if existing:
        print(f"  • rezerwacje na {today}: już istnieje {existing} – pomijam (użyj --reset)")
        return

    rows = (await session.execute(select(Resource.id, Resource.floor_id).where(Resource.status == "active"))).all()
    by_floor: dict[int, list[str]] = defaultdict(list)
    for rid, floor in rows:
        by_floor[floor].append(rid)
    for desks in by_floor.values():
        desks.sort()

    users = sorted((await session.scalars(select(User.id).where(User.id != DEMO_USER_ID))).all())
    wanted = min(wanted, len(users))

    # Wagi pięter: piętro-pokaz najbardziej obłożone, 9 "gorących" pięter, reszta sporadycznie.
    floors = list(range(1, TOTAL_FLOORS + 1))
    hot = set(rng.sample([f for f in floors if f != SHOWCASE_FLOOR], 9))
    weights = [60 if f == SHOWCASE_FLOOR else 16 if f in hot else 1 for f in floors]

    reservations: list[dict] = []
    while len(reservations) < wanted:
        floor = rng.choices(floors, weights)[0]
        pool = by_floor[floor]
        if not pool:
            continue
        rid = pool.pop(rng.randrange(len(pool)))
        reservations.append(
            {"user_id": users[len(reservations)], "resource_id": rid, "reservation_date": today}
        )

    for part in chunks(reservations):
        await session.execute(insert(Reservation), part)
    await session.commit()

    per_floor: dict[int, int] = defaultdict(int)
    for r in reservations:
        per_floor[int(r["resource_id"][1:4])] += 1
    top = sorted(per_floor.items(), key=lambda kv: -kv[1])[:5]
    print(f"  • rezerwacje na {today}: +{len(reservations)}")
    print("    najbardziej obłożone piętra: " + ", ".join(f"FL-{f} ({n}/150)" for f, n in top))


async def main(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    rng = random.Random(args.seed)
    print(f"Aether Tower OS seed → {engine.url.render_as_string(hide_password=True)}")
    await init_db()

    async with SessionLocal() as session:
        if args.reset:
            print("  • --reset: czyszczenie tabel")
            for model in (Reservation, Resource, User):
                await session.execute(delete(model))
            await session.commit()

        await seed_table(session, Resource, build_resource_rows(rng), "resources")
        await seed_table(session, User, build_user_rows(), "users")
        await seed_reservations(session, rng, args.reservations)

        total = await session.scalar(select(func.count()).select_from(Resource))
        print(f"Gotowe w {time.perf_counter() - started:.1f}s — zasoby w bazie: {total}")
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="usuń istniejące dane przed zasileniem")
    parser.add_argument("--reservations", type=int, default=280, help="liczba rezerwacji na dziś (domyślnie 280)")
    parser.add_argument("--seed", type=int, default=42, help="ziarno generatora losowego (deterministyczne dane)")
    asyncio.run(main(parser.parse_args()))
