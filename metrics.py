from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TeamStats:
    team: str
    conference_display: str
    overall_wins: int = 0
    overall_losses: int = 0
    conf_wins: int = 0
    conf_losses: int = 0
    sp_rating: Optional[float] = None
    sp_rank: Optional[int] = None
    sos_ooc: Optional[float] = None    # avg SP+ of non-conference opponents
    cfp_rank: Optional[int] = None

    @property
    def nonconf_wins(self) -> int:
        return max(0, self.overall_wins - self.conf_wins)

    @property
    def nonconf_losses(self) -> int:
        return max(0, self.overall_losses - self.conf_losses)

    @property
    def win_pct(self) -> float:
        total = self.overall_wins + self.overall_losses
        return self.overall_wins / total if total else 0.0

    @property
    def record_str(self) -> str:
        return f"{self.overall_wins}-{self.overall_losses}"

    @property
    def conf_record_str(self) -> str:
        return f"{self.conf_wins}-{self.conf_losses}"

    @property
    def nonconf_record_str(self) -> str:
        return f"{self.nonconf_wins}-{self.nonconf_losses}"

    @property
    def cfp_rank_str(self) -> str:
        return f"#{self.cfp_rank}" if self.cfp_rank else "—"

    @property
    def sp_str(self) -> str:
        return f"{self.sp_rating:+.1f}" if self.sp_rating is not None else "N/A"

    @property
    def sos_str(self) -> str:
        return f"{self.sos_ooc:+.1f}" if self.sos_ooc is not None else "N/A"


@dataclass
class CrossGameResult:
    week: int
    home_team: str
    home_conference: str
    away_team: str
    away_conference: str
    home_points: Optional[int]
    away_points: Optional[int]
    neutral_site: bool = False
    game_date: str = ""

    @property
    def played(self) -> bool:
        return self.home_points is not None and self.away_points is not None

    def winner(self) -> Optional[str]:
        if not self.played:
            return None
        return self.home_team if self.home_points > self.away_points else self.away_team

    def score_str(self) -> str:
        if not self.played:
            return "TBD"
        loc = " (N)" if self.neutral_site else ""
        winner = self.winner()
        loser  = self.away_team if winner == self.home_team else self.home_team
        pts_w  = self.home_points if winner == self.home_team else self.away_points
        pts_l  = self.away_points if winner == self.home_team else self.home_points
        return f"{winner} {pts_w}, {loser} {pts_l}{loc}"

    def sec_won(self, sec_conf_response: str) -> Optional[bool]:
        winner = self.winner()
        if winner is None:
            return None
        if self.home_conference == sec_conf_response:
            return winner == self.home_team
        return winner == self.away_team


@dataclass
class ConferenceStats:
    name: str
    display: str
    teams: list[TeamStats] = field(default_factory=list)
    h2h_wins: int = 0
    h2h_losses: int = 0
    d_avg_sp: Optional[float] = None
    d_avg_sos: Optional[float] = None

    @property
    def ranked_teams(self) -> int:
        return sum(1 for t in self.teams if t.cfp_rank is not None)

    @property
    def avg_sp_rating(self) -> Optional[float]:
        rated = [t.sp_rating for t in self.teams if t.sp_rating is not None]
        return round(sum(rated) / len(rated), 2) if rated else None

    @property
    def avg_sos(self) -> Optional[float]:
        rated = [t.sos_ooc for t in self.teams if t.sos_ooc is not None]
        return round(sum(rated) / len(rated), 2) if rated else None

    @property
    def total_wins(self) -> int:
        return sum(t.overall_wins for t in self.teams)

    @property
    def total_losses(self) -> int:
        return sum(t.overall_losses for t in self.teams)

    @property
    def nonconf_wins(self) -> int:
        return sum(t.nonconf_wins for t in self.teams)

    @property
    def nonconf_losses(self) -> int:
        return sum(t.nonconf_losses for t in self.teams)

    @property
    def h2h_record_str(self) -> str:
        if self.h2h_wins == 0 and self.h2h_losses == 0:
            return "No games played yet"
        total = self.h2h_wins + self.h2h_losses
        pct = self.h2h_wins / total if total else 0
        return f"{self.h2h_wins}-{self.h2h_losses} ({pct:.3f})"

    @property
    def best_ranked_teams(self) -> list[TeamStats]:
        ranked = [t for t in self.teams if t.cfp_rank is not None]
        return sorted(ranked, key=lambda t: t.cfp_rank)[:5]


