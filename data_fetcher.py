import requests
import time
from datetime import date
from typing import Any

from config import CFBD_API_KEY, YEAR, SEC_CONF_PARAM, BIG10_CONF_PARAM, BIG10_CONF_RESPONSE, SEC_CONF_RESPONSE, SEASON_START

BASE_URL = "https://api.collegefootballdata.com"
HTTP_TIMEOUT = 30
HTTP_ATTEMPTS = 3
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def _headers() -> dict:
    return {"Authorization": f"Bearer {CFBD_API_KEY}"}


def _get(path: str, params: dict) -> list:
    for attempt in range(1, HTTP_ATTEMPTS + 1):
        try:
            r = requests.get(f"{BASE_URL}{path}", headers=_headers(), params=params, timeout=HTTP_TIMEOUT)
            r.raise_for_status()
        except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as exc:
            status = exc.response.status_code if exc.response is not None else None
            if isinstance(exc, requests.HTTPError) and status not in RETRYABLE_STATUS_CODES:
                raise
            if attempt == HTTP_ATTEMPTS:
                print(f"CFBD {path}: failed after {attempt} attempts ({type(exc).__name__}, status={status})", flush=True)
                raise
            delay = 2 ** attempt
            print(f"CFBD {path}: attempt {attempt}/{HTTP_ATTEMPTS} failed "
                  f"({type(exc).__name__}, status={status}); retrying in {delay}s", flush=True)
            time.sleep(delay)
        else:
            return r.json()


def get_current_week() -> int:
    today = date.today()
    if today < SEASON_START:
        return 1
    delta = (today - SEASON_START).days
    return max(1, min((delta // 7) + 1, 20))


def fetch_records(year: int, conference: str) -> list[dict]:
    return _get("/records", {"year": year, "conference": conference})


def fetch_all_conference_games(year: int, conference: str) -> list[dict]:
    """All regular + postseason games involving any team in this conference."""
    games = []
    for season_type in ("regular", "postseason"):
        rows = _get("/games", {"year": year, "seasonType": season_type, "conference": conference})
        if not isinstance(rows, list) or any(not isinstance(g, dict) or g.get("id") is None for g in rows):
            raise ValueError("Invalid CFBD games response")
        games.extend(rows)
    unique = {}
    for game in games:
        gid = game["id"]
        if gid in unique and unique[gid] != game:
            raise ValueError("Conflicting CFBD game records")
        unique[gid] = game
    return list(unique.values())


def cross_conference_games(games: list[dict]) -> list[dict]:
    return [g for g in games if {g.get("homeConference"), g.get("awayConference")}
            == {SEC_CONF_RESPONSE, BIG10_CONF_RESPONSE}]


def fetch_cross_conference_games(year: int) -> list[dict]:
    """Require complete data; API failure must never mean no games played."""
    return cross_conference_games(fetch_all_conference_games(year, SEC_CONF_PARAM))


def _poll_sort_key(p: dict) -> int:
    name = p.get("poll", "")
    if "Playoff" in name:
        return 0
    if "AP" in name:
        return 1
    if "Coaches" in name and "FCS" not in name and "Division" not in name:
        return 2
    return 9  # FCS, D2, D3 -- skip


def fetch_rankings(year: int, week: int) -> dict[str, int]:
    """Return dict of team -> rank (CFP preferred, AP Top 25 fallback).

    If the requested week has no rankings yet (polls publish after games),
    walks back up to 4 weeks to find the most recent available rankings.
    """
    season_type = "postseason" if date.today() > date(year, 12, 1) and year == YEAR else "regular"

    data: list = []
    for w in range(week, max(0, week - 4), -1):
        try:
            data = _get("/rankings", {"year": year, "week": w, "seasonType": season_type})
        except Exception:
            continue
        if data:
            break

    if not data:
        return {}

    rankings: dict[str, int] = {}
    week_data = data[0]

    for poll in sorted(week_data.get("polls", []), key=_poll_sort_key):
        if _poll_sort_key(poll) >= 9:
            break  # skip FCS/D2/D3 polls entirely
        for entry in poll.get("ranks", []):
            school = entry.get("school", "")
            rank   = entry.get("rank")
            if school and rank and school not in rankings:
                rankings[school] = rank
        # One authoritative FBS poll is enough
        if "Playoff" in poll.get("poll", "") or "AP" in poll.get("poll", ""):
            break
    return rankings


def fetch_sp_ratings(year: int) -> dict[str, dict]:
    """All FBS teams keyed by team name."""
    try:
        data = _get("/ratings/sp", {"year": year})
    except Exception:
        return {}
    return {row["team"]: row for row in data if "team" in row}


def fetch_all_data(year: int, week: int) -> dict[str, Any]:
    sec_records    = fetch_records(year, SEC_CONF_PARAM)
    big10_records  = fetch_records(year, BIG10_CONF_PARAM)
    sec_all_games  = fetch_all_conference_games(year, SEC_CONF_PARAM)
    big10_all_games = fetch_all_conference_games(year, BIG10_CONF_PARAM)
    cross_games = cross_conference_games(sec_all_games)
    other_cross = cross_conference_games(big10_all_games)
    if {g["id"]: g for g in cross_games} != {g["id"]: g for g in other_cross}:
        raise ValueError("SEC and Big Ten head-to-head data disagree")
    rankings       = fetch_rankings(year, week)
    sp_ratings     = fetch_sp_ratings(year)
    return {
        "sec_records":      sec_records,
        "big10_records":    big10_records,
        "cross_games":      cross_games,
        "sec_all_games":    sec_all_games,
        "big10_all_games":  big10_all_games,
        "rankings":         rankings,
        "sp_ratings":       sp_ratings,
    }
