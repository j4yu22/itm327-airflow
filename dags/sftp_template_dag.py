"""Milestone 2: load daily SFTP news into PROJECT_DB.RAW.UNDERWOOD_JAY_M2.

Each run processes its data interval's date, including Airflow backfills.
CSV downloads and a transformed Parquet file are staged by date. Snowflake
MERGE makes retries safe; a date is recorded only after the load succeeds.
"""

from __future__ import annotations

import logging
import os
import posixpath
import shutil
import stat
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pendulum
from paramiko import SFTPClient
from airflow.sdk import dag, task
from airflow.timetables.interval import CronDataIntervalTimetable

from utils import create_sftp_connection, get_snowflake_connection

log = logging.getLogger(__name__)
STAGING_AREA = Path(__file__).resolve().parents[1] / "staging" / "sftp"
PROCESSED_LOG_FILE = STAGING_AREA / "processed_dates.txt"
SNOWFLAKE_TABLE = "UNDERWOOD_JAY_M2"
TIMEZONE = "America/Denver"
NEWS_COLUMNS = [
    "CATEGORY", "DATETIME", "HEADLINE", "ID", "IMAGE", "RELATED",
    "SOURCE", "SUMMARY", "URL",
]
MERGE_KEYS = ["SOURCE_DATE", "SOURCE_FILE", "ID"]


def get_source_date(data_interval_start, run_after=None) -> str:
    """Use the interval date, or yesterday at the time of a manual trigger."""
    if data_interval_start is not None:
        return pendulum.instance(data_interval_start).in_timezone(TIMEZONE).date().isoformat()
    if run_after is None:
        raise ValueError("A data interval or manual trigger time is required")
    return pendulum.instance(run_after).in_timezone(TIMEZONE).subtract(days=1).date().isoformat()


def transform_news_files(local_files: list[str], date_str: str) -> pd.DataFrame:
    """Keep source fields, normalize types, and add traceable source metadata."""
    source_date = date.fromisoformat(date_str)
    frames = []
    for file_path in local_files:
        try:
            # Read as text first so IDs are not rounded and blank fields stay null.
            frame = pd.read_csv(file_path, dtype="string", keep_default_na=False,
                                na_values=[""])
        except pd.errors.EmptyDataError:
            log.warning("Skipping empty file: %s", Path(file_path).name)
            continue
        frame.columns = frame.columns.str.strip().str.upper()
        missing = set(NEWS_COLUMNS) - set(frame.columns)
        if missing:
            raise ValueError(f"{Path(file_path).name}: missing columns {sorted(missing)}")
        if frame.empty:
            continue
        frame = frame[NEWS_COLUMNS].copy()
        for column in NEWS_COLUMNS:
            frame[column] = frame[column].str.strip()
        for column in ["ID", "DATETIME"]:
            if frame[column].isna().any():
                raise ValueError(f"{Path(file_path).name}: {column} cannot be null")
            if not frame[column].str.fullmatch(r"[+-]?\d+", na=False).all():
                raise ValueError(f"{Path(file_path).name}: {column} must contain whole integers")
            # Construct from Python integers so pandas cannot silently truncate
            # decimals or wrap an unsigned value when converting to Int64.
            frame[column] = pd.array([int(value) for value in frame[column]], dtype="Int64")
        # Snowflake TIMESTAMP_NTZ stores these timestamps in UTC.
        frame["PUBLISHED_AT"] = pd.to_datetime(
            frame["DATETIME"], unit="s", utc=True, errors="raise"
        ).dt.tz_localize(None)
        frame["SOURCE_DATE"] = source_date
        frame["SOURCE_FILE"] = Path(file_path).name
        frames.append(frame)
    if not frames:
        raise ValueError(f"No news rows found for {date_str}; date was not processed")
    result = pd.concat(frames, ignore_index=True)
    result = result.drop_duplicates(subset=MERGE_KEYS, keep="last").reset_index(drop=True)
    result["LOADED_AT"] = pd.Timestamp.now(tz="UTC").tz_localize(None)
    return result


