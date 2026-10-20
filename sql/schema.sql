-- PitWall Analytics: database schema (SQLite dialect; portable to PostgreSQL
-- with minor changes: INTEGER PRIMARY KEY -> SERIAL, REAL -> DOUBLE PRECISION).
-- Times are stored in seconds (REAL) so pace maths needs no parsing.

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------- dimensions

CREATE TABLE IF NOT EXISTS drivers (
    driver_id     TEXT PRIMARY KEY,          -- Jolpica id, e.g. 'max_verstappen'
    code          TEXT,                      -- 3-letter code, e.g. 'VER'
    number        INTEGER,
    given_name    TEXT NOT NULL,
    family_name   TEXT NOT NULL,
    nationality   TEXT,
    date_of_birth TEXT
);

CREATE TABLE IF NOT EXISTS teams (
    team_id     TEXT PRIMARY KEY,            -- Jolpica constructorId, e.g. 'red_bull'
    name        TEXT NOT NULL,
    nationality TEXT
);

CREATE TABLE IF NOT EXISTS circuits (
    circuit_id  TEXT PRIMARY KEY,            -- e.g. 'monza'
    name        TEXT NOT NULL,
    locality    TEXT,
    country     TEXT,
    latitude    REAL,
    longitude   REAL
);

-- ---------------------------------------------------------------- events

CREATE TABLE IF NOT EXISTS races (
    race_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    season      INTEGER NOT NULL,
    round       INTEGER NOT NULL,
    name        TEXT NOT NULL,               -- e.g. 'Italian Grand Prix'
    circuit_id  TEXT NOT NULL REFERENCES circuits(circuit_id),
    race_date   TEXT NOT NULL,
    total_laps  INTEGER,
    UNIQUE (season, round)
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    race_id     INTEGER NOT NULL REFERENCES races(race_id),
    session_type TEXT NOT NULL CHECK (session_type IN
                  ('FP1','FP2','FP3','Q','SQ','S','R')),
    UNIQUE (race_id, session_type)
);

-- ---------------------------------------------------------------- results

CREATE TABLE IF NOT EXISTS results (
    result_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    race_id        INTEGER NOT NULL REFERENCES races(race_id),
    driver_id      TEXT    NOT NULL REFERENCES drivers(driver_id),
    team_id        TEXT    NOT NULL REFERENCES teams(team_id),
    grid           INTEGER,                  -- 0 = pit lane start
    finish_pos     INTEGER,                  -- NULL if not classified
    position_text  TEXT,                     -- 'R' for retired, etc.
    points         REAL,
    laps_completed INTEGER,
    status         TEXT,                     -- 'Finished', '+1 Lap', 'Engine', ...
    fastest_lap_rank INTEGER,
    UNIQUE (race_id, driver_id)
);

CREATE TABLE IF NOT EXISTS qualifying (
    qualifying_id INTEGER PRIMARY KEY AUTOINCREMENT,
    race_id       INTEGER NOT NULL REFERENCES races(race_id),
    driver_id     TEXT    NOT NULL REFERENCES drivers(driver_id),
    team_id       TEXT    NOT NULL REFERENCES teams(team_id),
    position      INTEGER,
    q1_s          REAL,
    q2_s          REAL,
    q3_s          REAL,
    UNIQUE (race_id, driver_id)
);

-- ---------------------------------------------------------------- laps

CREATE TABLE IF NOT EXISTS laps (
    lap_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   INTEGER NOT NULL REFERENCES sessions(session_id),
    driver_id    TEXT    NOT NULL REFERENCES drivers(driver_id),
    lap_number   INTEGER NOT NULL,
    lap_time_s   REAL,
    sector1_s    REAL,
    sector2_s    REAL,
    sector3_s    REAL,
    position     INTEGER,                    -- running position at end of lap
    stint        INTEGER,
    compound     TEXT,                       -- SOFT / MEDIUM / HARD / INTERMEDIATE / WET
    tyre_age     INTEGER,                    -- laps on this set (incl. used sets)
    fresh_tyre   INTEGER,                    -- 1 = new set, 0 = used
    is_pit_in    INTEGER NOT NULL DEFAULT 0,
    is_pit_out   INTEGER NOT NULL DEFAULT 0,
    track_status TEXT,                       -- FastF1 codes: 1 clear, 2 yellow, 4 SC, 5 red, 6 VSC, 7 VSC ending
    is_accurate  INTEGER,                    -- FastF1 IsAccurate flag
    is_clean     INTEGER NOT NULL DEFAULT 0, -- derived: usable for pace analysis
    UNIQUE (session_id, driver_id, lap_number)
);

CREATE INDEX IF NOT EXISTS idx_laps_session_driver ON laps(session_id, driver_id);

-- ---------------------------------------------------------------- strategy

CREATE TABLE IF NOT EXISTS pit_stops (
    pit_stop_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    race_id      INTEGER NOT NULL REFERENCES races(race_id),
    driver_id    TEXT    NOT NULL REFERENCES drivers(driver_id),
    stop_number  INTEGER NOT NULL,
    lap          INTEGER NOT NULL,
    duration_s   REAL,                       -- pit lane time as reported by Jolpica
    UNIQUE (race_id, driver_id, stop_number)
);

CREATE TABLE IF NOT EXISTS tire_stints (
    stint_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   INTEGER NOT NULL REFERENCES sessions(session_id),
    driver_id    TEXT    NOT NULL REFERENCES drivers(driver_id),
    stint        INTEGER NOT NULL,
    compound     TEXT,
    start_lap    INTEGER NOT NULL,
    end_lap      INTEGER NOT NULL,
    stint_length INTEGER NOT NULL,
    start_tyre_age INTEGER,                  -- >0 means a used set was fitted
    UNIQUE (session_id, driver_id, stint)
);

-- ---------------------------------------------------------------- conditions

CREATE TABLE IF NOT EXISTS weather (
    weather_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   INTEGER NOT NULL REFERENCES sessions(session_id),
    time_offset_s REAL NOT NULL,             -- seconds since session start
    air_temp_c   REAL,
    track_temp_c REAL,
    humidity     REAL,
    pressure     REAL,
    wind_speed   REAL,
    wind_direction REAL,
    rainfall     INTEGER                     -- 0 / 1
);

CREATE INDEX IF NOT EXISTS idx_weather_session ON weather(session_id);

CREATE TABLE IF NOT EXISTS race_events (
    event_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   INTEGER NOT NULL REFERENCES sessions(session_id),
    event_type   TEXT NOT NULL CHECK (event_type IN
                   ('SAFETY_CAR','VSC','RED_FLAG','YELLOW','PENALTY','OTHER')),
    start_lap    INTEGER,
    end_lap      INTEGER,
    driver_id    TEXT REFERENCES drivers(driver_id),  -- set for penalties
    detail       TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_session ON race_events(session_id);
