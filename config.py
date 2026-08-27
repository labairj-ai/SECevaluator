import os
from datetime import date

RECIPIENTS = [
    "robertjsherman1@gmail.com",
    "coreyolangreen@gmail.com",
    "jtdowning@gmail.com",
]

# CFBD API uses abbreviations as filter params; response data uses full names
SEC_CONF_PARAM = "SEC"
BIG10_CONF_PARAM = "B1G"
SEC_CONF_RESPONSE = "SEC"
BIG10_CONF_RESPONSE = "Big Ten"
SEC_DISPLAY = "SEC"
BIG10_DISPLAY = "Big Ten"

YEAR = 2026
# Season window: first game weekend through CFP championship (~mid-Jan)
SEASON_START = date(2026, 8, 28)
SEASON_END = date(2027, 1, 21)

MAC_STUDIO_URL = "http://100.73.128.40:8080/v1/chat/completions"
LLM_MODEL = "mlx-community/Qwen3.6-35B-A3B-4bit"
LLM_TIMEOUT = 300

CFBD_API_KEY = os.environ.get("CFBD_API_KEY", "").strip()
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "").strip()
TEST_TO_EMAILS = [e.strip() for e in os.environ.get("TEST_TO_EMAILS", "").split(",") if e.strip()]
