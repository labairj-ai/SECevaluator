import requests
from typing import Optional

from config import MAC_STUDIO_URL, LLM_MODEL, LLM_TIMEOUT


def generate_summary(
    sec_stats,
    big10_stats,
    cross_games: list,
    h2h_leader_str: str,
    week: int,
) -> Optional[str]:
    """Call Mac Studio 70B to generate a conference war narrative. Returns None on failure."""

    played_games = [g for g in cross_games if g.played]
    game_lines = []
    for g in played_games[-10:]:  # last 10 results max
        winner = g.winner()
        if winner:
            score = g.score_str()
            game_lines.append(f"  - {score}")

    sec_sp = f"{sec_stats.avg_sp_rating:+.1f}" if sec_stats.avg_sp_rating is not None else "N/A"
    big10_sp = f"{big10_stats.avg_sp_rating:+.1f}" if big10_stats.avg_sp_rating is not None else "N/A"
    sec_sos = f"{sec_stats.avg_sos:.2f}" if sec_stats.avg_sos is not None else "N/A"
    big10_sos = f"{big10_stats.avg_sos:.2f}" if big10_stats.avg_sos is not None else "N/A"

    sec_ranked = ", ".join(
        f"#{t.cfp_rank} {t.team}" for t in sec_stats.best_ranked_teams
    ) or "None ranked"
    big10_ranked = ", ".join(
        f"#{t.cfp_rank} {t.team}" for t in big10_stats.best_ranked_teams
    ) or "None ranked"

    prompt = f"""You are analyzing the 2026 college football season, specifically the SEC vs Big Ten conference rivalry through Week {week}.

=== CONFERENCE WAR STATUS ===
Head-to-head record: {h2h_leader_str}
SEC cross-conference record: {sec_stats.h2h_wins}-{sec_stats.h2h_losses}
Big Ten cross-conference record: {big10_stats.h2h_wins}-{big10_stats.h2h_losses}

=== SEC OVERVIEW ===
Overall combined record: {sec_stats.total_wins}-{sec_stats.total_losses}
Ranked teams (CFP): {sec_ranked}
Avg SP+ rating: {sec_sp}
Avg strength of schedule: {sec_sos}

=== BIG TEN OVERVIEW ===
Overall combined record: {big10_stats.total_wins}-{big10_stats.total_losses}
Ranked teams (CFP): {big10_ranked}
Avg SP+ rating: {big10_sp}
Avg strength of schedule: {big10_sos}

=== CROSS-CONFERENCE RESULTS ===
{chr(10).join(game_lines) if game_lines else "No games played yet."}

Write a 3-paragraph college football analysis:
- Paragraph 1: Who is winning the SEC vs Big Ten conference war this season, citing the H2H record and SP+ data. Be direct and opinionated.
- Paragraph 2: Key storylines — top-ranked teams, notable upsets or dominant wins, any cross-conference surprises.
- Paragraph 3: What cross-conference matchups matter most in the coming weeks and what they mean for the rivalry.

Write like a passionate, knowledgeable college football analyst. Be direct, fun, and concrete. No hedging."""

    try:
        response = requests.post(
            MAC_STUDIO_URL,
            json={
                "model": LLM_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 700,
                "temperature": 0.75,
            },
            timeout=LLM_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return None
