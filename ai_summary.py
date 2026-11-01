"""Evidence-based narrative: every claim comes from the displayed report data."""
from config import YEAR
from metrics import h2h_leader, build_conference_stats


def generate_summary(sec_stats, big10_stats, cross_games, h2h_leader_str, week, year=YEAR, season_type="regular"):
    # Recompute the headline rather than trusting a potentially stale caller string.
    leader = h2h_leader(sec_stats, big10_stats)
    played = [g for g in cross_games if g.winner() is not None]
    expected = build_conference_stats("SEC", "SEC", [], cross_games, "SEC")
    if ((sec_stats.h2h_wins, sec_stats.h2h_losses) != (expected.h2h_wins, expected.h2h_losses)
            or (big10_stats.h2h_losses, big10_stats.h2h_wins) != (expected.h2h_wins, expected.h2h_losses)):
        raise ValueError("Inconsistent head-to-head summary evidence")
    period = f"postseason week {week}" if season_type == "postseason" else f"week {week}"
    sentences = [f"Season-to-date {year} report (report {period}): {leader}."]
    sentences.append(f"Overall records are SEC {sec_stats.total_wins}-{sec_stats.total_losses} "
                     f"and Big Ten {big10_stats.total_wins}-{big10_stats.total_losses}; "
                     "these include conference games and are separate from head-to-head results.")
    for label, attr in (("SP+", "avg_sp_rating"),):
        a, b = getattr(sec_stats, attr), getattr(big10_stats, attr)
        if a is None or b is None:
            sentences.append(f"The {label} comparison is unavailable because rating data is incomplete.")
        else:
            lead = "Neither conference leads" if a == b else ("SEC leads" if a > b else "Big Ten leads")
            sentences.append(f"{lead} on average {label}: SEC {a:+.2f}, Big Ten {b:+.2f}.")
    sentences.append("Nonconference opponent SP+ (rated opponents only; game-weighted): "
                     f"SEC {sec_stats.sos_str}; Big Ten {big10_stats.sos_str}.")
    sentences.append("Unrated opponents are excluded; this is not a complete schedule-strength comparison.")
    results = "; ".join(g.score_str() for g in played[-8:])
    second = f"Completed head-to-head results (latest eight): {results}." if results else "No completed SEC–Big Ten games are present in the verified season data."
    if sec_stats.poll_label and sec_stats.poll_label == big10_stats.poll_label:
        second += f" Ranked teams ({sec_stats.poll_label}): SEC {sec_stats.ranked_teams}, Big Ten {big10_stats.ranked_teams}."
    else:
        second += " Rankings are unavailable; missing poll data does not mean zero ranked teams."
    second += " Head-to-head results and rating comparisons measure different things; neither alone establishes an overall conference winner."
    return " ".join(sentences) + "\n\n" + second
