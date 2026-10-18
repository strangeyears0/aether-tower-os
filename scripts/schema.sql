-- Aether Tower OS – referencyjny DDL (PostgreSQL 14+).
-- Montowany w docker-compose do /docker-entrypoint-initdb.d, a jednocześnie
-- odzwierciedlony w modelach SQLAlchemy (application/reservation-service/models.py).

CREATE TABLE IF NOT EXISTS resources (
    id              VARCHAR(16)  PRIMARY KEY,                 -- np. 'F042-D114'
    floor_id        INTEGER      NOT NULL,
    zone            VARCHAR(16)  NOT NULL,                    -- Alpha | Beta | Gamma | Delta
    name            VARCHAR(64)  NOT NULL,
    type            VARCHAR(32)  NOT NULL,
    svg_element_id  VARCHAR(32)  NOT NULL,
    status          VARCHAR(16)  NOT NULL DEFAULT 'active',   -- active | maintenance
    equipment       JSONB        NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT ck_resources_status CHECK (status IN ('active', 'maintenance')),
    CONSTRAINT ck_resources_floor  CHECK (floor_id BETWEEN 1 AND 100)
);
CREATE INDEX IF NOT EXISTS ix_resources_floor_zone ON resources (floor_id, zone);

CREATE TABLE IF NOT EXISTS users (
    id         VARCHAR(32)  PRIMARY KEY,
    full_name  VARCHAR(120) NOT NULL,
    email      VARCHAR(254) NOT NULL,
    CONSTRAINT users_email_key UNIQUE (email)
);

CREATE TABLE IF NOT EXISTS reservations (
    id                SERIAL       PRIMARY KEY,
    user_id           VARCHAR(32)  NOT NULL REFERENCES users (id)     ON DELETE CASCADE,
    resource_id       VARCHAR(16)  NOT NULL REFERENCES resources (id) ON DELETE CASCADE,
    reservation_date  DATE         NOT NULL,
    created_at        TIMESTAMP    NOT NULL DEFAULT now(),
    -- Ograniczenie zapobiegające podwójnej rezerwacji tego samego biurka w danym dniu.
    CONSTRAINT unique_resource_reservation_per_day UNIQUE (resource_id, reservation_date)
);
CREATE INDEX IF NOT EXISTS ix_reservations_date      ON reservations (reservation_date);
CREATE INDEX IF NOT EXISTS ix_reservations_user_date ON reservations (user_id, reservation_date);
