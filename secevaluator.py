#!/usr/bin/env python3
import argparse
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
import data_fetcher
from data_fetcher import fetch_all_data
from metrics import (
    build_team_stats, build_cross_game_results,
    build_conference_stats, h2h_leader,
)
from ai_summary import generate_summary
from email_builder import build_email, send_gmail
from db import init_db, save_snapshot, load_prior_snapshot


LOG_FILE = "secevaluator.log"


def log(msg: str) -> None:
    line = f"{datetime.now().isoformat()} - {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def in_season(year: int) -> bool:
    if year != YEAR:
        return True  # historical runs always allowed
    today = date.today()
    return SEASON_START <= today <= SEASON_END


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year",  type=int, default=YEAR,  help="Season year (default: current)")
    parser.add_argument("--week",  type=int, default=None,  help="Override week number")
    parser.add_argument("--force", action="store_true",     help="Run even if off-season")
    parser.add_argument("--test",  action="store_true",     help="Send to TEST_TO_EMAILS only, don't save snapshot")
    args = parser.parse_args()

    year = args.year
    test_mode = args.test or bool(TEST_TO_EMAILS)

    if not args.force and not in_season(year):
        log(f"Off-season ({date.today()} outside {SEASON_START}–{SEASON_END}). Use --force to override.")
        return

    init_db()
    log(f"SECevaluator starting — YEAR={year}, fetching data...")

    week = args.week if args.week else data_fetcher.get_current_week()

    try:
        data = fetch_all_data(year, week)
    except Exception as e:
        log(f"ERROR fetching data: {e}")
        sys.exit(1)

    log(f"Data fetched. Week {week}. SEC={len(data['sec_records'])}, Big Ten={len(data['big10_records'])}, cross-conf games={len(data['cross_games'])}")

    sec_teams   = build_team_stats(data["sec_records"],   data["sec_all_games"],   data["sp_ratings"], data["rankings"], SEC_DISPLAY)
    big10_teams = build_team_stats(data["big10_records"], data["big10_all_games"], data["sp_ratings"], data["rankings"], BIG10_DISPLAY)
    cross_results = build_cross_game_results(data["cross_games"])

    sec_stats   = build_conference_stats(SEC_CONF_RESPONSE,   SEC_DISPLAY,   sec_teams,   cross_results, SEC_CONF_RESPONSE)
    big10_stats = build_conference_stats(BIG10_CONF_RESPONSE, BIG10_DISPLAY, big10_teams, cross_results, SEC_CONF_RESPONSE)

    # Load prior week snapshots for week-over-week deltas
    prior_sec   = load_prior_snapshot(year, week, SEC_CONF_RESPONSE)
    prior_big10 = load_prior_snapshot(year, week, BIG10_CONF_RESPONSE)
    if prior_sec and sec_stats.avg_sp_rating is not None:
        sec_stats.d_avg_sp  = (sec_stats.avg_sp_rating  or 0) - (prior_sec["avg_sp_rating"]  or 0) if prior_sec["avg_sp_rating"]  else None
        sec_stats.d_avg_sos = (sec_stats.avg_sos         or 0) - (prior_sec["avg_sos"]         or 0) if prior_sec["avg_sos"]         else None
    if prior_big10 and big10_stats.avg_sp_rating is not None:
        big10_stats.d_avg_sp  = (big10_stats.avg_sp_rating  or 0) - (prior_big10["avg_sp_rating"]  or 0) if prior_big10["avg_sp_rating"]  else None
        big10_stats.d_avg_sos = (big10_stats.avg_sos          or 0) - (prior_big10["avg_sos"]          or 0) if prior_big10["avg_sos"]          else None

    leader_str = h2h_leader(sec_stats, big10_stats)
    log(f"H2H: {leader_str}")

    log("Requesting AI summary from Mac Studio...")
    ai_text = generate_summary(sec_stats, big10_stats, cross_results, leader_str, week)
    log("AI summary received." if ai_text else "AI summary unavailable.")

    subject, text_body, html_body = build_email(
        sec_stats, big10_stats, cross_results, ai_text, leader_str, week, SEC_CONF_RESPONSE, year
    )

    recipients = TEST_TO_EMAILS if test_mode else RECIPIENTS
    sender = SENDER_EMAIL
    if not sender:
        log("ERROR: SENDER_EMAIL not set.")
        sys.exit(1)

    log(f"Sending to: {', '.join(recipients)}")
    try:
        send_gmail(sender, recipients, subject, text_body, html_body)
        log("Email sent successfully.")
    except Exception as e:
        log(f"ERROR sending email: {e}")
        sys.exit(1)

    # Save snapshot after successful send (skip for test mode so it doesn't pollute history)
    if not test_mode:
        save_snapshot(year, week, SEC_CONF_RESPONSE,   sec_stats)
        save_snapshot(year, week, BIG10_CONF_RESPONSE, big10_stats)
        log("Weekly snapshot saved.")


if __name__ == "__main__":
    main()
