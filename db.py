"""Report history, with atomic conference pairs and versioned metric semantics."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DB_PATH = "secevaluator.db"
METRIC_VERSION = 3


@contextmanager
def _conn():
    connection = sqlite3.connect(DB_PATH)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def init_db() -> None:
    with _conn() as c:
        # Keep legacy weekly_snapshots untouched: its partial averages and poll
        # labels are not comparable to the validated v2 report semantics.
        c.execute("""
            CREATE TABLE IF NOT EXISTS report_snapshots (
                year INTEGER NOT NULL, week INTEGER NOT NULL,
                season_type TEXT NOT NULL CHECK(season_type IN ('regular','postseason')),
                conference TEXT NOT NULL, avg_sp_rating REAL, avg_sos REAL,
                h2h_wins INTEGER, h2h_losses INTEGER,
                total_wins INTEGER, total_losses INTEGER,
                ranked_teams INTEGER, saved_at TEXT NOT NULL,
                metric_version INTEGER NOT NULL, poll_label TEXT,
                sos_rated_games INTEGER, sos_total_games INTEGER,
                PRIMARY KEY (year, season_type, week, conference)
            )
        """)

        columns = {r[1] for r in c.execute("PRAGMA table_info(report_snapshots)")}
        for column in ("sos_rated_games", "sos_total_games"):
            if column not in columns:
                c.execute(f"ALTER TABLE report_snapshots ADD COLUMN {column} INTEGER")


def _save(c, year, week, conf_name, stats, saved_at, season_type):
    c.execute("""
        INSERT OR REPLACE INTO report_snapshots
        (year,week,season_type,conference,avg_sp_rating,avg_sos,h2h_wins,h2h_losses,
         total_wins,total_losses,ranked_teams,saved_at,metric_version,poll_label,sos_rated_games,sos_total_games)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (year, week, season_type, conf_name, stats.avg_sp_rating, stats.avg_sos,
          stats.h2h_wins, stats.h2h_losses, stats.total_wins, stats.total_losses,
          stats.ranked_teams if stats.poll_label else None, saved_at,
          METRIC_VERSION, stats.poll_label, stats.sos_rated_games, stats.sos_total_games))


def save_snapshots(year: int, week: int, conferences, season_type: str = "regular") -> None:
    conferences = list(conferences)
    if len(conferences) != 2 or {name for name, _ in conferences} != {"SEC", "Big Ten"}:
        raise ValueError("Both conference snapshots are required")
    saved_at = datetime.now(timezone.utc).isoformat()
    with _conn() as c:
        for name, stats in conferences:
            _save(c, year, week, name, stats, saved_at, season_type)


def save_snapshot(year: int, week: int, conf_name: str, stats) -> None:
    """Single-row compatibility API; the report runner always uses the atomic pair."""
    with _conn() as c:
        _save(c, year, week, conf_name, stats, datetime.now(timezone.utc).isoformat(), "regular")


def load_prior_snapshot(year: int, week: int, conf_name: str, season_type: str = "regular") -> Optional[dict]:
    if not Path(DB_PATH).exists():
        return None
    # A read must not create a database or migrate historical data.
    c = sqlite3.connect(Path(DB_PATH).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        columns = {row[1] for row in c.execute("PRAGMA table_info(report_snapshots)")}
        if not {"metric_version", "sos_rated_games", "sos_total_games"}.issubset(columns):
            return None  # old metric definitions are not comparable
        c.row_factory = sqlite3.Row
        row = c.execute("""
            SELECT week,season_type,avg_sp_rating,avg_sos,h2h_wins,h2h_losses,total_wins,
                   total_losses,ranked_teams,poll_label,sos_rated_games,sos_total_games
            FROM report_snapshots
            WHERE year=? AND conference=? AND metric_version=? AND (
                (season_type=? AND week<?) OR (?='postseason' AND season_type='regular'))
            ORDER BY (season_type='postseason') DESC, week DESC LIMIT 1
        """, (year, conf_name, METRIC_VERSION, season_type, week, season_type)).fetchone()
        return dict(row) if row else None
    finally:
        c.close()
