#!/usr/bin/env python3
import os
import sys
from datetime import date, datetime

from config import (
    RECIPIENTS, SENDER_EMAIL, TEST_TO_EMAILS,
    SEC_CONF_PARAM, BIG10_CONF_PARAM,
    SEC_CONF_RESPONSE, BIG10_CONF_RESPONSE,
    SEC_DISPLAY, BIG10_DISPLAY,
    YEAR, SEASON_START, SEASON_END,
)
from data_fetcher import fetch_all_data
from metrics import (
    build_team_stats, build_cross_game_results,
    build_conference_stats, h2h_leader,
)
from ai_summary import generate_summary
from email_builder import build_email, send_gmail


LOG_FILE = "secevaluator.log"


def log(msg: str) -> None:
    line = f"{datetime.now().isoformat()} - {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def in_season() -> bool:
    today = date.today()
    return SEASON_START <= today <= SEASON_END


def main() -> None:
    force = "--force" in sys.argv
    test_mode = "--test" in sys.argv or bool(TEST_TO_EMAILS)

    if not force and not in_season():
        log(f"Off-season ({date.today()} outside {SEASON_START}–{SEASON_END}). Use --force to override.")
        return

    log(f"SECevaluator starting — YEAR={YEAR}, week fetch in progress...")

    try:
        data = fetch_all_data(YEAR)
    except Exception as e:
        log(f"ERROR fetching data: {e}")
        sys.exit(1)

    week = data["week"]
    log(f"Data fetched. Week {week}. SEC teams: {len(data['sec_records'])}, Big Ten teams: {len(data['big10_records'])}, Cross-conf games: {len(data['cross_games'])}")

    sec_teams = build_team_stats(
        data["sec_records"], data["sp_ratings"], data["sos_ratings"], data["rankings"], SEC_DISPLAY
    )
    big10_teams = build_team_stats(
        data["big10_records"], data["sp_ratings"], data["sos_ratings"], data["rankings"], BIG10_DISPLAY
    )
    cross_game_results = build_cross_game_results(data["cross_games"])

    sec_stats = build_conference_stats(SEC_CONF_RESPONSE, SEC_DISPLAY, sec_teams, cross_game_results, SEC_CONF_RESPONSE)
    big10_stats = build_conference_stats(BIG10_CONF_RESPONSE, BIG10_DISPLAY, big10_teams, cross_game_results, SEC_CONF_RESPONSE)

    leader_str = h2h_leader(sec_stats, big10_stats)
    log(f"H2H: {leader_str}")

    log("Requesting AI summary from Mac Studio...")
    ai_text = generate_summary(sec_stats, big10_stats, cross_game_results, leader_str, week)
    if ai_text:
        log("AI summary received.")
    else:
        log("AI summary unavailable (Mac Studio offline or timeout).")

    subject, text_body, html_body = build_email(
        sec_stats, big10_stats, cross_game_results, ai_text, leader_str, week, SEC_CONF_RESPONSE
    )

    recipients = TEST_TO_EMAILS if test_mode else RECIPIENTS
    sender = SENDER_EMAIL
    if not sender:
        log("ERROR: SENDER_EMAIL env var not set.")
        sys.exit(1)

    log(f"Sending email to: {', '.join(recipients)}")
    try:
        send_gmail(sender, recipients, subject, text_body, html_body)
        log("Email sent successfully.")
    except Exception as e:
        log(f"ERROR sending email: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
