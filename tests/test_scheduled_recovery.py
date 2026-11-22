import io
import subprocess
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

import requests

import scheduled_run as runner
import secevaluator as app


class ScheduledRecoveryTests(unittest.TestCase):
    def run_with_outcomes(self, outcomes):
        with patch.object(runner.subprocess, "run", side_effect=outcomes) as run, \
             patch.object(runner.time, "sleep") as sleep, redirect_stdout(io.StringIO()):
            result = runner.run_digest()
        return result, run.call_count, [call.args[0] for call in sleep.call_args_list]

    def test_recovers_after_two_fetch_failures(self):
        failure = Mock(stdout="CFBD error", returncode=75)
        success = Mock(stdout="sent", returncode=0)
        result, count, delays = self.run_with_outcomes([failure, failure, success])
        self.assertEqual(result, ("CFBD error\nCFBD error\nsent", 0))
        self.assertEqual(count, 3)
        self.assertEqual(delays, [300, 600])

    def test_fetch_failures_stop_after_three_attempts(self):
        failure = Mock(stdout="CFBD error", returncode=75)
        result, count, delays = self.run_with_outcomes([failure] * 3)
        self.assertEqual(result[1], 75)
        self.assertEqual((count, delays), (3, [300, 600]))

    def test_no_retry_after_possible_delivery(self):
        for failure in (Mock(stdout="Sending to 3 recipient(s).", returncode=1),
                        subprocess.TimeoutExpired("digest", 10, output=b"Sending")):
            with self.subTest(failure=failure):
                result, count, delays = self.run_with_outcomes([failure])
                self.assertEqual(result[1], 1)
                self.assertEqual((count, delays), (1, []))

    def test_retry_wait_must_fit_total_budget(self):
        failure = Mock(stdout="CFBD error", returncode=75)
        with patch.object(runner.time, "monotonic", side_effect=[0, 0, 1600]):
            result, count, delays = self.run_with_outcomes([failure])
        self.assertEqual((result[1], count, delays), (75, 1, []))

    def test_only_transient_fetch_errors_signal_safe_retry(self):
        gateway = requests.Response()
        gateway.status_code = 502
        unauthorized = requests.Response()
        unauthorized.status_code = 401
        cases = ((requests.Timeout(), 75),
                 (requests.HTTPError(response=gateway), 75),
                 (requests.HTTPError(response=unauthorized), 1),
                 (requests.exceptions.SSLError(), 1),
                 (ValueError("bad data"), 1))
        for error, code in cases:
            with self.subTest(error=error), \
                 patch("sys.argv", ["secevaluator", "--week", "12"]), \
                 patch.object(app, "in_season", return_value=True), \
                 patch.object(app, "init_db"), patch.object(app, "log"), \
                 patch.object(app, "fetch_all_data", side_effect=error), \
                 patch.object(app, "send_gmail") as send, \
                 self.assertRaises(SystemExit) as result:
                app.main()
            self.assertEqual(result.exception.code, code)
            send.assert_not_called()
