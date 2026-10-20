"""Project-wide settings."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "pitwall.db"
SCHEMA_PATH = ROOT / "sql" / "schema.sql"
FASTF1_CACHE = DATA_DIR / "fastf1_cache"

# Jolpica-F1 is the maintained successor to the Ergast API.
JOLPICA_BASE = "https://api.jolpi.ca/ergast/f1"

# Be polite to the API: seconds to wait between requests.
REQUEST_DELAY = 0.5

DEFAULT_SEASONS = [2023, 2024, 2025]
