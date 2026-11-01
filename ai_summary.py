"""Evidence-based narrative: every claim comes from the displayed report data."""
from config import YEAR
from metrics import h2h_leader


def generate_summary(sec_stats, big10_stats, cross_games, h2h_leader_str, week, year=YEAR):
    # Recompute the headline rather than trusting a potentially stale caller string.
    leader = h2h_leader(sec_stats, big10_stats)
    played = [g for g in cross_games if g.winner() is not None]
    if (sec_stats.h2h_wins != big10_stats.h2h_losses
            or sec_stats.h2h_losses != big10_stats.h2h_wins
            or len(played) != sec_stats.h2h_wins + sec_stats.h2h_losses):
        raise ValueError("Inconsistent head-to-head summary evidence")
    sentences = [f"Through Week {week} of {year}: {leader}."]
    sentences.append(f"Overall records are SEC {sec_stats.total_wins}-{sec_stats.total_losses} "
                     f"and Big Ten {big10_stats.total_wins}-{big10_stats.total_losses}; "
                     "these include conference games and are separate from head-to-head results.")
    for label, attr in (("SP+", "avg_sp_rating"), ("nonconference opponent SP+", "avg_sos")):
        a, b = getattr(sec_stats, attr), getattr(big10_stats, attr)
        if a is None or b is None:
            sentences.append(f"The {label} comparison is unavailable because rating data is incomplete.")
        else:
            lead = "Neither conference leads" if a == b else ("SEC leads" if a > b else "Big Ten leads")
            sentences.append(f"{lead} on average {label}: SEC {a:+.2f}, Big Ten {b:+.2f}.")
    results = "; ".join(g.score_str() for g in played[-8:])
    second = f"Completed head-to-head results: {results}." if results else "No completed SEC–Big Ten games are present in the verified season data."
    second += f" Ranked teams in the selected poll: SEC {sec_stats.ranked_teams}, Big Ten {big10_stats.ranked_teams}."
    second += " Head-to-head results and rating comparisons measure different things; neither alone establishes an overall conference winner."
    return " ".join(sentences) + "\n\n" + second
