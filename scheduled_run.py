"""Recover from transient pre-send fetch failures and report terminal failures."""
import html
import os
import subprocess
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from config import SENDER_EMAIL
from data_fetcher import TEMPORARY_FETCH_FAILURE
from email_builder import send_gmail


RETRY_DELAYS = (0, 300, 600)
RUN_BUDGET_SECONDS = 1800


def run_digest():
    """Only the explicit transient data-fetch exit authorizes another attempt."""
    deadline = time.monotonic() + RUN_BUDGET_SECONDS
    attempt_logs = []
    for attempt, delay in enumerate(RETRY_DELAYS, start=1):
        if delay:
            if time.monotonic() + delay >= deadline:
                break
            print(f"Transient CFBD fetch failure before email. Retrying in {delay}s.", flush=True)
            time.sleep(delay)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            result = subprocess.run(
                [sys.executable, "-u", "secevaluator.py"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                timeout=remaining,
            )
            output, status = result.stdout, result.returncode
        except subprocess.TimeoutExpired as exc:
            output = exc.stdout or ""
            if isinstance(output, bytes):
                output = output.decode("utf-8", errors="replace")
            output += "\nDigest exceeded the 30 minute time limit."
            status = 1
        except OSError as exc:
            output, status = f"Unable to start digest: {type(exc).__name__}", 1

        print(f"Digest attempt {attempt}/{len(RETRY_DELAYS)} (exit {status}):\n{output}", flush=True)
        attempt_logs.append(output)
        if status != TEMPORARY_FETCH_FAILURE:
            return "\n".join(attempt_logs), status
    return "\n".join(attempt_logs), TEMPORARY_FETCH_FAILURE


def main():
    output, status = run_digest()
    if not status:
        return 0
    # Remove configured credentials before including diagnostics in an email.
    for key, value in os.environ.items():
        if value and any(word in key.upper() for word in ("KEY", "TOKEN", "SECRET", "PASSWORD")):
            output = output.replace(value, "[REDACTED]")
    recipients = [address.strip() for address in os.environ.get(
        "ERROR_TO_EMAILS", "robertjsherman1@gmail.com"
    ).split(",") if address.strip()]
    stamp = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M %Z")
    delivery = (
        "Data collection failed before email delivery."
        if status == TEMPORARY_FETCH_FAILURE else
        "Check the logs before rerunning. Delivery may be uncertain if Gmail was reached."
    )
    body = (
        f"SECevaluator failed at {stamp} (exit status {status}).\n\n"
        f"{delivery} Automatic retries are limited to transient pre-send data fetch failures.\n\n"
        "Recent output:\n" + output[-12000:]
    )
    try:
        send_gmail(SENDER_EMAIL, recipients, "SECevaluator error alert", body,
                   "<pre>" + html.escape(body) + "</pre>")
        print("Error alert sent successfully.", flush=True)
    except Exception as exc:
        print(f"ERROR: error alert could not be sent ({type(exc).__name__}); check Gmail credentials/connectivity.", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
