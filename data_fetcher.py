import requests
import time
from datetime import date, datetime, time as clock_time, timezone
import math
from zoneinfo import ZoneInfo
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
            data = r.json()
            if not isinstance(data, list):
                raise ValueError("CFBD response must be a list")
            return data


def get_current_period(year: int = YEAR, now: datetime | None = None) -> tuple[int, str]:
    """Use the provider's actual football calendar, not elapsed seven-day blocks."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Current time must include a timezone")
    rows = _get("/calendar", {"year": year})
    periods = []
    for row in rows:
        if row.get("season") != year or row.get("seasonType") not in ("regular", "postseason") or type(row.get("week")) is not int or row["week"] < 1:
            raise ValueError("Invalid football calendar")
        start = datetime.fromisoformat(row.get("startDate", "").replace("Z", "+00:00"))
        if start.tzinfo is None:
            raise ValueError("Calendar time must include a timezone")
        periods.append((start, row["week"], row["seasonType"]))
    if not periods or len({p[0] for p in periods}) != len(periods):
        raise ValueError("Missing or conflicting football calendar")
    periods.sort()
    eligible = [p for p in periods if p[0] <= now]
    _, week, season_type = eligible[-1] if eligible else periods[0]
    return week, season_type


def get_current_week(today: date | None = None) -> int:
    now = datetime.combine(today, clock_time(12), ZoneInfo("America/New_York")) if today else None
    return get_current_period(now=now)[0]


def fetch_records(year: int, conference: str) -> list[dict]:
    rows = _get("/records", {"year": year, "conference": conference})
    expected = SEC_CONF_RESPONSE if conference == SEC_CONF_PARAM else BIG10_CONF_RESPONSE
    if not rows or any(not isinstance(r, dict) or r.get("year") != year
                       or r.get("conference") != expected for r in rows):
        raise ValueError("Invalid conference records identity")
    return rows


def fetch_all_conference_games(year: int, conference: str) -> list[dict]:
    """All regular + postseason games involving any team in this conference."""
    games = []
    for season_type in ("regular", "postseason"):
        rows = _get("/games", {"year": year, "seasonType": season_type, "conference": conference})
        if not isinstance(rows, list) or any(not isinstance(g, dict) or type(g.get("id")) is not int or g["id"] <= 0 for g in rows):
            raise ValueError("Invalid CFBD games response")
        for game in rows:
            if game.get("season") != year or game.get("seasonType") != season_type:
                raise ValueError("Wrong game season identity")
            expected = SEC_CONF_RESPONSE if conference == SEC_CONF_PARAM else BIG10_CONF_RESPONSE
            if expected not in (game.get("homeConference"), game.get("awayConference")):
                raise ValueError("Wrong game conference identity")
            if type(game.get("completed")) is not bool:
                raise ValueError("Missing completed game status")
            if type(game.get("week")) is not int or game["week"] < 0:
                raise ValueError("Invalid game week")
            if any(not isinstance(game.get(k), str) or not game[k].strip() for k in ("homeTeam", "awayTeam")) or game["homeTeam"] == game["awayTeam"]:
                raise ValueError("Invalid game teams")
            start = datetime.fromisoformat(game.get("startDate", "").replace("Z", "+00:00"))
            if start.tzinfo is None:
                raise ValueError("Game start time has no timezone")
            for k in ("homePoints", "awayPoints"):
                value = game.get(k)
                if value is not None and (type(value) is not int or value < 0):
                    raise ValueError("Invalid game score")
            if game["completed"] and (game.get("homePoints") is None or game.get("awayPoints") is None or game["homePoints"] == game["awayPoints"]):
                raise ValueError("Invalid completed game score")
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
    # Never infer an FBS poll from a substring in an unknown/FCS poll name.
    return {"Playoff Committee Rankings": 0, "College Football Playoff Rankings": 0,
            "AP Top 25": 1, "Coaches Poll": 2}.get(p.get("poll"), 9)


class Rankings(dict):
    """Ranks plus the actual poll/week, including an explicit unavailable state."""
    def __init__(self, values=None, *, poll=None, week=None, season_type="regular"):
        super().__init__(values or {})
        self.poll = poll
        self.week = week
        self.season_type = season_type


def fetch_rankings(year: int, week: int, season_type: str = "regular") -> dict[str, int]:
    if season_type not in ("regular", "postseason"):
        raise ValueError("Invalid rankings season type")
    if season_type == "postseason":
        data = _get("/rankings", {"year": year, "seasonType": "postseason"})
        data += _get("/rankings", {"year": year, "seasonType": "regular"})
        for entry in data:
            if entry.get("season") != year or entry.get("seasonType") not in ("regular", "postseason") or type(entry.get("week")) is not int:
                raise ValueError("Wrong poll season identity")
        # Postseason week 1 follows regular week 15 rather than preceding it.
        ordered = sorted((e for e in data if e["seasonType"] == "regular" or e["week"] <= week),
                         key=lambda e: (e["seasonType"] == "postseason", e["week"]), reverse=True)
        for entry in ordered:
            result = _poll_rankings(entry, year, entry["week"], entry["seasonType"])
            if result:
                return result
        return Rankings()
    for w in range(week, max(0, week - 4), -1):
        data = _get("/rankings", {"year": year, "week": w, "seasonType": season_type})
        if not isinstance(data, list):
            raise ValueError("Invalid rankings response")
        for entry in data:
            result = _poll_rankings(entry, year, w, season_type)
            if result:
                return result
    return Rankings()


def _poll_rankings(entry, year, week, season_type):
    if entry.get("season") != year or entry.get("week") != week or entry.get("seasonType") != season_type:
        raise ValueError("Wrong poll season or week")
    for poll in sorted(entry.get("polls", []), key=_poll_sort_key):
        if _poll_sort_key(poll) >= 9 or not poll.get("ranks"):
            continue
        ranks = {}
        for row in poll["ranks"]:
            school, rank = row.get("school"), row.get("rank")
            if not school or type(rank) is not int or not 1 <= rank <= 25 or school in ranks:
                raise ValueError("Invalid poll rank")
            ranks[school] = rank
        return Rankings(ranks, poll=poll["poll"], week=week, season_type=season_type)
    return Rankings()


def fetch_sp_ratings(year: int) -> dict[str, dict]:
    """All FBS teams keyed by team name."""
    data = _get("/ratings/sp", {"year": year})
    ratings = {}
    for row in data:
        team, rating = row.get("team"), row.get("rating")
        if not team or team in ratings or row.get("year") != year:
            raise ValueError("Invalid SP+ team or season identity")
        if rating is not None and (type(rating) not in (int, float) or not math.isfinite(rating)):
            raise ValueError("Invalid SP+ rating")
        ratings[team] = row
    return ratings


def fetch_all_data(year: int, week: int, season_type: str = "regular") -> dict[str, Any]:
    sec_records    = fetch_records(year, SEC_CONF_PARAM)
    big10_records  = fetch_records(year, BIG10_CONF_PARAM)
    sec_all_games  = fetch_all_conference_games(year, SEC_CONF_PARAM)
    big10_all_games = fetch_all_conference_games(year, BIG10_CONF_PARAM)
    cross_games = cross_conference_games(sec_all_games)
    other_cross = cross_conference_games(big10_all_games)
    if {g["id"]: g for g in cross_games} != {g["id"]: g for g in other_cross}:
        raise ValueError("SEC and Big Ten head-to-head data disagree")
    rankings       = fetch_rankings(year, week, season_type)
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
