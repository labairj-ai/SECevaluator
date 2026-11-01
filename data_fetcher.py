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


class Rankings(dict):
    """Ranks plus the actual poll/week, including an explicit unavailable state."""
    def __init__(self, values=None, *, poll=None, week=None):
        super().__init__(values or {})
        self.poll = poll
        self.week = week


def fetch_rankings(year: int, week: int) -> dict[str, int]:
    for w in range(week, max(0, week - 4), -1):
        data = _get("/rankings", {"year": year, "week": w, "seasonType": "regular"})
        if not isinstance(data, list):
            raise ValueError("Invalid rankings response")
        for entry in data:
            for poll in sorted(entry.get("polls", []), key=_poll_sort_key):
                if _poll_sort_key(poll) >= 9 or not poll.get("ranks"):
                    continue
                ranks = {}
                for row in poll["ranks"]:
                    school, rank = row.get("school"), row.get("rank")
                    if not school or type(rank) is not int or not 1 <= rank <= 25 or school in ranks:
                        raise ValueError("Invalid poll rank")
                    ranks[school] = rank
                return Rankings(ranks, poll=poll["poll"], week=w)
    return Rankings()


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
