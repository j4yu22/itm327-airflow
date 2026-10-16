"""Offline tests for Milestone 2's CSV transformation and staging contract.

Run inside the Airflow worker; fixtures stay in a temporary directory and no
SFTP, Snowflake, or Airflow task is invoked.
"""

import csv
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
from pandas.api.types import is_integer_dtype


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dags"))
from sftp_template_dag import transform_news_files


SOURCE_COLUMNS = [
    "category", "datetime", "headline", "id", "image", "related",
    "source", "summary", "url",
]
OUTPUT_COLUMNS = [
    "CATEGORY", "DATETIME", "HEADLINE", "ID", "IMAGE", "RELATED",
    "SOURCE", "SUMMARY", "URL", "PUBLISHED_AT", "SOURCE_DATE",
    "SOURCE_FILE", "LOADED_AT",
]
SOURCE_DATE = "2026-09-14"
PUBLISHED_TIME = datetime(2026, 9, 14, 3, 4, 5, tzinfo=timezone.utc)


class TransformNewsFilesTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)

    def news_row(self, **changes):
        row = {
            "category": "company",
            "datetime": str(int(PUBLISHED_TIME.timestamp())),
            "headline": "A sample company headline",
            "id": "123456789",
            "image": "https://example.invalid/image.jpg",
            "related": "AAPL",
            "source": "Example News",
            "summary": "A sample article summary.",
            "url": "https://example.invalid/article",
        }
        row.update(changes)
        return row

    def write_csv(self, name, rows, fieldnames=None):
        path = self.directory / name
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames or SOURCE_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        return str(path)

    def test_schema_utc_timestamp_source_metadata_and_large_integer_id(self):
        article_id = 9007199254740993  # Cannot be represented exactly as float64.
        path = self.write_csv("AAPL_2026-09-14.csv", [self.news_row(id=str(article_id))])
        before = pd.Timestamp.now(tz="UTC").tz_localize(None)

        result = transform_news_files([path], SOURCE_DATE)

        after = pd.Timestamp.now(tz="UTC").tz_localize(None)
        self.assertEqual(list(result.columns), OUTPUT_COLUMNS)
        self.assertEqual(len(result), 1)
        self.assertTrue(is_integer_dtype(result["ID"]))
        self.assertTrue(is_integer_dtype(result["DATETIME"]))
        self.assertEqual(result.loc[0, "ID"], article_id)
        self.assertEqual(result.loc[0, "DATETIME"], int(PUBLISHED_TIME.timestamp()))
        self.assertEqual(result.loc[0, "PUBLISHED_AT"], pd.Timestamp("2026-09-14 03:04:05"))
        self.assertIsNone(result["PUBLISHED_AT"].dt.tz)
        self.assertEqual(result.loc[0, "SOURCE_DATE"], date(2026, 9, 14))
        self.assertEqual(result.loc[0, "SOURCE_FILE"], "AAPL_2026-09-14.csv")
        self.assertIsNone(result["LOADED_AT"].dt.tz)
        self.assertLessEqual(before, result.loc[0, "LOADED_AT"])
        self.assertLessEqual(result.loc[0, "LOADED_AT"], after)

    def test_strips_text_preserves_nulls_and_literal_na_strings(self):
        path = self.write_csv("news.csv", [self.news_row(
            category=" NULL ", headline="  Trimmed headline  ", image="",
            related=" NA ", summary="", source="  News desk ", id=" 42 ",
        )])

        result = transform_news_files([path], SOURCE_DATE)

        self.assertEqual(result.loc[0, "CATEGORY"], "NULL")
        self.assertEqual(result.loc[0, "HEADLINE"], "Trimmed headline")
        self.assertEqual(result.loc[0, "RELATED"], "NA")
        self.assertEqual(result.loc[0, "SOURCE"], "News desk")
        self.assertEqual(result.loc[0, "ID"], 42)
        self.assertTrue(pd.isna(result.loc[0, "IMAGE"]))
        self.assertTrue(pd.isna(result.loc[0, "SUMMARY"]))

    def test_duplicate_article_in_same_file_keeps_last_but_other_file_is_retained(self):
        first = self.write_csv("AAPL.csv", [
            self.news_row(id="42", headline="Earlier version"),
            self.news_row(id="42", headline="Corrected version"),
        ])
        second = self.write_csv("MSFT.csv", [self.news_row(id="42", related="MSFT")])

        result = transform_news_files([first, second], SOURCE_DATE)

        self.assertEqual(len(result), 2)
        self.assertEqual(set(result["SOURCE_FILE"]), {"AAPL.csv", "MSFT.csv"})
        self.assertEqual(
            result.loc[result["SOURCE_FILE"] == "AAPL.csv", "HEADLINE"].iloc[0],
            "Corrected version",
        )
        self.assertFalse(result.duplicated(["SOURCE_DATE", "SOURCE_FILE", "ID"]).any())

    def test_empty_and_header_only_files_do_not_discard_valid_rows(self):
        empty = self.directory / "empty.csv"
        empty.write_text("", encoding="utf-8")
        header_only = self.write_csv("header_only.csv", [])
        valid = self.write_csv("valid.csv", [self.news_row()])

        result = transform_news_files([str(empty), header_only, valid], SOURCE_DATE)

        self.assertEqual(len(result), 1)
        self.assertEqual(result.loc[0, "SOURCE_FILE"], "valid.csv")

    def test_no_files_or_only_empty_files_fail_instead_of_marking_date_processed(self):
        empty = self.directory / "empty.csv"
        empty.write_text("", encoding="utf-8")
        header_only = self.write_csv("header_only.csv", [])
        for paths in ([], [str(empty)], [header_only], [str(empty), header_only]):
            with self.subTest(paths=paths):
                with self.assertRaisesRegex(ValueError, "No news rows found"):
                    transform_news_files(paths, SOURCE_DATE)

    def test_missing_required_column_fails_with_filename_and_column(self):
        row = self.news_row()
        del row["url"]
        path = self.write_csv("missing_url.csv", [row], SOURCE_COLUMNS[:-1])

        with self.assertRaisesRegex(ValueError, r"missing_url\.csv: missing columns.*URL"):
            transform_news_files([path], SOURCE_DATE)

    def test_null_numeric_keys_fail_instead_of_loading_ambiguous_records(self):
        for field in ("id", "datetime"):
            with self.subTest(field=field):
                path = self.write_csv(f"null_{field}.csv", [self.news_row(**{field: ""})])
                with self.assertRaisesRegex(ValueError, f"null_{field}\\.csv: {field.upper()}"):
                    transform_news_files([path], SOURCE_DATE)

    def test_non_numeric_or_fractional_ids_and_timestamps_are_rejected(self):
        for field in ("id", "datetime"):
            for invalid in ("not-a-number", "123.5"):
                with self.subTest(field=field, value=invalid):
                    path = self.write_csv("invalid_numeric.csv", [self.news_row(**{field: invalid})])
                    with self.assertRaises((ValueError, TypeError)):
                        transform_news_files([path], SOURCE_DATE)

    def test_integer_overflow_is_rejected_instead_of_wrapping_negative(self):
        for field in ("id", "datetime"):
            with self.subTest(field=field):
                path = self.write_csv("overflow.csv", [self.news_row(
                    **{field: "9223372036854775808"}
                )])
                with self.assertRaises((ValueError, TypeError, OverflowError)):
                    transform_news_files([path], SOURCE_DATE)

    def test_invalid_source_date_is_rejected(self):
        path = self.write_csv("news.csv", [self.news_row()])
        for invalid in ("not-a-date", "2026-02-30", "../2026-09-14"):
            with self.subTest(source_date=invalid):
                with self.assertRaises(ValueError):
                    transform_news_files([path], invalid)

    def test_parquet_round_trip_preserves_load_types_and_nulls(self):
        article_id = 9007199254740993
        path = self.write_csv("news.csv", [self.news_row(id=str(article_id), image="")])
        result = transform_news_files([path], SOURCE_DATE)
        staged = self.directory / "transformed.parquet"

        result.to_parquet(staged, index=False)
        restored = pd.read_parquet(staged)

        self.assertEqual(list(restored.columns), OUTPUT_COLUMNS)
        self.assertEqual(restored.loc[0, "ID"], article_id)
        self.assertEqual(restored.loc[0, "SOURCE_DATE"], date(2026, 9, 14))
        self.assertEqual(restored.loc[0, "PUBLISHED_AT"], pd.Timestamp("2026-09-14 03:04:05"))
        self.assertIsNone(restored["PUBLISHED_AT"].dt.tz)
        self.assertTrue(pd.isna(restored.loc[0, "IMAGE"]))


if __name__ == "__main__":
    unittest.main()
