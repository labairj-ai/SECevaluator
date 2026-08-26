import base64
import os
from datetime import date, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

from metrics import TeamStats, ConferenceStats, CrossGameResult


# ── Colors ───────────────────────────────────────────────────────────────────
SEC_COLOR = "#990000"     # crimson
BIG10_COLOR = "#003087"   # navy
HEADER_BG = "#1a1a2e"
TABLE_HEADER_BG = "#2d2d44"
ROW_ALT = "#f5f5f5"
WIN_GREEN = "#c8f0c8"
LOSS_RED = "#f7c5c5"


def _next_sunday() -> date:
    today = date.today()
    days_ahead = 6 - today.weekday()  # Sunday = 6
    if days_ahead <= 0:
        days_ahead += 7
    return today + timedelta(days=days_ahead)


def _conf_color(conf_display: str) -> str:
    return SEC_COLOR if conf_display == "SEC" else BIG10_COLOR


# ── HTML helpers ─────────────────────────────────────────────────────────────

def _td(content: str, bg: str = "", bold: bool = False, align: str = "left", color: str = "") -> str:
    style = f"padding:5px 10px;border:1px solid #ddd;text-align:{align};"
    if bg:
        style += f"background:{bg};"
    if bold:
        style += "font-weight:bold;"
    if color:
        style += f"color:{color};"
    return f"<td style='{style}'>{content}</td>"


def _th(content: str, bg: str = TABLE_HEADER_BG, color: str = "white") -> str:
    return f"<th style='padding:6px 10px;border:1px solid #555;background:{bg};color:{color};text-align:left;'>{content}</th>"


def _team_row(t: TeamStats, idx: int, highlight: bool = False) -> str:
    bg = "#fff9c4" if highlight else (ROW_ALT if idx % 2 else "white")
    rank_str = t.cfp_rank_str
    rank_bold = t.cfp_rank is not None
    return (
        "<tr>"
        + _td(rank_str, bg=bg, bold=rank_bold, align="center")
        + _td(t.team, bg=bg, bold=True)
        + _td(t.record_str, bg=bg)
        + _td(t.sp_str, bg=bg, align="right")
        + _td(t.sos_str, bg=bg, align="right")
        + "</tr>"
    )


def _standings_table_html(conf: ConferenceStats) -> str:
    color = _conf_color(conf.display)
    rows = "".join(_team_row(t, i) for i, t in enumerate(conf.teams))
    return f"""
<table style='border-collapse:collapse;width:100%;font-family:Arial,sans-serif;font-size:13px;margin-bottom:20px;'>
  <caption style='text-align:left;font-size:16px;font-weight:bold;color:{color};padding-bottom:6px;'>
    {conf.display} Standings
  </caption>
  <thead>
    <tr>
      {_th("CFP")}
      {_th("Team")}
      {_th("Record (Conf)")}
      {_th("SP+")}
      {_th("SOS")}
    </tr>
  </thead>
  <tbody>{rows}</tbody>
</table>
"""


def _cross_conf_table_html(cross_games: list[CrossGameResult], sec_response: str) -> str:
    played = [g for g in cross_games if g.played]
    if not played:
        return "<p style='color:#666;font-style:italic;'>No cross-conference games played yet.</p>"

    rows = ""
    for g in played:
        sec_won = g.sec_won(sec_response)
        result_bg = WIN_GREEN if sec_won else LOSS_RED
        winner = g.winner() or ""
        loser = g.away_team if winner == g.home_team else g.home_team
        pts_w = g.home_points if winner == g.home_team else g.away_points
        pts_l = g.away_points if winner == g.home_team else g.home_points
        loc = " (N)" if g.neutral_site else ""
        score = f"{winner} {pts_w}, {loser} {pts_l}{loc}"
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
<table style='border-collapse:collapse;width:100%;font-family:Arial,sans-serif;font-size:13px;margin-bottom:20px;'>
  <caption style='text-align:left;font-size:16px;font-weight:bold;color:#333;padding-bottom:6px;'>
    SEC vs Big Ten Cross-Conference Results
  </caption>
  <thead>
    <tr>
      {_th("Week")}
      {_th("Date")}
      {_th("Result")}
      {_th("Winner")}
    </tr>
  </thead>
  <tbody>{rows}</tbody>