@dag(
    dag_id="sftp_template_dag",
    start_date=pendulum.datetime(2026, 9, 14, tz=TIMEZONE),
    # Explicit interval timetable: midnight loads the previous local day's folder.
    schedule=CronDataIntervalTimetable("0 0 * * *", timezone=TIMEZONE),
    catchup=True,
    max_active_runs=2,
    max_active_tasks=4,
    tags=["milestone-2", "sftp", "news", "snowflake"],
    default_args={"owner": "airflow", "retries": 1,
                  "retry_delay": timedelta(minutes=2)},
)
def sftp_template_pipeline():
    @task
    def extract_from_sftp(data_interval_start=None, dag_run=None):
        # Airflow 3 manual runs can have no logical date or data interval.
        date_str = get_source_date(data_interval_start, dag_run.run_after if dag_run else None)
        STAGING_AREA.mkdir(parents=True, exist_ok=True)
        processed_dates = (
            PROCESSED_LOG_FILE.read_text().splitlines() if PROCESSED_LOG_FILE.exists() else []
        )
        if date_str in processed_dates:
            log.info("Date %s was already loaded successfully; skipping.", date_str)
            return [], date_str

        sftp_dir = os.environ.get("SFTP_DIR")
        if not sftp_dir:
            raise ValueError("SFTP_DIR must be configured in .env")
        remote_path = posixpath.join(sftp_dir, date_str)
        local_dir = STAGING_AREA / date_str
        local_dir.mkdir(parents=True, exist_ok=True)
        sftp = create_sftp_connection()
        transport = sftp.get_channel().get_transport()
        clients = [sftp]
        try:
            # Ignore .done markers and directories; a missing date must fail visibly.
            filenames = sorted(
                entry.filename for entry in sftp.listdir_attr(remote_path)
                if stat.S_ISREG(entry.st_mode) and entry.filename.lower().endswith(".csv")
            )
            if not filenames:
                raise ValueError(f"No CSV files available in SFTP folder {date_str}")

            def download_batch(client_and_batch):
                client, batch = client_and_batch
                downloaded = []
                for filename in batch:
                    local_file = local_dir / filename
                    client.get(posixpath.join(remote_path, filename), str(local_file))
                    downloaded.append(str(local_file))
                return downloaded

            # Use separate SFTP channels over one authenticated SSH connection.
            # This speeds up small files without a burst of new server logins.
            batches = [filenames[index::4] for index in range(min(4, len(filenames)))]
            for _ in range(len(batches) - 1):
                clients.append(SFTPClient.from_transport(transport))
            with ThreadPoolExecutor(max_workers=4) as executor:
                downloaded_files = sorted(
                    path for batch in executor.map(download_batch, zip(clients, batches))
                    for path in batch
                )
        finally:
            for client in clients:
                client.close()
            if transport is not None:
                transport.close()
        log.info("Downloaded %s CSV files for %s", len(downloaded_files), date_str)
        return downloaded_files, date_str

    @task
    def transform_data(extract_result: tuple):
        local_files, date_str = extract_result
        if not local_files:
            return None, date_str
        frame = transform_news_files(local_files, date_str)
        transformed_path = STAGING_AREA / date_str / "transformed.parquet"
        frame.to_parquet(transformed_path, index=False)
        log.info("Prepared %s news rows for %s", len(frame), date_str)
        # Pass a file path through XCom, rather than all the article text.
        return str(transformed_path), date_str

    @task
    def load_to_snowflake(transform_result: tuple):
        from snowflake.connector.pandas_tools import write_pandas

        transformed_path, date_str = transform_result
        if transformed_path is None:
            return date_str
        frame = pd.read_parquet(transformed_path)
        if frame.empty:
            raise ValueError("Refusing to mark an empty load as processed")
        conn = get_snowflake_connection(schema="RAW")
        try:
            with conn.cursor() as cursor:
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {SNOWFLAKE_TABLE} (
                        CATEGORY VARCHAR, DATETIME NUMBER(38,0), HEADLINE VARCHAR,
                        ID NUMBER(38,0), IMAGE VARCHAR, RELATED VARCHAR,
                        SOURCE VARCHAR, SUMMARY VARCHAR, URL VARCHAR,
                        PUBLISHED_AT TIMESTAMP_NTZ, SOURCE_DATE DATE,
                        SOURCE_FILE VARCHAR, LOADED_AT TIMESTAMP_NTZ
                    )
                """)
                stage_table = "M2_NEWS_STAGE"
                success, _, rows, _ = write_pandas(
                    conn, frame, stage_table, auto_create_table=True,
                    table_type="temporary", use_logical_type=True,
                )
                if not success or rows != len(frame):
                    raise RuntimeError("Snowflake did not stage every transformed row")
                columns = list(frame.columns)
                match = " AND ".join(f't."{key}" = s."{key}"' for key in MERGE_KEYS)
                updates = ", ".join(
                    f't."{column}" = s."{column}"' for column in columns
                    if column not in MERGE_KEYS
                )
                column_sql = ", ".join(f'"{column}"' for column in columns)
                values_sql = ", ".join(f's."{column}"' for column in columns)
                cursor.execute(f"""
                    MERGE INTO {SNOWFLAKE_TABLE} t USING {stage_table} s ON {match}
                    WHEN MATCHED THEN UPDATE SET {updates}
                    WHEN NOT MATCHED THEN INSERT ({column_sql}) VALUES ({values_sql})
                """)
                cursor.execute(
                    f"SELECT COUNT(*) FROM {SNOWFLAKE_TABLE} WHERE SOURCE_DATE = %s",
                    (date_str,),
                )
                if cursor.fetchone()[0] != len(frame):
                    raise RuntimeError(f"Snowflake row count does not match source for {date_str}")
            # This is written only after the MERGE and its row-count check succeed.
            with PROCESSED_LOG_FILE.open("a", encoding="utf-8") as processed_log:
                processed_log.write(f"{date_str}\n")
            log.info("Verified %s rows in RAW.%s for %s", len(frame), SNOWFLAKE_TABLE, date_str)
        finally:
            conn.close()
        return date_str

    @task
    def cleanup_staging_files(processed_date: str):
        # Validate both the date and resolved path before removing staging files.
        safe_date = date.fromisoformat(processed_date).isoformat()
        local_dir = (STAGING_AREA / safe_date).resolve()
        if local_dir.parent != STAGING_AREA.resolve():
            raise ValueError("Cleanup path must be inside the SFTP staging area")
        if local_dir.exists():
            shutil.rmtree(local_dir)
        log.info("Staging cleanup complete for %s", safe_date)

    extracted = extract_from_sftp()
    transformed = transform_data(extracted)
    loaded_date = load_to_snowflake(transformed)
    cleanup_staging_files(loaded_date)


sftp_template_dag = sftp_template_pipeline()
