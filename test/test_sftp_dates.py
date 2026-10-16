"""Offline tests for backfill and manual-run source dates."""

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dags"))
from sftp_template_dag import get_source_date


class SourceDateTests(unittest.TestCase):
    def test_backfill_interval_takes_precedence_over_manual_trigger_time(self):
        interval_start = datetime(2026, 9, 14, 6, tzinfo=timezone.utc)
        run_after = datetime(2026, 10, 16, 3, 59, tzinfo=timezone.utc)

        self.assertEqual(get_source_date(interval_start, run_after), "2026-09-14")

    def test_manual_run_uses_denver_day_before_trigger(self):
        # October 16 at 03:59 UTC is still October 15 in Denver.
        run_after = datetime(2026, 10, 16, 3, 59, tzinfo=timezone.utc)

        self.assertEqual(get_source_date(None, run_after), "2026-10-14")

    def test_manual_run_just_after_denver_midnight_advances_source_date(self):
        # October 16 at 06:01 UTC is October 16 at 00:01 in Denver.
        run_after = datetime(2026, 10, 16, 6, 1, tzinfo=timezone.utc)

        self.assertEqual(get_source_date(None, run_after), "2026-10-15")

    def test_missing_interval_and_trigger_time_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "data interval or manual trigger time"):
            get_source_date(None)


if __name__ == "__main__":
    unittest.main()
