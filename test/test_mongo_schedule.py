"""Regression checks for Mongo's completed-day extraction schedule."""

import sys
import unittest
from pathlib import Path

import pendulum
from airflow.timetables.base import DataInterval, TimeRestriction

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dags"))
from mongo_template_dag import mongo_template_dag


class MongoScheduleTests(unittest.TestCase):
    def test_manual_saturday_run_extracts_friday(self):
        interval = mongo_template_dag.timetable.infer_manual_data_interval(
            run_after=pendulum.datetime(2026, 11, 14, 19, 8, tz="UTC")
        )
        self.assertEqual(interval.start, pendulum.datetime(2026, 11, 13, tz="UTC"))
        self.assertEqual(interval.end, pendulum.datetime(2026, 11, 14, tz="UTC"))

    def test_midnight_schedule_extracts_the_completed_day(self):
        info = mongo_template_dag.timetable.next_dagrun_info(
            last_automated_data_interval=DataInterval(
                start=pendulum.datetime(2026, 11, 12, tz="UTC"),
                end=pendulum.datetime(2026, 11, 13, tz="UTC"),
            ),
            restriction=TimeRestriction(
                earliest=pendulum.datetime(2026, 11, 12, tz="UTC"),
                latest=None,
                catchup=True,
            ),
        )
        self.assertEqual(info.data_interval.start, pendulum.datetime(2026, 11, 13, tz="UTC"))
        self.assertEqual(info.run_after, pendulum.datetime(2026, 11, 14, tz="UTC"))


if __name__ == "__main__":
    unittest.main()
