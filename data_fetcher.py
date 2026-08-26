import requests
from datetime import date
from typing import Any

from config import CFBD_API_KEY, YEAR, SEC_CONF_PARAM, BIG10_CONF_PARAM, BIG10_CONF_RESPONSE, SEASON_START

BASE_URL = "https://api.collegefootballdata.com"
HTTP_TIMEOUT = 30


def _headers() -> dict:
    return {"Authorization": f"Bearer {CFBD_API_KEY}"}


def _get(path: str, params: dict) -> list:
    r = requests.get(f"{BASE_URL}{path}", headers=_headers(), params=params, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    return r.json()


def get_current_week() -> int:
    today = date.today()
    if today < SEASON_START:
        return 1
    delta = (today - SEASON_START).days
    return max(1, min((delta // 7) + 1, 20))


def fetch_records(year: int, conference: str) -> list[dict]:
    return _get("/records", {"year": year, "conference": conference})


def fetch_conference_games(year: int, conference: str, season_type: str = "regular") -> list[dict]:
    return _get("/games", {"year": year, "seasonType": season_type, "conference": conference})


def fetch_cross_conference_games(year: int) -> list[dict]:
    """Return all played SEC vs Big Ten games (regular + postseason)."""
    all_games: list[dict] = []
    for season_type in ("regular", "postseason"):
        try:
            sec_games = _get("/games", {
                "year": year,
                "seasonType": season_type,
                "conference": SEC_CONF_PARAM,
            })
            cross = [
                g for g in sec_games
                if g.get("home_conference") == BIG10_CONF_RESPONSE
                or g.get("away_conference") == BIG10_CONF_RESPONSE
            ]
            all_games.extend(cross)
        except Exception:
            pass
    # Deduplicate by game id
    seen: set[int] = set()
    unique = []
    for g in all_games:
        gid = g.get("id")
        if gid not in seen:
            seen.add(gid)
            unique.append(g)
    return unique


def fetch_rankings(year: int) -> dict[str, int]:
    """Return dict of team -> CFP rank (or AP if CFP unavailable). None if unranked."""
    week = get_current_week()
    season_type = "postseason" if date.today() > date(year, 12, 1) else "regular"
    try:
        data = _get("/rankings", {"year": year, "week": week, "seasonType": season_type})
    except Exception:
        return {}

    if not data:
        return {}

    rankings: dict[str, int] = {}
    week_data = data[0] if data else {}
    for poll in week_data.get("polls", []):
        poll_name = poll.get("poll", "")
        if "Playoff" in poll_name or "AP" in poll_name:
            for entry in poll.get("ranks", []):
                school = entry.get("school", "")
                rank = entry.get("rank")
                if school and rank and school not in rankings:
                    rankings[school] = rank
            if "Playoff" in poll_name:
                break  # prefer CFP rankings over AP
    return rankings


def fetch_sp_ratings(year: int) -> dict[str, dict]:
    """Return dict of team -> {rating, ranking, conference} for all FBS teams."""
    try:
        data = _get("/ratings/sp", {"year": year})
    except Exception:
        return {}
    return {row["team"]: row for row in data if "team" in row}


def fetch_sos(year: int) -> dict[str, dict]:
    """Return dict of team -> SOS data for all FBS teams."""
    try:
        data = _get("/ratings/sos", {"year": year})
    except Exception:
        return {}
    return {row["team"]: row for row in data if "team" in row}


def fetch_all_data(year: int) -> dict[str, Any]:
    """Fetch everything needed for the weekly report."""
    sec_records = fetch_records(year, SEC_CONF_PARAM)
    big10_records = fetch_records(year, BIG10_CONF_PARAM)
    cross_games = fetch_cross_conference_games(year)
    rankings = fetch_rankings(year)
    sp_ratings = fetch_sp_ratings(year)
    sos_ratings = fetch_sos(year)
    week = get_current_week()
    return {
        "sec_records": sec_records,
        "big10_records": big10_records,
        "cross_games": cross_games,
        "rankings": rankings,
        "sp_ratings": sp_ratings,
        "sos_ratings": sos_ratings,
        "week": week,
    }
