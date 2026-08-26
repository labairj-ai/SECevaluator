import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

DB_PATH = "secevaluator.db"


def _conn():
    return sqlite3.connect(DB_PATH)


def init_db() -> None:
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS weekly_snapshots (
                year          INTEGER,
                week          INTEGER,
                conference    TEXT,
                avg_sp_rating REAL,
                avg_sos       REAL,
                h2h_wins      INTEGER,
                h2h_losses    INTEGER,
                total_wins    INTEGER,
                total_losses  INTEGER,
                ranked_teams  INTEGER,
                saved_at      TEXT,
                PRIMARY KEY (year, week, conference)
            )
        """)


def save_snapshot(year: int, week: int, conf_name: str, stats) -> None:
    with _conn() as c:
        c.execute("""
            INSERT OR REPLACE INTO weekly_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (
            year, week, conf_name,
            stats.avg_sp_rating,
            stats.avg_sos,
            stats.h2h_wins,
            stats.h2h_losses,
            stats.total_wins,
            stats.total_losses,
            stats.ranked_teams,
            datetime.now().isoformat(),
        ))


def load_prior_snapshot(year: int, week: int, conf_name: str) -> Optional[dict]:
    """Return the most recent snapshot before the given week."""
    with _conn() as c:
        row = c.execute("""
            SELECT avg_sp_rating, avg_sos, h2h_wins, h2h_losses, total_wins, total_losses, ranked_teams
            FROM weekly_snapshots
            WHERE year=? AND week<? AND conference=?
            ORDER BY week DESC LIMIT 1
        """, (year, week, conf_name)).fetchone()
    if not row:
        return None
    return {
        "avg_sp_rating": row[0],
        "avg_sos":        row[1],
        "h2h_wins":       row[2],
        "h2h_losses":     row[3],
        "total_wins":     row[4],
        "total_losses":   row[5],
        "ranked_teams":   row[6],
    }
