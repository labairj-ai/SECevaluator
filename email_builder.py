import base64
import os
from datetime import date, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

from metrics import TeamStats, ConferenceStats, CrossGameResult


# ── Colors ───────────────────────────────────────────────────────────────────
SEC_COLOR    = "#990000"
BIG10_COLOR  = "#003087"
HEADER_BG    = "#1a1a2e"
TABLE_HDR_BG = "#2d2d44"
ROW_ALT      = "#f5f5f5"
WIN_GREEN    = "#c8f0c8"
LOSS_RED     = "#f7c5c5"


def _next_sunday() -> date:
    today = date.today()
    days_ahead = 6 - today.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return today + timedelta(days=days_ahead)


def _conf_color(conf_display: str) -> str:
    return SEC_COLOR if conf_display == "SEC" else BIG10_COLOR


def _delta_str(d: Optional[float], higher_is_better: bool = True) -> str:
    """Format a week-over-week delta with arrow and color."""
    if d is None:
        return ""
    if abs(d) < 0.005:
        return "<span style='color:#888;'>→ 0</span>"
    arrow = "▲" if d > 0 else "▼"
    color = "#228822" if (d > 0) == higher_is_better else "#cc2222"
    return f"<span style='color:{color};font-size:11px;'>{arrow} {abs(d):.2f}</span>"


# ── HTML helpers ─────────────────────────────────────────────────────────────

def _td(content: str, bg: str = "", bold: bool = False, align: str = "left", color: str = "") -> str:
    style = f"padding:4px 7px;border:1px solid #ddd;text-align:{align};font-size:12px;"
    if bg:    style += f"background:{bg};"
    if bold:  style += "font-weight:bold;"
    if color: style += f"color:{color};"
    return f"<td style='{style}'>{content}</td>"


def _th(content: str, bg: str = TABLE_HDR_BG, color: str = "white", title: str = "") -> str:
    tip = f" title='{title}'" if title else ""
    return (f"<th{tip} style='padding:5px 7px;border:1px solid #555;background:{bg};"
            f"color:{color};text-align:left;cursor:default;font-size:12px;white-space:nowrap;'>{content}</th>")


def _record_cell(t: TeamStats, bg: str) -> str:
    # Single cell: "8-1" bold, then "(6-1 conf / 2-0 ext)" in smaller muted text
    sub = f"<span style='font-size:10px;color:#777;'>{t.conf_record_str}&nbsp;conf&nbsp;/&nbsp;{t.nonconf_record_str}&nbsp;ext</span>"
    style = f"padding:4px 7px;border:1px solid #ddd;background:{bg};white-space:nowrap;"
    return f"<td style='{style}'><strong>{t.record_str}</strong><br>{sub}</td>"


def _team_row(t: TeamStats, idx: int) -> str:
    bg = ROW_ALT if idx % 2 else "white"
    if t.cfp_rank and t.cfp_rank <= 5:
        bg = "#fff9c4"
    return (
        "<tr>"
        + _td(t.cfp_rank_str, bg=bg, bold=bool(t.cfp_rank), align="center")
        + _td(t.team, bg=bg, bold=True)
        + _record_cell(t, bg)
        + _td(t.sp_str, bg=bg, align="right")
        + _td(t.sos_str, bg=bg, align="right")
        + "</tr>"
    )