def _compute_ooc_sos(
    team_name: str,
    conf_team_names: set[str],
    all_conf_games: list[dict],
    sp_ratings: dict,
) -> Optional[float]:
    """Average SP+ rating of non-conference opponents faced by this team."""
    opponent_sp: list[float] = []
    for g in all_conf_games:
        home = g.get("homeTeam", "")
        away = g.get("awayTeam", "")
        if home == team_name:
            opponent = away
        elif away == team_name:
            opponent = home
        else:
            continue
        if opponent in conf_team_names:
            continue  # skip intra-conference opponents
        if g.get("homePoints") is None:
            continue  # game not yet played
        sp = sp_ratings.get(opponent, {})
        if sp and sp.get("rating") is not None:
            opponent_sp.append(sp["rating"])
    return round(sum(opponent_sp) / len(opponent_sp), 2) if opponent_sp else None


def build_team_stats(
    records: list[dict],
    all_conf_games: list[dict],
    sp_ratings: dict,
    rankings: dict,
    conference_display: str,
) -> list[TeamStats]:
    team_names = {r.get("team", "") for r in records}

    teams = []
    for row in records:
        team_name = row.get("team", "")
        total = row.get("total", {})
        conf  = row.get("conferenceGames", {})
        sp    = sp_ratings.get(team_name, {})

        sos = _compute_ooc_sos(team_name, team_names, all_conf_games, sp_ratings)

        ts = TeamStats(
            team=team_name,
            conference_display=conference_display,
            overall_wins=total.get("wins", 0),
            overall_losses=total.get("losses", 0),
            conf_wins=conf.get("wins", 0),
            conf_losses=conf.get("losses", 0),
            sp_rating=sp.get("rating"),
            sp_rank=sp.get("ranking"),
            sos_ooc=sos,
            cfp_rank=rankings.get(team_name),
        )
        teams.append(ts)

    return sorted(teams, key=lambda t: (-t.win_pct, t.overall_losses))


def build_cross_game_results(raw_games: list[dict]) -> list[CrossGameResult]:
    """Build CrossGameResult list from raw API game dicts (camelCase fields)."""
    results = []
    for g in raw_games:
        results.append(CrossGameResult(
            week=g.get("week", 0),
            home_team=g.get("homeTeam", ""),
            home_conference=g.get("homeConference", ""),
            away_team=g.get("awayTeam", ""),
            away_conference=g.get("awayConference", ""),
            home_points=g.get("homePoints"),
            away_points=g.get("awayPoints"),
            neutral_site=g.get("neutralSite", False),
            game_date=(g.get("startDate") or "")[:10],
        ))
    return sorted(results, key=lambda g: (g.week, g.game_date))


def build_conference_stats(
    name: str,
    display: str,
    teams: list[TeamStats],
    cross_games: list[CrossGameResult],
    sec_conf_response: str,
) -> ConferenceStats:
    stats = ConferenceStats(name=name, display=display, teams=teams)
    is_sec = (name == sec_conf_response)
    for game in cross_games:
        if not game.played:
            continue
        sec_won = game.sec_won(sec_conf_response)
        if sec_won is None:
            continue
        if is_sec:
            if sec_won:
                stats.h2h_wins += 1
            else:
                stats.h2h_losses += 1
        else:
            if sec_won:
                stats.h2h_losses += 1
            else:
                stats.h2h_wins += 1
    return stats


