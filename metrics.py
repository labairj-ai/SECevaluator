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
    sos_rating: Optional[float] = None
    cfp_rank: Optional[int] = None

    @property
    def win_pct(self) -> float:
        total = self.overall_wins + self.overall_losses
        return self.overall_wins / total if total else 0.0

    @property
    def record_str(self) -> str:
        conf = f"{self.conf_wins}-{self.conf_losses}"
        return f"{self.overall_wins}-{self.overall_losses} ({conf})"

    @property
    def cfp_rank_str(self) -> str:
        return f"#{self.cfp_rank}" if self.cfp_rank else "—"

    @property
    def sp_str(self) -> str:
        if self.sp_rating is None:
            return "N/A"
        return f"{self.sp_rating:+.1f}" if self.sp_rating else "N/A"

    @property
    def sos_str(self) -> str:
        if self.sos_rating is None:
            return "N/A"
        return f"{self.sos_rating:.2f}"


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
        return f"{self.home_team} {self.home_points}, {self.away_team} {self.away_points}{loc}"

    def sec_won(self, sec_response_name: str) -> Optional[bool]:
        winner = self.winner()
        if winner is None:
            return None
        if self.home_conference == sec_response_name:
            return winner == self.home_team
        return winner == self.away_team


@dataclass
class ConferenceStats:
    name: str
    display: str
    teams: list[TeamStats] = field(default_factory=list)
    h2h_wins: int = 0
    h2h_losses: int = 0

    @property
    def ranked_teams(self) -> int:
        return sum(1 for t in self.teams if t.cfp_rank is not None)

    @property
    def avg_sp_rating(self) -> Optional[float]:
        rated = [t.sp_rating for t in self.teams if t.sp_rating is not None]
        return sum(rated) / len(rated) if rated else None

    @property
    def avg_sos(self) -> Optional[float]:
        rated = [t.sos_rating for t in self.teams if t.sos_rating is not None]
        return sum(rated) / len(rated) if rated else None

    @property
    def total_wins(self) -> int:
        return sum(t.overall_wins for t in self.teams)

    @property
    def total_losses(self) -> int:
        return sum(t.overall_losses for t in self.teams)

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


def build_team_stats(
    records: list[dict],
    sp_ratings: dict,
    sos_ratings: dict,
    rankings: dict,
    conference_display: str,
) -> list[TeamStats]:
    teams = []
    for row in records:
        team_name = row.get("team", "")
        total = row.get("total", {})
        conf = row.get("conferenceGames", {})
        sp = sp_ratings.get(team_name, {})
        sos = sos_ratings.get(team_name, {})

        ts = TeamStats(
            team=team_name,
            conference_display=conference_display,
            overall_wins=total.get("wins", 0),
            overall_losses=total.get("losses", 0),
            conf_wins=conf.get("wins", 0),
            conf_losses=conf.get("losses", 0),
            sp_rating=sp.get("rating"),
            sp_rank=sp.get("ranking"),
            sos_rating=sos.get("currentRating") if sos else None,
            cfp_rank=rankings.get(team_name),
        )
        teams.append(ts)

    return sorted(teams, key=lambda t: (-t.win_pct, t.overall_losses))


def build_cross_game_results(raw_games: list[dict]) -> list[CrossGameResult]:
    results = []
    for g in raw_games:
        if g.get("home_points") is None and g.get("away_points") is None:
            # skip future games
            pass
        results.append(CrossGameResult(
            week=g.get("week", 0),
            home_team=g.get("home_team", ""),
            home_conference=g.get("home_conference", ""),
            away_team=g.get("away_team", ""),
            away_conference=g.get("away_conference", ""),
            home_points=g.get("home_points"),
            away_points=g.get("away_points"),
            neutral_site=g.get("neutral_site", False),
            game_date=(g.get("start_date") or "")[:10],
        ))
    return sorted(results, key=lambda g: (g.week, g.game_date))


def build_conference_stats(
    name: str,
    display: str,
    teams: list[TeamStats],
    cross_games: list[CrossGameResult],
    sec_response_name: str,
) -> ConferenceStats:
    stats = ConferenceStats(name=name, display=display, teams=teams)
    is_sec = (name == sec_response_name)
    for game in cross_games:
        if not game.played:
            continue
        sec_won = game.sec_won(sec_response_name)
        if sec_won is None:
            continue
        if is_sec:
            stats.h2h_wins += 1 if sec_won else 0
            stats.h2h_losses += 0 if sec_won else 1
        else:
            stats.h2h_wins += 0 if sec_won else 1
            stats.h2h_losses += 1 if sec_won else 0
    return stats


def h2h_leader(sec: ConferenceStats, big10: ConferenceStats) -> str:
    if sec.h2h_wins > sec.h2h_losses:
        margin = sec.h2h_wins - sec.h2h_losses
        return f"SEC leads {sec.h2h_wins}-{sec.h2h_losses} ({margin} game advantage)"
    elif big10.h2h_wins > big10.h2h_losses:
        margin = big10.h2h_wins - big10.h2h_losses
        return f"Big Ten leads {big10.h2h_wins}-{big10.h2h_losses} ({margin} game advantage)"
    elif sec.h2h_wins > 0:
        return f"Series tied {sec.h2h_wins}-{big10.h2h_wins}"
    return "No cross-conference games played yet"
