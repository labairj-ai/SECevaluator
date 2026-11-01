# SECevaluator

Weekly college football conference rivalry digest comparing the SEC and Big Ten. Every Sunday at 7am ET during the season, it fetches current standings, computes head-to-head records, ranks the best wins by opponent quality, and generates a validated, facts-based narrative — then emails it to a distribution list.

## What It Sends

Each email includes:

- **Game of the Week** — highest combined-SP+ upcoming SEC vs Big Ten matchup by combined SP+ rating
- **Data Summary** — 2 paragraphs generated from reconciled results, ratings and identified poll evidence
- **Conference Comparison** — head-to-head record, overall, external (non-conference), avg SP+, avg OOC SOS, selected-poll ranked teams; with arrows against the prior comparable saved report
- **Cross-Conference Results** — every SEC vs Big Ten game played, with score and margin
- **Best Wins** — top 5 wins per conference ranked by opponent SP+ rating
- **Standings** — all SEC and Big Ten teams with overall / conference / external records, SP+, OOC SOS, selected-poll rank

## Data Sources

| Source | What it provides |
|---|---|
| [College Football Data API](https://collegefootballdata.com) | Season calendar, records, games, SP+ ratings and named FBS polls |
| Gmail API (OAuth2) | Email delivery |

## Metric Glossary

- **SP+** — ESPN's predictive team quality rating, adjusted for opponent strength. 0 = average FBS team; +10 means roughly 10 points per game better than average.
- **OOC SOS** — Out-of-Conference Strength of Schedule. Average SP+ of non-conference opponents faced. Higher = harder external slate.
- **External Record** — wins/losses against non-conference opponents only; same-conference games excluded.
- **Poll Rank** — rank in the actual named poll and week (CFP preferred when available, then AP, then Coaches). Rankings do not by themselves establish playoff qualification.

## Season Window

Runs weekly (Sundays 7am ET) from the first game weekend through the CFP National Championship. Controlled by `SEASON_START` and `SEASON_END` in `config.py`.

## Setup

### Requirements

- Python 3.10+
- A free API key from [collegefootballdata.com](https://collegefootballdata.com/key)
- Gmail OAuth2 credentials (same app as dansbytracker — copy `credentials.json` and `token.json`)

### Local dev

```bash
git clone https://github.com/labairj-ai/SECevaluator.git
cd SECevaluator
python3 -m venv venv
venv/bin/pip install -r requirements.txt
cp ~/dansbytracker/credentials.json .
cp ~/dansbytracker/token.json .
```

Create `.env` (never committed):
```
SENDER_EMAIL=labairj@gmail.com
CFBD_API_KEY=your_key_here
```

### Run a test email

```bash
# Send to yourself using a historical season week
set -a; source .env; set +a
TEST_TO_EMAILS=you@gmail.com venv/bin/python3 secevaluator.py --year 2025 --week 10 --test --force

# Current season test (bypasses off-season check)
TEST_TO_EMAILS=you@gmail.com venv/bin/python3 secevaluator.py --test --force
```

### CLI flags

| Flag | Description |
|---|---|
| `--year YYYY` | Pull data for a historical season (default: current year) |
| `--week N` | Override poll/report week; current default comes from the CFBD season calendar |
| `--test` | Send only to a required nonempty `TEST_TO_EMAILS` list; no snapshots |
| `--dry-run` | Fetch, validate and render without Gmail or snapshot/database writes |
| `--season-type regular/postseason` | Season type for an explicit `--week`; regular by default |
| `--force` | Bypass the off-season window check |

## Deployment (Optiplex)

```bash
ssh optiplex
cd /home/optiplex
git clone https://github.com/labairj-ai/SECevaluator.git
cd SECevaluator
python3 -m venv venv && venv/bin/pip install -r requirements.txt

# Copy Gmail credentials from dansbytracker
cp /home/optiplex/dansbytracker/credentials.json .
cp /home/optiplex/dansbytracker/token.json .

# Create environment file
cat > .env <<EOF
SENDER_EMAIL=labairj@gmail.com
CFBD_API_KEY=your_key_here
EOF

# Install systemd units
sudo cp systemd/secevaluator.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now secevaluator.timer

# Verify
systemctl list-timers secevaluator.timer
```

### Logs

```bash
tail -f /home/optiplex/SECevaluator/secevaluator.log
```

## Project Structure

```
secevaluator.py     — main orchestration, CLI args
config.py           — constants, env vars, season dates
data_fetcher.py     — College Football Data API calls
metrics.py          — TeamStats / ConferenceStats dataclasses, top wins, game of week
ai_summary.py       — validated deterministic narrative from report evidence
email_builder.py    — HTML + plain text email builder, Gmail send
db.py               — atomic, season-aware paired report snapshots
systemd/            — secevaluator.service + secevaluator.timer
```

## Updating for a New Season

1. Update `YEAR`, `SEASON_START`, `SEASON_END` in `config.py`
2. Push to GitHub and pull on optiplex
3. The timer picks up automatically on the new season's first Sunday

### Report data consistency

Game API failures abort the digest rather than being presented as zero games.
The head-to-head table is derived from the same season games used elsewhere in
the report and must agree across the SEC and Big Ten queries. Incomplete or
conflicting responses abort before email delivery. Summaries are generated from
report facts, distinguish the head-to-head leader from the ratings leader, and
use the requested season year. They no longer depend on unvalidated LLM prose.

Run the offline regression suite without sending mail:

```sh
python -m unittest discover -s tests -v
```

Accuracy safeguards also reconcile each team's overall and conference record
against completed season games. Live scores are excluded from final results,
top wins and upcoming-matchup selection. Invalid or inconsistent records abort
before delivery. Ratings must cover every conference team for a conference-wide
SP+ average; missing opponent ratings make the OOC comparison unavailable.
OOC SOS is an unweighted mean of team-level averages, not a national SOS rank.
Poll name and actual fallback week accompany ranking counts. Unavailable polls
are distinct from zero ranked teams, and AP/Coaches results are not labeled CFP.
Latest available season opponent ratings are not described as game-time or final
season ratings. Both email formats use the same validated facts and explicitly
handle zero ratings and missing comparisons.

These checks establish internal consistency against CFBD evidence; they cannot
guarantee that the upstream provider itself has no errors. Reports describe
season-to-date data, not a historical week cutoff when replaying an old week.

### Full review safeguards

- All required API failures abort rather than silently producing empty data;
  empty successful rankings/ratings responses remain explicitly unavailable.
- Validate game, record, poll and rating season/conference identities. The
  provider calendar determines the current week, including its uneven week 1.
  Postseason rankings can fall back to the last available regular-season poll.
- Reject past unplayed games as upcoming features and require both SP+ ratings
  to rank upcoming matchups. Tied comparisons receive no winner/loser colors.
- The email delivery boundary recomputes the headline and summary from the
  validated games; caller-supplied stale commentary cannot override the facts.
- New `report_snapshots` rows are saved for both conferences in one transaction.
  The legacy `weekly_snapshots` table is preserved without alteration and is not
  used for comparisons against the stricter v2 metric definitions. Regular and
  postseason week numbers are separate keys. Missing ranked counts are NULL.
- `--dry-run` can write diagnostic logs but never sends mail, initializes the
  database or saves snapshots. Test sends require explicit test recipients.
- The timer source uses an explicit IANA zone inside `OnCalendar`; `TimeZone`
  is not a valid timer directive ([systemd calendar syntax](https://www.freedesktop.org/software/systemd/man/latest/systemd.time.html)).
  Updating Git does not install or restart the timer.

Read-only report preview (requires the CFBD key but no Gmail authentication):

```sh
set -a; source .env; set +a
venv/bin/python3 secevaluator.py --dry-run
```

Historical `--week` selects the report/poll context; records and ratings remain
season-to-date as supplied by CFBD, not a reconstructed historical cutoff.
Gmail delivery and SQLite cannot form a single atomic transaction: an ambiguous
network failure or a snapshot failure after delivery needs operator review
before retrying, to avoid duplicate email. No automatic mail retry is added.