def h2h_leader(sec: ConferenceStats, big10: ConferenceStats) -> str:
    if sec.h2h_wins == 0 and sec.h2h_losses == 0:
        return "No cross-conference games played yet"
    if sec.h2h_wins > sec.h2h_losses:
        return f"SEC leads {sec.h2h_wins}-{sec.h2h_losses}"
    if big10.h2h_wins > big10.h2h_losses:
        return f"Big Ten leads {big10.h2h_wins}-{big10.h2h_losses}"
    return f"Series tied {sec.h2h_wins}-{big10.h2h_wins}"


# ── Top Wins ──────────────────────────────────────────────────────────────────

@dataclass
class TopWin:
    team: str
    conference_display: str
    opponent: str
    opponent_sp: float
    winner_score: int
    loser_score: int
    week: int
    margin: int

    @property
    def score_str(self) -> str:
        return f"{self.winner_score}-{self.loser_score}"


def compute_top_wins(
    all_conf_games: list[dict],
    conf_team_names: set[str],
    sp_ratings: dict,
    conference_display: str,
    n: int = 5,
) -> list[TopWin]:
    """Top N wins by conference teams ranked by opponent SP+ at time of game."""
    wins: list[TopWin] = []
    seen: set = set()
    for g in all_conf_games:
        gid = g.get("id")
        if gid in seen:
            continue
        seen.add(gid)

        home  = g.get("homeTeam", "")
        away  = g.get("awayTeam", "")
        hp    = g.get("homePoints")
        ap    = g.get("awayPoints")
        if hp is None or ap is None or hp == ap:
            continue

        if home in conf_team_names and hp > ap:
            winner, opponent, ws, ls = home, away, hp, ap
        elif away in conf_team_names and ap > hp:
            winner, opponent, ws, ls = away, home, ap, hp
        else:
            continue

        opp_sp = (sp_ratings.get(opponent) or {}).get("rating")
        if opp_sp is None:
            continue

        wins.append(TopWin(
            team=winner,
            conference_display=conference_display,
            opponent=opponent,
            opponent_sp=opp_sp,
            winner_score=ws,
            loser_score=ls,
            week=g.get("week", 0),
            margin=ws - ls,
        ))

    return sorted(wins, key=lambda w: -w.opponent_sp)[:n]


# ── Game of the Week ──────────────────────────────────────────────────────────

@dataclass
class GameOfWeek:
    week: int
    home_team: str
    home_conference: str
    away_team: str
    away_conference: str
    home_sp: Optional[float]
    away_sp: Optional[float]
    game_date: str

    @property
    def combined_sp(self) -> float:
        return (self.home_sp or 0) + (self.away_sp or 0)

    @property
    def matchup_str(self) -> str:
        loc = "vs" if self.home_conference else "at"
        return f"{self.away_team} at {self.home_team}"


def compute_game_of_week(
    cross_games: list[CrossGameResult],
    sp_ratings: dict,
) -> Optional[GameOfWeek]:
    """Return the highest-quality upcoming SEC vs Big Ten matchup by combined SP+."""
    upcoming = [g for g in cross_games if not g.played]
    if not upcoming:
        return None

    best: Optional[GameOfWeek] = None
    for g in upcoming:
        home_sp = (sp_ratings.get(g.home_team) or {}).get("rating")
        away_sp = (sp_ratings.get(g.away_team) or {}).get("rating")
        candidate = GameOfWeek(
            week=g.week,
            home_team=g.home_team,
            home_conference=g.home_conference,
            away_team=g.away_team,
            away_conference=g.away_conference,
            home_sp=home_sp,
            away_sp=away_sp,
            game_date=g.game_date,
        )
        if best is None or candidate.combined_sp > best.combined_sp:
            best = candidate
    return best