def _standings_table_html(conf: ConferenceStats) -> str:
    color = _conf_color(conf.display)
    rows = "".join(_team_row(t, i) for i, t in enumerate(conf.teams))
    return f"""
<table style='border-collapse:collapse;width:100%;font-family:Arial,sans-serif;font-size:12px;margin-bottom:20px;table-layout:fixed;'>
  <caption style='text-align:left;font-size:15px;font-weight:bold;color:{color};padding-bottom:5px;'>
    {conf.display} Standings
    <span style='font-size:11px;font-weight:normal;color:#888;margin-left:8px;'>
      <span style='background:#fff9c4;padding:1px 5px;border:1px solid #ddd;'>&#9632;</span> = CFP top 5
    </span>
  </caption>
  <colgroup>
    <col style='width:42px;'>
    <col style='width:auto;'>
    <col style='width:120px;'>
    <col style='width:48px;'>
    <col style='width:56px;'>
  </colgroup>
  <thead><tr>
    {_th("CFP", title="College Football Playoff ranking. — = unranked.")}
    {_th("Team")}
    {_th("Record (conf / ext)", title="Overall record. Sub-line: conference record / external (non-conference) record.")}
    {_th("SP+", title="ESPN predictive rating vs avg opponent. 0 = average FBS; higher = better.")}
    {_th("OOC SOS", title="Avg SP+ of non-conference opponents faced. Higher = tougher external slate.")}
  </tr></thead>
  <tbody>{rows}</tbody>
</table>
"""


def _cross_conf_table_html(cross_games: list[CrossGameResult], sec_response: str) -> str:
    played = [g for g in cross_games if g.played]
    if not played:
        return "<p style='color:#666;font-style:italic;font-family:Arial,sans-serif;'>No cross-conference games played yet.</p>"

    rows = ""
    for g in played:
        sec_won = g.sec_won(sec_response)
        result_bg = WIN_GREEN if sec_won else LOSS_RED
        winner = g.winner() or ""
        loser  = g.away_team if winner == g.home_team else g.home_team
        pts_w  = g.home_points if winner == g.home_team else g.away_points
        pts_l  = g.away_points if winner == g.home_team else g.home_points
        loc    = " (N)" if g.neutral_site else ""
        score  = f"{winner} {pts_w}, {loser} {pts_l}{loc}"
        conf_w = g.home_conference if winner == g.home_team else g.away_conference
        rows += (
            "<tr>"
            + _td(f"Wk {g.week}", align="center")
            + _td(g.game_date, align="center")
            + _td(score)
            + _td(conf_w, bold=True, color=_conf_color(conf_w), bg=result_bg)
            + "</tr>"
        )

    return f"""
<table style='border-collapse:collapse;width:100%;font-family:Arial,sans-serif;font-size:12px;margin-bottom:20px;'>
  <caption style='text-align:left;font-size:15px;font-weight:bold;color:#333;padding-bottom:5px;'>
    SEC vs Big Ten Cross-Conference Results
    <span style='font-size:12px;font-weight:normal;color:#888;margin-left:8px;'>
      (Green = SEC win, Red = Big Ten win)
    </span>
  </caption>
  <thead><tr>
    {_th("Week")} {_th("Date")} {_th("Result")} {_th("Winner")}
  </tr></thead>
  <tbody>{rows}</tbody>
</table>
"""