</table>
"""


def _comparison_table_html(sec: ConferenceStats, big10: ConferenceStats) -> str:
    def _row(label: str, sec_val: str, big10_val: str, sec_better: Optional[bool] = None) -> str:
        sec_bg = WIN_GREEN if sec_better is True else (LOSS_RED if sec_better is False else "white")
        b10_bg = WIN_GREEN if sec_better is False else (LOSS_RED if sec_better is True else "white")
        return (
            f"<tr>"
            f"<td style='padding:5px 10px;font-weight:bold;border:1px solid #ddd;'>{label}</td>"
            f"<td style='padding:5px 10px;text-align:center;border:1px solid #ddd;background:{sec_bg};'>{sec_val}</td>"
            f"<td style='padding:5px 10px;text-align:center;border:1px solid #ddd;background:{b10_bg};'>{big10_val}</td>"
            f"</tr>"
        )

    sec_sp = sec.avg_sp_rating
    b10_sp = big10.avg_sp_rating
    sec_sos = sec.avg_sos
    b10_sos = big10.avg_sos

    rows = [
        _row(
            "H2H Record",
            f"{sec.h2h_wins}-{sec.h2h_losses}",
            f"{big10.h2h_wins}-{big10.h2h_losses}",
            sec_better=sec.h2h_wins > sec.h2h_losses if (sec.h2h_wins + sec.h2h_losses) > 0 else None,
        ),
        _row(
            "Overall Record",
            f"{sec.total_wins}-{sec.total_losses}",
            f"{big10.total_wins}-{big10.total_losses}",
            sec_better=None,
        ),
        _row(
            "Avg SP+ Rating",
            f"{sec_sp:+.1f}" if sec_sp is not None else "N/A",
            f"{b10_sp:+.1f}" if b10_sp is not None else "N/A",
            sec_better=(sec_sp > b10_sp) if (sec_sp is not None and b10_sp is not None) else None,
        ),
        _row(
            "Avg SOS",
            f"{sec_sos:.2f}" if sec_sos is not None else "N/A",
            f"{b10_sos:.2f}" if b10_sos is not None else "N/A",
            sec_better=(sec_sos > b10_sos) if (sec_sos is not None and b10_sos is not None) else None,
        ),
        _row("CFP Ranked Teams", str(sec.ranked_teams), str(big10.ranked_teams),
             sec_better=sec.ranked_teams > big10.ranked_teams if sec.ranked_teams != big10.ranked_teams else None),
    ]

    return f"""
<table style='border-collapse:collapse;width:100%;font-family:Arial,sans-serif;font-size:13px;margin-bottom:20px;'>
  <caption style='text-align:left;font-size:16px;font-weight:bold;color:#333;padding-bottom:6px;'>
    Conference Comparison
  </caption>
  <thead>
    <tr>
      {_th("Metric")}
      {_th("SEC", bg=SEC_COLOR)}
      {_th("Big Ten", bg=BIG10_COLOR)}
    </tr>
  </thead>
  <tbody>{"".join(rows)}</tbody>
</table>
"""


def build_html(
    sec: ConferenceStats,
    big10: ConferenceStats,
    cross_games: list[CrossGameResult],
    ai_text: Optional[str],
    h2h_leader_str: str,
    week: int,
    sec_response: str,
) -> str:
    next_sun = _next_sunday().strftime("%B %d, %Y")

    ai_section = ""
    if ai_text:
        paragraphs = "\n".join(f"<p style='margin:10px 0;'>{p.strip()}</p>" for p in ai_text.split("\n\n") if p.strip())
        ai_section = f"""
<div style='background:#f0f4ff;border-left:4px solid #6688cc;padding:16px 20px;margin-bottom:24px;border-radius:4px;font-family:Arial,sans-serif;font-size:14px;line-height:1.6;'>
  <div style='font-weight:bold;font-size:15px;margin-bottom:10px;color:#334;'>AI Analysis — 70B Conference Breakdown</div>
  {paragraphs}
</div>
"""
    else:
        ai_section = "<p style='color:#888;font-style:italic;font-family:Arial,sans-serif;'>AI summary unavailable (Mac Studio offline).</p>"

    return f"""<!DOCTYPE html>
