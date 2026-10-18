# Aether Tower OS — System Rezerwacji Zasobów Biurowych

Konsola NOC do rezerwacji **15 000 stanowisk** (100 pięter × 150 biurek, strefy Alpha / Beta / Gamma / Delta).

```
┌────────────┐   /api/*    ┌─────────────────────┐   async SQLAlchemy   ┌────────────┐
│  frontend  │ ──────────▶ │  reservation-service │ ───────────────────▶ │ PostgreSQL │
│ NGINX :8080│  (proxy)    │  FastAPI        :8000│                      └────────────┘
└────────────┘             └──────────┬──────────┘
                                      │ HTTP (best-effort, w tle)
                                      ▼
                           ┌──────────────────────────┐
                           │ user-notification-service │  FastAPI :8001
                           └──────────────────────────┘
```

## Szybki start (jedno polecenie)

```bash
docker compose up --build
```

Kolejność startu: `postgres` → `user-notification-service` → `reservation-service` → `seed` (jednorazowo: 15 000 stanowisk, 300 użytkowników, 280 rezerwacji na dziś) → `frontend`.

| Usługa | Adres |
|---|---|
| **Aether Tower OS (UI)** | http://localhost:8080 |
| Reservation API + Swagger | http://localhost:8000/docs |
| Notification API + Swagger | http://localhost:8001/docs |
| PostgreSQL | `localhost:5432` (domyślnie `aether` / `aether_dev_password`) |

Ponowne zasilenie od zera: `docker compose run --rm seed python /scripts/seed.py --reset`.

## Uruchomienie lokalne bez Dockera (SQLite)

Bez `DB_HOST` aplikacja używa pliku SQLite (`application/reservation-service/aether_local.db`).

```bash
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r application/reservation-service/requirements.txt -r application/user-notification-service/requirements.txt

python scripts/seed.py                                    # zasilenie bazy
cd application/user-notification-service && uvicorn main:app --port 8001 &
cd application/reservation-service        && uvicorn main:app --port 8000 &
cd application/frontend && python -m http.server 3000     # UI: http://localhost:3000/?api=http://localhost:8000/api
```

## Konfiguracja (zmienne środowiskowe)

**reservation-service**

| Zmienna | Domyślnie | Opis |
|---|---|---|
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | – | PostgreSQL (asyncpg). Brak `DB_HOST` ⇒ SQLite (`SQLITE_PATH`). |
| `DB_POOL_SIZE`, `DB_MAX_OVERFLOW` | `10`, `10` | Pula połączeń PostgreSQL |
| `NOTIFICATION_SERVICE_URL` | `http://localhost:8001` | Adres user-notification-service |
| `OFFICE_TIMEZONE` | `Europe/Warsaw` | Strefa wyznaczająca „dzisiaj” |
| `BOOKING_HORIZON_DAYS` | `30` | Maks. wyprzedzenie rezerwacji |
| `MAX_RESERVATIONS_PER_USER_PER_DAY` | `1` | Limit rezerwacji użytkownika na dzień |
| `CORS_ORIGINS` | `*` | Lista oddzielona przecinkami |

**user-notification-service**: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_STARTTLS`, `MAIL_FROM` (bez `SMTP_HOST` powiadomienia są logowane – kanał `log`).

**frontend**: `API_UPSTREAM` (domyślnie `http://reservation-service:8000`) – podstawiane do `nginx.conf` przez `envsubst`.

## API (reservation-service)

| Metoda | Ścieżka | Opis |
|---|---|---|
| GET | `/api/meta` | Dzisiejsza data, horyzont rezerwacji |
| GET | `/api/floors?date=` | Zajętość 100 pięter (jedno zapytanie agregujące) |
| GET | `/api/floors/{1-100}/resources?date=` | Mapa piętra – 150 stanowisk ze statusem (`free` / `occupied` / `maintenance`) |
| GET | `/api/resources/{id}?date=` | Szczegóły stanowiska, np. `F042-D114` |
| GET | `/api/users`, `/api/users/{id}`, `/api/users/{id}/reservations` | Użytkownicy i ich rezerwacje |
| POST | `/api/reservations` | `{user_id, resource_id, reservation_date}` → `201` / `409` (konflikt) |
| DELETE | `/api/reservations/{id}?user_id=` | Anulowanie (`204`) |
| GET | `/health`, `/ready` | Sondy liveness / readiness (K8s) |

Podwójna rezerwacja jest blokowana na poziomie bazy: `CONSTRAINT unique_resource_reservation_per_day UNIQUE (resource_id, reservation_date)` – równoległe żądania kończą się `409`, nie błędem 500.

## Model danych

DDL referencyjny: [`scripts/schema.sql`](scripts/schema.sql) (montowany do PostgreSQL przy pierwszym starcie), odpowiadające mu modele: [`models.py`](application/reservation-service/models.py).

Identyfikatory: `F042-D114` = piętro 42, biurko 114. Strefy na piętrze: **Alpha** 1–30, **Beta** 31–70, **Gamma** 71–110, **Delta** 111–150.

Odstępstwa od minimalnego DDL: tabela `resources` ma dodatkową kolumnę `status` (`active` / `maintenance`) zasilającą stan *Amber Telemetry* (ok. 1,2 % biurek jest w konserwacji; seed nie rezerwuje ich).

## Seed (`scripts/seed.py`)

Idempotentny; deterministyczny (`--seed 42`). 280 rezerwacji na dziś jest rozłożonych nierównomiernie (Piętro 42 ≈ 40 %, 9 „gorących” pięter ≈ 10 %, reszta sporadycznie), dzięki czemu lista pięter i mapy są zróżnicowane. Opcje: `--reset`, `--reservations N` (≤ 299), `--seed N`. Konto demo w UI: `U-0300` (bez rezerwacji).

## Kubernetes / AWS EKS — gotowość obrazów

- bezstanowe serwisy (skalowalne przez HPA), konfiguracja wyłącznie przez zmienne środowiskowe (`ConfigMap` / `Secret` / External Secrets dla RDS),
- sondy: `GET /health` (liveness), `GET /ready` (readiness, sprawdza bazę), frontend: `GET /healthz`,
- obrazy działają jako nie-root (`appuser` UID 10001, NGINX unprivileged na porcie 8080) – zgodne z `runAsNonRoot` i Pod Security Standards,
- `init_db()` używa blokady doradczej PostgreSQL, więc równoległy start wielu replik jest bezpieczny,
- w klastrze ruch `/api/*` można kierować przez Ingress (ALB) do `reservation-service`, albo zostawić proxy w NGINX ustawiając `API_UPSTREAM=http://reservation-service.<ns>.svc.cluster.local:8000`.
