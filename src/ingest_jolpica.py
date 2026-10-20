"""Load race results, qualifying, pit stops and reference data from Jolpica-F1.

Usage:
    python -m src.ingest_jolpica 2024            # whole season
    python -m src.ingest_jolpica 2024 1          # a single round
"""
import sys
import time

import requests

from .config import JOLPICA_BASE, REQUEST_DELAY
from .db import get_connection, init_db

PAGE_SIZE = 100


def _get(path: str, params: dict | None = None) -> dict:
    """GET a Jolpica endpoint, retrying politely on rate limits."""
    url = f"{JOLPICA_BASE}/{path}.json"
    for attempt in range(5):
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code == 429:
            time.sleep(2 ** attempt)
            continue
        resp.raise_for_status()
        time.sleep(REQUEST_DELAY)
        return resp.json()["MRData"]
    raise RuntimeError(f"Rate limited too many times on {url}")


def _get_all(path: str, table_key: str) -> list[dict]:
    """Page through an endpoint and return the combined list of races."""
    races: dict[tuple, dict] = {}
    offset = 0
    while True:
        data = _get(path, {"limit": PAGE_SIZE, "offset": offset})
        for race in data["RaceTable"][table_key]:
            key = (race["season"], race["round"])
            if key in races:
                for list_key in ("Results", "QualifyingResults", "PitStops"):
                    if list_key in race:
                        races[key].setdefault(list_key, []).extend(race[list_key])
            else:
                races[key] = race
        offset += PAGE_SIZE
        if offset >= int(data["total"]):
            break
    return list(races.values())


def _seconds(text: str | None) -> float | None:
    """Convert '1:23.456' or '23.456' to seconds."""
    if not text:
        return None
    try:
        if ":" in text:
            minutes, rest = text.split(":", 1)
            return int(minutes) * 60 + float(rest)
        return float(text)
    except ValueError:
        return None


def _int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _upsert_reference(conn, race: dict) -> None:
    circuit = race["Circuit"]
    loc = circuit["Location"]
    conn.execute(
        """INSERT OR IGNORE INTO circuits
           (circuit_id, name, locality, country, latitude, longitude)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (circuit["circuitId"], circuit["circuitName"], loc.get("locality"),
         loc.get("country"), float(loc["lat"]), float(loc["long"])),
    )


def _upsert_driver_team(conn, entry: dict) -> None:
    d, c = entry["Driver"], entry["Constructor"]
    conn.execute(
        """INSERT OR IGNORE INTO drivers
           (driver_id, code, number, given_name, family_name, nationality, date_of_birth)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (d["driverId"], d.get("code"), _int(d.get("permanentNumber")),
         d["givenName"], d["familyName"], d.get("nationality"), d.get("dateOfBirth")),
    )
    conn.execute(
        "INSERT OR IGNORE INTO teams (team_id, name, nationality) VALUES (?, ?, ?)",
        (c["constructorId"], c["name"], c.get("nationality")),
    )


def _race_id(conn, race: dict, total_laps: int | None = None) -> int:
    conn.execute(
        """INSERT OR IGNORE INTO races
           (season, round, name, circuit_id, race_date, total_laps)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (int(race["season"]), int(race["round"]), race["raceName"],
         race["Circuit"]["circuitId"], race["date"], total_laps),
    )
    row = conn.execute(
        "SELECT race_id FROM races WHERE season = ? AND round = ?",
        (int(race["season"]), int(race["round"])),
    ).fetchone()
    return row["race_id"]


def load_results(conn, season: int, rnd: int | None) -> int:
    path = f"{season}/{rnd}/results" if rnd else f"{season}/results"
    races = _get_all(path, "Races")
    for race in races:
        _upsert_reference(conn, race)
        results = race.get("Results", [])
        total_laps = max((_int(r.get("laps")) or 0 for r in results), default=None)
        race_id = _race_id(conn, race, total_laps)
        # make sure the 'R' session exists
        conn.execute(
            "INSERT OR IGNORE INTO sessions (race_id, session_type) VALUES (?, 'R')",
            (race_id,),
        )
        for r in results:
            _upsert_driver_team(conn, r)
            conn.execute(
                """INSERT OR REPLACE INTO results
                   (race_id, driver_id, team_id, grid, finish_pos, position_text,
                    points, laps_completed, status, fastest_lap_rank)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (race_id, r["Driver"]["driverId"], r["Constructor"]["constructorId"],
                 _int(r.get("grid")), _int(r.get("position")), r.get("positionText"),
                 float(r.get("points", 0)), _int(r.get("laps")), r.get("status"),
                 _int(r.get("FastestLap", {}).get("rank"))),
            )
    return len(races)


def load_qualifying(conn, season: int, rnd: int | None) -> None:
    path = f"{season}/{rnd}/qualifying" if rnd else f"{season}/qualifying"
    for race in _get_all(path, "Races"):
        _upsert_reference(conn, race)
        race_id = _race_id(conn, race)
        conn.execute(
            "INSERT OR IGNORE INTO sessions (race_id, session_type) VALUES (?, 'Q')",
            (race_id,),
        )
        for q in race.get("QualifyingResults", []):
            _upsert_driver_team(conn, q)
            conn.execute(
                """INSERT OR REPLACE INTO qualifying
                   (race_id, driver_id, team_id, position, q1_s, q2_s, q3_s)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (race_id, q["Driver"]["driverId"], q["Constructor"]["constructorId"],
                 _int(q.get("position")), _seconds(q.get("Q1")),
                 _seconds(q.get("Q2")), _seconds(q.get("Q3"))),
            )


def load_pit_stops(conn, season: int, rnd: int | None) -> None:
    path = f"{season}/{rnd}/pitstops" if rnd else f"{season}/pitstops"
    for race in _get_all(path, "Races"):
        race_id = _race_id(conn, race)
        for p in race.get("PitStops", []):
            conn.execute(
                """INSERT OR REPLACE INTO pit_stops
                   (race_id, driver_id, stop_number, lap, duration_s)
                   VALUES (?, ?, ?, ?, ?)""",
                (race_id, p["driverId"], int(p["stop"]), int(p["lap"]),
                 _seconds(p.get("duration"))),
            )


def ingest(season: int, rnd: int | None = None) -> None:
    init_db()
    with get_connection() as conn:
        n = load_results(conn, season, rnd)
        print(f"{season}: loaded results for {n} race(s)")
        load_qualifying(conn, season, rnd)
        print(f"{season}: loaded qualifying")
        load_pit_stops(conn, season, rnd)
        print(f"{season}: loaded pit stops")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Usage: python -m src.ingest_jolpica <season> [round]")
    ingest(int(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else None)
