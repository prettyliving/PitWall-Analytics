"""Create the SQLite database from sql/schema.sql and hand out connections."""
import sqlite3

from .config import DATA_DIR, DB_PATH, SCHEMA_PATH


def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create all tables (safe to re-run; uses IF NOT EXISTS)."""
    with get_connection() as conn:
        conn.executescript(SCHEMA_PATH.read_text())
    print(f"Database ready at {DB_PATH}")


if __name__ == "__main__":
    init_db()