def _comparison_table_html(sec: ConferenceStats, big10: ConferenceStats) -> str:
    def _row(label: str, sec_val: str, big10_val: str, sec_better: Optional[bool] = None,
             sec_delta: str = "", b10_delta: str = "", tip: str = "") -> str:
        sec_bg  = WIN_GREEN if sec_better is True  else (LOSS_RED if sec_better is False else "white")
        b10_bg  = WIN_GREEN if sec_better is False else (LOSS_RED if sec_better is True  else "white")
        label_td = f"<td style='padding:5px 10px;font-weight:bold;border:1px solid #ddd;' title='{tip}'>{label}</td>"
        sec_cell  = f"<td style='padding:5px 10px;text-align:center;border:1px solid #ddd;background:{sec_bg};'>{sec_val}<br>{sec_delta}</td>"
        b10_cell  = f"<td style='padding:5px 10px;text-align:center;border:1px solid #ddd;background:{b10_bg};'>{big10_val}<br>{b10_delta}</td>"
        return f"<tr>{label_td}{sec_cell}{b10_cell}</tr>"

    sec_sp  = sec.avg_sp_rating
    b10_sp  = big10.avg_sp_rating
    sec_sos = sec.avg_sos
    b10_sos = big10.avg_sos

    rows = [
        _row(
            "H2H Record",
            f"{sec.h2h_wins}-{sec.h2h_losses}",
            f"{big10.h2h_wins}-{big10.h2h_losses}",
            sec_better=(sec.h2h_wins > sec.h2h_losses) if (sec.h2h_wins + sec.h2h_losses) > 0 else None,
            tip="Head-to-head record in games between SEC and Big Ten teams this season.",
        ),
        _row(
            "Overall Record",
            f"{sec.total_wins}-{sec.total_losses}",
            f"{big10.total_wins}-{big10.total_losses}",
            tip="Combined wins and losses across all games, including within-conference matchups.",
        ),
        _row(
            "External Record",
            f"{sec.nonconf_wins}-{sec.nonconf_losses}",
            f"{big10.nonconf_wins}-{big10.nonconf_losses}",
            sec_better=(sec.nonconf_wins / max(sec.nonconf_wins + sec.nonconf_losses, 1)) >
                       (big10.nonconf_wins / max(big10.nonconf_wins + big10.nonconf_losses, 1))
                       if (sec.nonconf_wins + sec.nonconf_losses + big10.nonconf_wins + big10.nonconf_losses) > 0 else None,
            tip="Record against non-conference opponents only — same-conference games (SEC vs SEC, Big Ten vs Big Ten) are excluded.",
        ),
        _row(
            "Avg SP+ ↑ better",
            f"{sec_sp:+.1f}" if sec_sp is not None else "N/A",
            f"{b10_sp:+.1f}" if b10_sp is not None else "N/A",
            sec_better=(sec_sp > b10_sp) if (sec_sp and b10_sp) else None,
            sec_delta=_delta_str(sec.d_avg_sp, higher_is_better=True),
            b10_delta=_delta_str(big10.d_avg_sp, higher_is_better=True),
            tip="SP+ is ESPN's predictive team quality rating, adjusted for opponent strength. National average = 0. Higher = better. Shows average across all conference teams.",
        ),
        _row(
            "Avg SOS ↑ harder",
            f"{sec_sos:.2f}" if sec_sos is not None else "N/A",
            f"{b10_sos:.2f}" if b10_sos is not None else "N/A",
            sec_better=(sec_sos > b10_sos) if (sec_sos and b10_sos) else None,
            sec_delta=_delta_str(sec.d_avg_sos, higher_is_better=True),
            b10_delta=_delta_str(big10.d_avg_sos, higher_is_better=True),
            tip="Strength of Schedule — how difficult each conference's average opponent slate has been. Higher = harder schedule. Arrows show change vs last week.",
        ),
        _row(
            "CFP Top-25 Teams",
            str(sec.ranked_teams),
            str(big10.ranked_teams),
            sec_better=sec.ranked_teams > big10.ranked_teams if sec.ranked_teams != big10.ranked_teams else None,
            tip="Number of teams ranked in the College Football Playoff top 25.",
        ),
    ]

    return f"""
<table style='border-collapse:collapse;width:100%;font-family:Arial,sans-serif;font-size:12px;margin-bottom:20px;'>
  <caption style='text-align:left;font-size:15px;font-weight:bold;color:#333;padding-bottom:5px;'>
    Conference Comparison
    <span style='font-size:11px;font-weight:normal;color:#888;margin-left:8px;'>▲▼ = change vs last week</span>
  </caption>
  <thead><tr>
    {_th("Metric")}
    {_th("SEC", bg=SEC_COLOR)}
    {_th("Big Ten", bg=BIG10_COLOR)}
  </tr></thead>
  <tbody>{"".join(rows)}</tbody>
</table>
"""


def _metric_legend_html() -> str:
    return """
<div style='font-family:Arial,sans-serif;font-size:11px;color:#888;background:#f9f9f9;
            border:1px solid #e0e0e0;border-radius:4px;padding:10px 14px;margin-bottom:20px;'>
  <strong style='color:#555;'>Metric Guide:</strong>
  <span style='margin-left:12px;'><strong>External</strong> — wins/losses vs non-conference opponents only; same-conference games excluded.</span>
  <span style='margin-left:12px;'><strong>SP+</strong> — ESPN's predictive rating adjusted for opponent quality. 0 = average FBS team; +10 means ~10 pts/game better than average.</span>
  <span style='margin-left:12px;'><strong>OOC SOS</strong> — avg SP+ of non-conference opponents faced. Higher = harder external schedule. Arrows (▲▼) show week-over-week change.</span>
  <span style='margin-left:12px;'><strong>CFP Rank</strong> — College Football Playoff committee ranking. Top 12 earn automatic playoff bids.</span>
</div>
"""