<html>
<body style='margin:0;padding:0;background:#f0f0f0;'>
<div style='max-width:700px;margin:20px auto;background:white;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.15);font-family:Arial,sans-serif;'>

  <!-- Header -->
  <div style='background:{HEADER_BG};color:white;padding:24px 28px;'>
    <div style='font-size:22px;font-weight:bold;letter-spacing:1px;'>⚔ SEC vs Big Ten — Conference War</div>
    <div style='font-size:14px;margin-top:6px;opacity:0.8;'>Week {week} Report</div>
    <div style='margin-top:14px;font-size:18px;font-weight:bold;'>
      <span style='color:#ff9999;'>SEC</span>
      <span style='margin:0 10px;opacity:0.6;'>vs</span>
      <span style='color:#99bbff;'>Big Ten</span>
      <span style='margin-left:20px;font-size:16px;font-weight:normal;opacity:0.9;'>{h2h_leader_str}</span>
    </div>
  </div>

  <!-- Body -->
  <div style='padding:24px 28px;'>

    {ai_section}

    {_comparison_table_html(sec, big10)}

    {_cross_conf_table_html(cross_games, sec_response)}

    {_standings_table_html(sec)}

    {_standings_table_html(big10)}

    <!-- Footer -->
    <div style='border-top:1px solid #eee;margin-top:24px;padding-top:14px;font-size:12px;color:#999;text-align:center;'>
      SECevaluator &bull; Next email: Sunday {next_sun} &bull; Data: CollegeFootballData.com
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
) -> str:
    lines = []
    lines.append(f"SECevaluator — Week {week} Report")
    lines.append("=" * 50)
    lines.append(f"SEC vs Big Ten H2H: {h2h_leader_str}")
    lines.append("")

    if ai_text:
        lines.append("AI ANALYSIS")
        lines.append("-" * 30)
        lines.append(ai_text)
        lines.append("")

    lines.append("CONFERENCE COMPARISON")
    lines.append("-" * 30)
    lines.append(f"{'Metric':<25} {'SEC':>10} {'Big Ten':>10}")
    lines.append(f"{'H2H Record':<25} {sec.h2h_wins}-{sec.h2h_losses:>8} {big10.h2h_wins}-{big10.h2h_losses:>8}")
    lines.append(f"{'Overall Record':<25} {sec.total_wins}-{sec.total_losses:>8} {big10.total_wins}-{big10.total_losses:>8}")
    if sec.avg_sp_rating is not None and big10.avg_sp_rating is not None:
        lines.append(f"{'Avg SP+':<25} {sec.avg_sp_rating:>+10.1f} {big10.avg_sp_rating:>+10.1f}")
    lines.append(f"{'CFP Ranked Teams':<25} {sec.ranked_teams:>10} {big10.ranked_teams:>10}")
    lines.append("")

    played = [g for g in cross_games if g.played]
    if played:
        lines.append("CROSS-CONFERENCE RESULTS")
        lines.append("-" * 30)
        for g in played:
            lines.append(f"  Wk {g.week:2d} | {g.score_str()}")
        lines.append("")

    for conf in (sec, big10):
        lines.append(f"{conf.display} STANDINGS")
        lines.append("-" * 30)
        lines.append(f"  {'Team':<25} {'Record':<15} {'SP+':>6} {'CFP':>6}")
        for t in conf.teams:
            rank = f"#{t.cfp_rank}" if t.cfp_rank else ""
            lines.append(f"  {t.team:<25} {t.record_str:<15} {t.sp_str:>6} {rank:>6}")
        lines.append("")

    lines.append(f"Next email: Sunday {_next_sunday().strftime('%B %d, %Y')}")
    return "\n".join(lines)


def build_email(
    sec: ConferenceStats,
    big10: ConferenceStats,
    cross_games: list[CrossGameResult],
    ai_text: Optional[str],
    h2h_leader_str: str,
    week: int,
    sec_response: str,
) -> tuple[str, str, str]:
    subject = f"SECevaluator — Wk {week} | {h2h_leader_str}"
    text = build_text(sec, big10, cross_games, ai_text, h2h_leader_str, week)
    html = build_html(sec, big10, cross_games, ai_text, h2h_leader_str, week, sec_response)
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
    msg["To"] = ", ".join(recipients)
    msg["From"] = sender
    msg["Subject"] = subject
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    get_gmail_service().users().messages().send(userId="me", body={"raw": raw}).execute()
