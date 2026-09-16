-- EL AL CRM - סכמת מסד נתונים (SQLite)

DROP TABLE IF EXISTS bookings;
DROP TABLE IF EXISTS flights;
DROP TABLE IF EXISTS customers;

CREATE TABLE customers (
    customer_id     INTEGER PRIMARY KEY,
    first_name      TEXT    NOT NULL,
    last_name       TEXT    NOT NULL,
    email           TEXT    NOT NULL UNIQUE,
    phone           TEXT    NOT NULL,
    passport        TEXT    NOT NULL UNIQUE,
    country         TEXT    NOT NULL,
    birth_date      TEXT    NOT NULL,
    matmid_tier     TEXT    NOT NULL,  -- Basic / Silver / Gold / Platinum / Top Platinum
    matmid_points   INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL
);

CREATE TABLE flights (
    flight_id       INTEGER PRIMARY KEY,
    flight_number   TEXT    NOT NULL,   -- LY001
    origin          TEXT    NOT NULL,   -- IATA
    destination     TEXT    NOT NULL,
    departure_time  TEXT    NOT NULL,   -- ISO
    arrival_time    TEXT    NOT NULL,
    aircraft_type   TEXT    NOT NULL,
    seats_business  INTEGER NOT NULL,
    seats_economy   INTEGER NOT NULL,
    price_business  REAL    NOT NULL,  -- ₪
    price_economy   REAL    NOT NULL,  -- ₪
    gate            TEXT,
    status          TEXT    NOT NULL    -- Scheduled/Delayed/Boarding/Departed/Landed/Cancelled
);

CREATE TABLE bookings (
    booking_id      INTEGER PRIMARY KEY,
    pnr             TEXT    NOT NULL UNIQUE,  -- קוד הזמנה בן 6 תווים
    customer_id     INTEGER NOT NULL REFERENCES customers(customer_id),
    flight_id       INTEGER NOT NULL REFERENCES flights(flight_id),
    booking_date    TEXT    NOT NULL,
    cabin_class     TEXT    NOT NULL,   -- Economy / Business
    seat            TEXT,
    baggage_count   INTEGER NOT NULL DEFAULT 0,
    price_paid      REAL    NOT NULL,  -- ₪
    status          TEXT    NOT NULL,   -- Confirmed/CheckedIn/Cancelled/Completed/NoShow
    agent_notes     TEXT
);

CREATE INDEX idx_flights_dep    ON flights(departure_time);
CREATE INDEX idx_flights_status ON flights(status);
CREATE INDEX idx_book_flight    ON bookings(flight_id);
CREATE INDEX idx_book_customer  ON bookings(customer_id);
CREATE INDEX idx_book_status    ON bookings(status);
