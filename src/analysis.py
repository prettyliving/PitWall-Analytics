"""Race pace and consistency analysis.

Definitions used throughout:

* clean lap      - flagged ``is_clean = 1`` in the database (not lap 1, not an
                   in/out lap, green flag, accurate timing).
* outlier lap    - a clean lap more than 2% slower than the trend line of its
                   stint (traffic, a mistake, a lock-up). Removed before stats.
* race pace      - median clean lap time per driver.
* consistency    - spread of lap times *after removing the linear trend inside
                   each stint*. Raw standard deviation would punish a driver for
                   fuel burn and tyre wear, which are not inconsistency. Lower is
                   better. The raw coefficient of variation is reported alongside.
"""
from __future__ import annotations

import sqlite3

import numpy as np
import pandas as pd

LAPS_QUERY = """
SELECT l.*,
       d.code,
       d.family_name,
       t.name AS team
FROM laps l
JOIN sessions s ON s.session_id = l.session_id
JOIN races r    ON r.race_id    = s.race_id
JOIN drivers d  ON d.driver_id  = l.driver_id
LEFT JOIN results res ON res.race_id = r.race_id AND res.driver_id = l.driver_id
LEFT JOIN teams t     ON t.team_id   = res.team_id
WHERE r.season = ? AND r.round = ? AND s.session_type = ?
"""


def load_race_laps(
    conn: sqlite3.Connection, season: int, rnd: int, session_type: str = "R"
) -> pd.DataFrame:
    """All laps for one session, joined to driver and team names."""
    laps = pd.read_sql_query(LAPS_QUERY, conn, params=(season, rnd, session_type))
    if laps.empty:
        raise ValueError(
            f"No laps found for {season} round {rnd} ({session_type}). "
            "Run the ingestion scripts first."
        )
    return laps


def clean_laps(laps: pd.DataFrame, outlier_factor: float = 1.02) -> pd.DataFrame:
    """Keep clean laps and drop slow outliers relative to each stint's trend line.

    A lap more than 2% (about 1.8 s on a 92 s lap) slower than the stint's fitted
    trend is treated as traffic or a mistake. The trend is fitted twice, so the
    outliers themselves do not drag the line up. Comparing to the trend rather
    than the stint median matters: fuel burn makes early laps slower than the
    median, which hid outliers on late laps (a 5% median-based rule and then a 3%
    one both let them through on synthetic data)."""
    clean = laps[(laps["is_clean"] == 1) & laps["lap_time_s"].notna()].copy()
    keep = pd.Series(True, index=clean.index)
    for _, g in clean.groupby(["driver_id", "stint"]):
        if len(g) < 5:
            continue
        x = g["lap_number"].to_numpy(float)
        y = g["lap_time_s"].to_numpy(float)
        ok = np.ones(len(g), dtype=bool)
        for _ in range(2):
            slope, intercept = np.polyfit(x[ok], y[ok], 1)
            ok = y <= outlier_factor * (slope * x + intercept)
        keep.loc[g.index] = ok
    return clean[keep].reset_index(drop=True)


def stint_stats(clean: pd.DataFrame, min_laps: int = 5) -> pd.DataFrame:
    """Pace, degradation slope and detrended consistency for every stint."""
    rows = []
    for (driver_id, code, stint), g in clean.groupby(["driver_id", "code", "stint"]):
        if len(g) < min_laps:
            continue
        x = g["lap_number"].to_numpy(float)
        y = g["lap_time_s"].to_numpy(float)
        slope, intercept = np.polyfit(x, y, 1)
        resid = y - (slope * x + intercept)
        rows.append({
            "driver_id": driver_id,
            "code": code,
            "stint": int(stint),
            "compound": g["compound"].mode().iat[0] if g["compound"].notna().any() else None,
            "n_laps": len(g),
            "median_s": float(np.median(y)),
            "mean_s": float(y.mean()),
            "std_s": float(y.std(ddof=1)),
            "cv_pct": float(100 * y.std(ddof=1) / y.mean()),
            "slope_s_per_lap": float(slope),   # tyre wear minus fuel burn
            "resid_std_s": float(resid.std(ddof=2)),
        })
    return pd.DataFrame(rows)


def driver_summary(clean: pd.DataFrame, stints: pd.DataFrame) -> pd.DataFrame:
    """One row per driver: race pace and consistency, ranked."""
    pace = clean.groupby(["driver_id", "code"]).agg(
        team=("team", "first"),
        clean_laps=("lap_time_s", "size"),
        median_pace_s=("lap_time_s", "median"),
    ).reset_index()

    # consistency: lap-weighted mean of the detrended stint spread
    def weighted(g: pd.DataFrame) -> pd.Series:
        w = g["n_laps"]
        return pd.Series({
            "consistency_s": np.average(g["resid_std_s"], weights=w),
            "cv_pct": np.average(g["cv_pct"], weights=w),
            "avg_slope_s_per_lap": np.average(g["slope_s_per_lap"], weights=w),
        })

    cons = stints.groupby("driver_id").apply(weighted, include_groups=False).reset_index()
    out = pace.merge(cons, on="driver_id", how="left")
    out["gap_to_best_s"] = out["median_pace_s"] - out["median_pace_s"].min()
    out["pace_rank"] = out["median_pace_s"].rank(method="min").astype(int)
    out["consistency_rank"] = out["consistency_s"].rank(method="min")
    return out.sort_values("median_pace_s").reset_index(drop=True)


def fmt_lap(seconds: float) -> str:
    """92.345 -> '1:32.345'."""
    minutes, rest = divmod(seconds, 60)
    return f"{int(minutes)}:{rest:06.3f}"
