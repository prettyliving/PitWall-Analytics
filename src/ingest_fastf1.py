"""Load lap-level data, tyre stints, weather and track status from FastF1.

Run ingest_jolpica first so the race, driver and session rows exist.

Usage:
    python -m src.ingest_fastf1 2024 1          # race session of round 1
    python -m src.ingest_fastf1 2024 1 Q        # qualifying of round 1
"""
import sys

import fastf1
import pandas as pd

from .config import FASTF1_CACHE
from .db import get_connection

# FastF1 TrackStatus codes: 1 clear, 2 yellow, 3 (unused), 4 safety car,
# 5 red flag, 6 VSC deployed, 7 VSC ending.
NEUTRALISED = {"2", "4", "5", "6", "7"}  # yellow, SC, red, VSC, VSC ending


def _is_clean(row: pd.Series) -> int:
    """A lap is usable for pace analysis if it is a flying, accurate,
    green-flag lap that is not lap 1 and not an in/out lap."""
    if pd.isna(row["lap_time_s"]) or row["lap_number"] == 1:
        return 0
    if row["is_pit_in"] or row["is_pit_out"]:
        return 0
    if pd.notna(row["is_accurate"]) and not row["is_accurate"]:
        return 0
    status = str(row["track_status"] or "")
    if any(ch in NEUTRALISED for ch in status):
        return 0
    return 1


def _driver_lookup(conn) -> dict[str, str]:
    rows = conn.execute("SELECT driver_id, code FROM drivers WHERE code IS NOT NULL")
    return {r["code"]: r["driver_id"] for r in rows}


def _session_id(conn, season: int, rnd: int, session_type: str) -> int:
    row = conn.execute(
        """SELECT s.session_id FROM sessions s
           JOIN races r ON r.race_id = s.race_id
           WHERE r.season = ? AND r.round = ? AND s.session_type = ?""",
        (season, rnd, session_type),
    ).fetchone()
    if row is None:
        raise SystemExit(
            f"No {session_type} session for {season} round {rnd}. "
            "Run ingest_jolpica first."
        )
    return row["session_id"]


def _build_laps(session, drivers: dict[str, str], session_id: int) -> pd.DataFrame:
    laps = session.laps.copy()
    df = pd.DataFrame({
        "session_id": session_id,
        "driver_id": laps["Driver"].map(drivers),
        "lap_number": laps["LapNumber"].astype(int),
        "lap_time_s": laps["LapTime"].dt.total_seconds(),
        "sector1_s": laps["Sector1Time"].dt.total_seconds(),
        "sector2_s": laps["Sector2Time"].dt.total_seconds(),
        "sector3_s": laps["Sector3Time"].dt.total_seconds(),
        "position": laps["Position"],
        "stint": laps["Stint"],
        "compound": laps["Compound"],
        "tyre_age": laps["TyreLife"],
        "fresh_tyre": laps["FreshTyre"].map({True: 1, False: 0}),
        "is_pit_in": laps["PitInTime"].notna().astype(int),
        "is_pit_out": laps["PitOutTime"].notna().astype(int),
        "track_status": laps["TrackStatus"],
        "is_accurate": laps["IsAccurate"].map({True: 1, False: 0}),
    })
    df = df.dropna(subset=["driver_id"])  # drivers missing from reference table
    df["is_clean"] = df.apply(_is_clean, axis=1)
    return df


def _build_stints(laps: pd.DataFrame) -> pd.DataFrame:
    grouped = laps.dropna(subset=["stint"]).groupby(
        ["session_id", "driver_id", "stint"], as_index=False
    ).agg(
        compound=("compound", "first"),
        start_lap=("lap_number", "min"),
        end_lap=("lap_number", "max"),
        start_tyre_age=("tyre_age", "min"),
    )
    grouped["stint_length"] = grouped["end_lap"] - grouped["start_lap"] + 1
    return grouped


def _build_weather(session, session_id: int) -> pd.DataFrame:
    w = session.weather_data
    return pd.DataFrame({
        "session_id": session_id,
        "time_offset_s": w["Time"].dt.total_seconds(),
        "air_temp_c": w["AirTemp"],
        "track_temp_c": w["TrackTemp"],
        "humidity": w["Humidity"],
        "pressure": w["Pressure"],
        "wind_speed": w["WindSpeed"],
        "wind_direction": w["WindDirection"],
        "rainfall": w["Rainfall"].astype(int),
    })


def _build_events(session, session_id: int) -> pd.DataFrame:
    """Derive safety car / VSC / red flag periods as lap ranges from lap track status."""
    laps = session.laps[["LapNumber", "TrackStatus"]].dropna()
    kinds = {"4": "SAFETY_CAR", "6": "VSC", "5": "RED_FLAG"}
    rows = []
    for code, kind in kinds.items():
        flagged = sorted(
            laps.loc[laps["TrackStatus"].astype(str).str.contains(code), "LapNumber"]
            .astype(int).unique()
        )
        if not flagged:
            continue
        start = prev = flagged[0]
        for lap in flagged[1:]:
            if lap != prev + 1:
                rows.append((session_id, kind, start, prev))
                start = lap
            prev = lap
        rows.append((session_id, kind, start, prev))
    return pd.DataFrame(rows, columns=["session_id", "event_type", "start_lap", "end_lap"])


def _replace(conn, table: str, df: pd.DataFrame, session_id: int) -> None:
    conn.execute(f"DELETE FROM {table} WHERE session_id = ?", (session_id,))
    df.to_sql(table, conn, if_exists="append", index=False)


def ingest(season: int, rnd: int, session_type: str = "R") -> None:
    FASTF1_CACHE.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(FASTF1_CACHE))

    session = fastf1.get_session(season, rnd, session_type)
    session.load(laps=True, weather=True, telemetry=False, messages=False)

    with get_connection() as conn:
        drivers = _driver_lookup(conn)
        session_id = _session_id(conn, season, rnd, session_type)

        laps = _build_laps(session, drivers, session_id)
        _replace(conn, "laps", laps, session_id)
        _replace(conn, "tire_stints", _build_stints(laps), session_id)
        _replace(conn, "weather", _build_weather(session, session_id), session_id)
        _replace(conn, "race_events", _build_events(session, session_id), session_id)

        clean = int(laps["is_clean"].sum())
        print(f"{season} R{rnd} {session_type}: {len(laps)} laps "
              f"({clean} clean) loaded")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("Usage: python -m src.ingest_fastf1 <season> <round> [session]")
    ingest(int(sys.argv[1]), int(sys.argv[2]),
           sys.argv[3] if len(sys.argv) > 3 else "R")
