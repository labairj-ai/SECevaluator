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
    compute_top_wins, compute_game_of_week,
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

    poll = data["rankings"]
    poll_label = f"{poll.poll}, week {poll.week}" if poll.poll else None
    sec_stats.poll_label = big10_stats.poll_label = poll_label

    # Load prior week snapshots for week-over-week deltas
    prior_sec   = load_prior_snapshot(year, week, SEC_CONF_RESPONSE)
    prior_big10 = load_prior_snapshot(year, week, BIG10_CONF_RESPONSE)
    for stats, prior in ((sec_stats, prior_sec), (big10_stats, prior_big10)):
        if prior:
            for field in ("avg_sp_rating", "avg_sos"):
                current, previous = getattr(stats, field), prior[field]
                delta = current - previous if current is not None and previous is not None else None
                setattr(stats, "d_avg_sp" if field == "avg_sp_rating" else "d_avg_sos", delta)

    leader_str = h2h_leader(sec_stats, big10_stats)
    log(f"H2H: {leader_str}")

    sec_team_names   = {t.team for t in sec_teams}
    big10_team_names = {t.team for t in big10_teams}
    sec_top_wins   = compute_top_wins(data["sec_all_games"],   sec_team_names,   data["sp_ratings"], SEC_DISPLAY)
    big10_top_wins = compute_top_wins(data["big10_all_games"], big10_team_names, data["sp_ratings"], BIG10_DISPLAY)
    game_of_week   = compute_game_of_week(cross_results, data["sp_ratings"])
    if game_of_week:
        log(f"Game of the Week: {game_of_week.away_team} at {game_of_week.home_team} (Wk {game_of_week.week})")

    log("Building validated data summary...")
    ai_text = generate_summary(sec_stats, big10_stats, cross_results, leader_str, week, year=args.year)
    if not ai_text:
        log("ERROR: AI summary unavailable. Aborting — email not sent.")
        sys.exit(1)
    log("Data summary validated.")

    subject, text_body, html_body = build_email(
        sec_stats, big10_stats, cross_results, ai_text, leader_str, week, SEC_CONF_RESPONSE, year,
        sec_top_wins, big10_top_wins, game_of_week,
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