def build_html(
    sec: ConferenceStats,
    big10: ConferenceStats,
    cross_games: list[CrossGameResult],
    ai_text: Optional[str],
    h2h_leader_str: str,
    week: int,
    sec_response: str,
    year: int,
) -> str:
    next_sun = _next_sunday().strftime("%B %d, %Y")

    if ai_text:
        paragraphs = "\n".join(
            f"<p style='margin:10px 0;'>{p.strip()}</p>"
            for p in ai_text.split("\n\n") if p.strip()
        )
        ai_section = f"""
<div style='background:#f0f4ff;border-left:4px solid #6688cc;padding:16px 20px;
            margin-bottom:24px;border-radius:4px;font-family:Arial,sans-serif;
            font-size:14px;line-height:1.6;'>
  <div style='font-weight:bold;font-size:14px;margin-bottom:8px;color:#334;'>
    AI Analysis — Conference War Breakdown
  </div>
  {paragraphs}
</div>
"""
    else:
        ai_section = "<p style='color:#888;font-style:italic;font-family:Arial,sans-serif;'>AI summary unavailable (Mac Studio offline).</p>"

    return f"""<!DOCTYPE html>
<html>
<body style='margin:0;padding:0;background:#f0f0f0;'>
<div style='max-width:600px;margin:20px auto;background:white;border-radius:8px;
            overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.15);font-family:Arial,sans-serif;'>

  <div style='background:{HEADER_BG};color:white;padding:18px 20px;'>
    <div style='font-size:21px;font-weight:bold;letter-spacing:0.5px;'>⚔ SEC vs Big Ten — Conference War</div>
    <div style='font-size:13px;margin-top:4px;opacity:0.7;'>{year} Season &bull; Week {week} Report</div>
    <div style='margin-top:12px;font-size:17px;font-weight:bold;'>
      <span style='color:#ff9999;'>SEC</span>
      <span style='margin:0 10px;opacity:0.5;'>vs</span>
      <span style='color:#99bbff;'>Big Ten</span>
      <span style='margin-left:18px;font-size:14px;font-weight:normal;opacity:0.85;'>{h2h_leader_str}</span>
    </div>
  </div>

  <div style='padding:16px 18px;'>
    {ai_section}
    {_metric_legend_html()}
    {_comparison_table_html(sec, big10)}
    {_cross_conf_table_html(cross_games, sec_response)}
    {_standings_table_html(sec)}
    {_standings_table_html(big10)}
    <div style='border-top:1px solid #eee;margin-top:24px;padding-top:12px;
                font-size:11px;color:#aaa;text-align:center;'>
      SECevaluator &bull; Next email: {next_sun} &bull; Data: CollegeFootballData.com
    </div>
  </div>
</div>
</body>
</html>"""


