# PitWall Analytics

**Motorsport Performance & Strategy Analytics**

An end-to-end analytics project that uses Formula 1 race data to evaluate how drivers, teams, and strategic decisions shape race results. It covers a data pipeline, a SQL database, statistical analysis in Python, and a Power BI dashboard.

> **Core question:** What can race data tell us about driver performance and race strategy?

## Scope (Version 1)

- **Series:** Formula 1
- **Seasons:** 2023-2025 (start with 2024, expand once the pipeline works)
- **Sessions:** Qualifying and Race

## Data Sources

| Source | Used for |
|---|---|
| [FastF1](https://docs.fastf1.dev/) | Lap times, sector times, tyre compound and age, weather, track status (safety cars) |
| [Jolpica-F1](https://github.com/jolpica/jolpica-f1) | Race results, qualifying results, pit stops, drivers, teams, circuits |

## Repository Layout

```
pitwall-analytics/
├── sql/
│   └── schema.sql          # Database schema (SQLite; portable to PostgreSQL)
├── src/
│   ├── config.py           # Paths, seasons, API settings
│   ├── db.py               # Create the database and open connections
│   ├── ingest_jolpica.py   # Results, qualifying, pit stops, reference data
│   ├── ingest_fastf1.py    # Laps, tyre stints, weather, track status
│   ├── analysis.py         # Clean laps, race pace, detrended consistency
│   └── plots.py            # Charts used by the notebooks
├── notebooks/
│   └── 01_race_pace_consistency.ipynb   # Single-race pace, consistency, stints
├── data/                   # Local database and FastF1 cache (git-ignored)
├── docs/                   # Data dictionary, cleaning notes, case study
├── requirements.txt
└── README.md
```

## Getting Started

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python -m src.db                   # create data/pitwall.db from sql/schema.sql
python -m src.ingest_jolpica 2024  # load results, qualifying, pit stops
python -m src.ingest_fastf1 2024 1 # load laps for season 2024, round 1
```

Load one race first and confirm the data looks right before ingesting a full season. FastF1 downloads are large and are cached under `data/fastf1_cache/`.

Then open `notebooks/01_race_pace_consistency.ipynb` (set `SEASON` and `ROUND` in the first code cell) and run all cells.

## Analysis Questions

| Question | Planned method |
|---|---|
| Which drivers are most consistent over a race? | Coefficient of variation of clean-lap times, per stint |
| How much does qualifying position affect finishing position? | Correlation and regression by circuit |
| Which strategies perform best at each circuit? | 1-stop vs. 2-stop outcomes, controlling for grid position |
| How does tyre choice affect race pace? | Fuel-corrected lap time vs. tyre age, by compound |
| How much position is gained or lost in pit stops? | Position before vs. after the stop cycle |
| How does safety car timing affect strategy? | Compare stops under a safety car vs. just before or after |

## Data Cleaning Rules

Pace calculations exclude lap 1, in/out laps, safety car and VSC laps, and laps flagged as inaccurate. These rules are applied in the `laps` table via the `is_clean` flag (see `sql/schema.sql`).

`src/analysis.py` then drops slow outliers (traffic, mistakes): any clean lap more than 2% slower than its stint's fitted trend line. The trend is used instead of the stint median because fuel burn makes early laps slower than the median, which hid late-lap outliers. Consistency is the lap-time spread *after* removing that trend, so a driver is not penalised for tyre wear or fuel burn.

**How this was checked:** on synthetic races with known pace and noise, the analysis recovered the pace order (Spearman 0.99) and the injected consistency (correlation 0.91, average ratio 1.00). It has not yet been run on real FastF1 data, so treat the first real race as a further test and check how many laps survive cleaning.

## Dashboard Pages (Power BI)

1. Race Overview
2. Driver Performance
3. Team Performance
4. Strategy
5. Circuit Analysis

## Roadmap

- [x] Project scope and schema design
- [ ] Ingest one race end to end
- [ ] Ingest full 2024 season
- [x] Clean-lap pace and consistency analysis (first version, tested on synthetic data)
- [ ] Run the notebook on a real race and write up findings
- [ ] Qualifying vs. finish analysis
- [ ] Pit stop and strategy analysis
- [ ] Power BI dashboard
- [ ] Written case study

Later versions: tyre degradation modeling, weather impact, driver performance scoring, strategy simulation, predictive models.

## Skills Demonstrated

SQL, Python (pandas), statistics, data visualization, Power BI, performance analysis, data storytelling.
