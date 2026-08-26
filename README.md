# SECevaluator

Weekly college football conference rivalry digest comparing the SEC and Big Ten. Every Sunday at 7am ET during the season, it fetches current standings, computes head-to-head records, ranks the best wins by opponent quality, and generates an AI-written narrative — then emails it to a distribution list.

## What It Sends

Each email includes:

- **Game of the Week** — highest-stakes upcoming SEC vs Big Ten matchup by combined SP+ rating
- **AI Analysis** — 2-paragraph narrative from a 70B LLM, framed around who's winning the conference war
- **Conference Comparison** — head-to-head record, overall, external (non-conference), avg SP+, avg OOC SOS, CFP ranked teams; with week-over-week delta arrows
- **Cross-Conference Results** — every SEC vs Big Ten game played, with score and margin
- **Best Wins** — top 5 wins per conference ranked by opponent SP+ rating
- **Standings** — all SEC and Big Ten teams with overall / conference / external records, SP+, OOC SOS, CFP rank

## Data Sources

| Source | What it provides |
|---|---|
| [College Football Data API](https://collegefootballdata.com) | Records, games, SP+ ratings, CFP rankings |
| Mac Studio MLX (local) | AI narrative via `mlx-community/Llama-3.3-70B-Instruct-4bit` |
| Gmail API (OAuth2) | Email delivery |

## Metric Glossary

- **SP+** — ESPN's predictive team quality rating, adjusted for opponent strength. 0 = average FBS team; +10 means roughly 10 points per game better than average.
- **OOC SOS** — Out-of-Conference Strength of Schedule. Average SP+ of non-conference opponents faced. Higher = harder external slate.
- **External Record** — wins/losses against non-conference opponents only; same-conference games excluded.
- **CFP Rank** — College Football Playoff committee ranking. Top 12 earn automatic playoff bids.

## Season Window

Runs weekly (Sundays 7am ET) from the first game weekend through the CFP National Championship. Controlled by `SEASON_START` and `SEASON_END` in `config.py`.

## Setup

### Requirements

- Python 3.9+
- A free API key from [collegefootballdata.com](https://collegefootballdata.com/key)
- Gmail OAuth2 credentials (same app as dansbytracker — copy `credentials.json` and `token.json`)
- Mac Studio running MLX at `http://100.73.128.40:8080` (or update `MAC_STUDIO_URL` in `config.py`)

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
source .env
TEST_TO_EMAILS=you@gmail.com venv/bin/python3 secevaluator.py --year 2025 --week 10 --test --force

# Current season test (bypasses off-season check)
TEST_TO_EMAILS=you@gmail.com venv/bin/python3 secevaluator.py --test --force
```

### CLI flags

| Flag | Description |
|---|---|
| `--year YYYY` | Pull data for a historical season (default: current year) |
| `--week N` | Override week number (default: computed from season start date) |
| `--test` | Send to `TEST_TO_EMAILS` instead of the full recipient list |
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
ai_summary.py       — Mac Studio LLM prompt + HTTP call
email_builder.py    — HTML + plain text email builder, Gmail send
db.py               — SQLite weekly snapshots for week-over-week deltas
systemd/            — secevaluator.service + secevaluator.timer
```

## Updating for a New Season

1. Update `YEAR`, `SEASON_START`, `SEASON_END` in `config.py`
2. Push to GitHub and pull on optiplex
3. The timer picks up automatically on the new season's first Sunday