def build_text(
    sec: ConferenceStats,
    big10: ConferenceStats,
    cross_games: list[CrossGameResult],
    ai_text: Optional[str],
    h2h_leader_str: str,
    week: int,
    year: int,
) -> str:
    lines = [
        f"SECevaluator — {year} Season Week {week}",
        "=" * 50,
        f"SEC vs Big Ten H2H: {h2h_leader_str}",
        "",
    ]
    if ai_text:
        lines += ["AI ANALYSIS", "-" * 30, ai_text, ""]

    lines += ["CONFERENCE COMPARISON (SP+ = quality rating, 0=avg; SOS = schedule difficulty, higher=harder)", "-" * 30]
    sp_note = "(▲▼ = change vs last week)"
    lines.append(f"{'Metric':<26} {'SEC':>10} {'Big Ten':>10}  {sp_note}")

    def _fmt_delta(d):
        if d is None: return ""
        if abs(d) < 0.005: return "→0"
        return f"{'▲' if d>0 else '▼'}{abs(d):.2f}"

    lines.append(f"{'H2H Record':<26} {sec.h2h_wins}-{sec.h2h_losses:>9} {big10.h2h_wins}-{big10.h2h_losses:>9}")
    lines.append(f"{'Overall Record':<26} {sec.total_wins}-{sec.total_losses:>9} {big10.total_wins}-{big10.total_losses:>9}")
    lines.append(f"{'External Record (OOC)':<26} {sec.nonconf_wins}-{sec.nonconf_losses:>9} {big10.nonconf_wins}-{big10.nonconf_losses:>9}")
    if sec.avg_sp_rating and big10.avg_sp_rating:
        d1 = _fmt_delta(sec.d_avg_sp)
        d2 = _fmt_delta(big10.d_avg_sp)
        lines.append(f"{'Avg SP+':<26} {sec.avg_sp_rating:>+10.1f} {big10.avg_sp_rating:>+10.1f}  {d1} / {d2}")
    if sec.avg_sos and big10.avg_sos:
        d1 = _fmt_delta(sec.d_avg_sos)
        d2 = _fmt_delta(big10.d_avg_sos)
        lines.append(f"{'Avg SOS':<26} {sec.avg_sos:>10.2f} {big10.avg_sos:>10.2f}  {d1} / {d2}")
    lines.append(f"{'CFP Top-25 Teams':<26} {sec.ranked_teams:>10} {big10.ranked_teams:>10}")
    lines.append("")

    played = [g for g in cross_games if g.played]
    if played:
        lines += ["CROSS-CONFERENCE RESULTS", "-" * 30]
        for g in played:
            lines.append(f"  Wk {g.week:2d} | {g.score_str()}")
        lines.append("")

    for conf in (sec, big10):
        lines += [f"{conf.display} STANDINGS", "-" * 30,
                  f"  {'Team':<25} {'Overall':>8} {'Conf':>6} {'External':>9} {'SP+':>6} {'OOC SOS':>8} {'CFP':>5}"]
        for t in conf.teams:
            lines.append(
                f"  {t.team:<25} {t.record_str:>8} {t.conf_record_str:>6}"
                f" {t.nonconf_record_str:>9} {t.sp_str:>6} {t.sos_str:>8} {t.cfp_rank_str:>5}"
            )
        lines.append("")

    lines.append(f"Next email: {_next_sunday().strftime('%B %d, %Y')}")
    return "\n".join(lines)


def build_email(
    sec: ConferenceStats,
    big10: ConferenceStats,
    cross_games: list[CrossGameResult],
    ai_text: Optional[str],
    h2h_leader_str: str,
    week: int,
    sec_response: str,
    year: int,
) -> tuple[str, str, str]:
    subject = f"SECevaluator {year} Wk {week} | {h2h_leader_str}"
    text = build_text(sec, big10, cross_games, ai_text, h2h_leader_str, week, year)
    html = build_html(sec, big10, cross_games, ai_text, h2h_leader_str, week, sec_response, year)
    return subject, text, html


# ── Gmail ────────────────────────────────────────────────────────────────────

def get_gmail_service():
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    token_path = Path("token.json")
    if not token_path.exists():
        raise FileNotFoundError("token.json not found — copy from dansbytracker/")
    creds = Credentials.from_authorized_user_file(
        str(token_path), ["https://www.googleapis.com/auth/gmail.send"]
    )
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json(), encoding="utf-8")
    return build("gmail", "v1", credentials=creds)


def send_gmail(sender: str, recipients: list[str], subject: str, text_body: str, html_body: str) -> None:
    if not sender:
        raise ValueError("SENDER_EMAIL is empty.")
    msg = MIMEMultipart("alternative")
    msg["To"]      = ", ".join(recipients)
    msg["From"]    = sender
    msg["Subject"] = subject
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    get_gmail_service().users().messages().send(userId="me", body={"raw": raw}).execute()
