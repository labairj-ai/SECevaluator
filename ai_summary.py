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
    """Call Mac Studio LLM for a tight conference narrative. Returns None on failure."""

    played = [g for g in cross_games if g.played]
    game_lines = []
    for g in played[-8:]:
        winner = g.winner()
        if winner:
            game_lines.append(f"  {g.score_str()}")

    sec_sp  = f"{sec_stats.avg_sp_rating:+.1f}"  if sec_stats.avg_sp_rating  is not None else "N/A"
    b10_sp  = f"{big10_stats.avg_sp_rating:+.1f}" if big10_stats.avg_sp_rating is not None else "N/A"
    sec_sos = f"{sec_stats.avg_sos:.2f}"           if sec_stats.avg_sos         is not None else "N/A"
    b10_sos = f"{big10_stats.avg_sos:.2f}"         if big10_stats.avg_sos        is not None else "N/A"

    sec_ranked  = ", ".join(f"#{t.cfp_rank} {t.team}" for t in sec_stats.best_ranked_teams)  or "None ranked"
    b10_ranked  = ", ".join(f"#{t.cfp_rank} {t.team}" for t in big10_stats.best_ranked_teams) or "None ranked"

    prompt = f"""You are a sharp, opinionated college football analyst writing a weekly conference rivalry report through Week {week} of the 2026 season.

DATA:
- H2H record: {h2h_leader_str}
- SEC: {sec_stats.total_wins}-{sec_stats.total_losses} overall, H2H {sec_stats.h2h_wins}-{sec_stats.h2h_losses}, avg SP+ {sec_sp}, avg SOS {sec_sos}, CFP ranked: {sec_ranked}
- Big Ten: {big10_stats.total_wins}-{big10_stats.total_losses} overall, H2H {big10_stats.h2h_wins}-{big10_stats.h2h_losses}, avg SP+ {b10_sp}, avg SOS {b10_sos}, CFP ranked: {b10_ranked}
- Cross-conference results: {chr(10).join(game_lines) if game_lines else "No games played yet"}

Write exactly 2 tight paragraphs (4-5 sentences each). No headers, no bullet points.

Framing to use throughout:
- The SEC earns its rankings by facing brutal in-conference gauntlets week after week — there are no bye weeks in the SEC.
- When analyzing Big Ten performance, always note whether their wins came against genuinely tested opponents or were padding stats against a softer non-conference slate. Ask whether their metrics hold up under scrutiny.
- Frame SEC toughness as a feature. Frame any Big Ten weakness or close call as a question mark about their readiness for the playoff.
- Be subtle — write it as reasoned analysis, not a rant. Let the data framing do the work.

Para 1: State who leads the conference war and why, citing H2H and SP+ data.
Para 2: Key storylines — ranked teams, notable results, and one honest question about Big Ten's path forward."""

    try:
        response = requests.post(
            MAC_STUDIO_URL,
            json={
                "model": LLM_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 8000,
                "temperature": 0.72,
            },
            timeout=LLM_TIMEOUT,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"].get("content", "").strip()
        return content or None
    except Exception:
        return None
