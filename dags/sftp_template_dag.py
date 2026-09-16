"""
# SFTP to Snowflake DAG Template

This DAG provides a skeleton for downloading files from an SFTP server,
transforming them, and loading them into Snowflake, incorporating best practices
for logging, staging, and preventing duplicate processing.

## Optional Airflow 3 exploration (not required for the baseline exercise)
After the baseline pipeline works, students can try `@task_group` for the
extract/transform/load stages, dynamic task mapping with `expand()` for one
mapped task per downloaded file, and an Airflow `Asset` for the staged output.
An asset-aware downstream DAG can then run when the SFTP load publishes new
data instead of relying only on a clock schedule.

## Instructions for Students:
1.  **Fill in the `TODO` sections** in each task to complete the pipeline.
2.  **Staging Area:** Files are downloaded to the `staging/sftp/{date}` directory.
3.  **Processed Log:** A file at `staging/sftp/processed_dates.txt` tracks completed dates to prevent re-processing.
4.  **Data Interval:** The DAG uses `data_interval_start` to process data for "yesterday", ensuring that backfills work correctly.
5.  **Cleanup:** A final task removes temporary files from the staging area upon success.
"""

from __future__ import annotations
import logging
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from airflow.sdk import dag, task

# Import necessary utilities
from utils import create_sftp_connection, get_snowflake_connection, list_files

# -- Set up logging
log = logging.getLogger(__name__)

# -- DAG Configuration
# Use Path for OS-agnostic path handling
# IMPORTANT: This path is relative to the Airflow project root.
STAGING_AREA = Path("staging/sftp")
PROCESSED_LOG_FILE = STAGING_AREA / "processed_dates.txt"
SNOWFLAKE_TABLE = "YOUR_TABLE_NAME_HERE"  # TODO: Replace with your target table name



@dag(
    dag_id="sftp_template_dag",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["template", "sftp", "snowflake", "best-practice"],
    default_args={
        "owner": "airflow",
        "retries": 1,
        "retry_delay": timedelta(minutes=5),
    },
)
def sftp_template_pipeline():
    """
    ### SFTP to Snowflake ELT Best Practices

    This DAG demonstrates a robust ELT pipeline that:
    1.  **Extracts** files from SFTP, skipping if already processed.
    2.  **Stages** files locally for transformation.
    3.  **Transforms** data using pandas.
    4.  **Loads** data into Snowflake.
    5.  **Logs** the processed date upon success.
    6.  **Cleans up** staged files.
    """

    @task
    def extract_from_sftp(data_interval_start=None):
        """
        Connects to SFTP, checks if the date has been processed, and downloads files.
        """
        date_str = data_interval_start.strftime('%Y-%m-%d')
        local_dir = STAGING_AREA / date_str

        # --- Check for Duplicates ---
        with open(PROCESSED_LOG_FILE, "r") as f:
            processed_dates = f.read().splitlines()
        if date_str in processed_dates:
            log.info(f"Date {date_str} has already been processed. Skipping.")
            return [], date_str # Return empty list to signal skipping

        # --- Proceed with Extraction ---
        local_dir.mkdir(exist_ok=True)
        #SFTP_DIR has the path of the SFTP directory stored and airflow will automatically load all .env variables 
        remote_path = f"{SFTP_DIR}{date_str}"
        downloaded_files = []

        log.info(f"Connecting to SFTP to download files from: {remote_path}")
        try:
            sftp = create_sftp_connection()
            file_list = list_files(sftp, remote_path)

            if not file_list:
                log.warning(f"No files found in {remote_path}. Skipping.")
                return [], date_str

            for filename in file_list:
                remote_file = os.path.join(remote_path, filename)
                local_file = local_dir / filename
                log.info(f"Downloading {remote_file} to {local_file}")
                # TODO: Uncomment the line below to perform the actual download
                # sftp.get(str(remote_file), str(local_file))
                downloaded_files.append(str(local_file))

            sftp.close()

        except Exception as e:
            log.error(f"SFTP Extract failed: {e}")
            raise

        log.info(f"Downloaded {len(downloaded_files)} files to {local_dir}")
        return downloaded_files, date_str

    @task
    def transform_data(extract_result: tuple):
        """
        Reads downloaded files from staging, combines them, and transforms the data.
        """
        local_files, date_str = extract_result
        if not local_files:
            log.info("No files to transform. Skipping.")
            return None, date_str

        log.info(f"Transforming {len(local_files)} files for date: {date_str}...")
        
        all_dfs = []
        for file_path in local_files:
            log.info(f"Reading {file_path}...")
            # TODO: Read each file into a DataFrame and append to `all_dfs`
            # Example:
            # try:
            #     df = pd.read_csv(file_path)
            #     all_dfs.append(df)
            # except pd.errors.EmptyDataError:
            #     log.warning(f"File is empty: {file_path}")
            pass

        if not all_dfs:
            log.warning("No data found in any of the files. Skipping.")
            return None, date_str
            
        combined_df = pd.concat(all_dfs, ignore_index=True)
        
        # TODO: Add your transformation logic here.
        # For example, rename columns, filter data, create new features.
        log.info("Applying transformations...")
        
        log.info(f"Transformation complete. Resulting DataFrame has {len(combined_df)} rows.")
        return combined_df, date_str

    @task
    def load_to_snowflake(transform_result: tuple):
        """
        Loads the transformed DataFrame to Snowflake and logs the processed date.
        """
        df, date_str = transform_result
        if df is None or df.empty:
            log.info("DataFrame is empty. Skipping Snowflake load.")
            return date_str # Return date_str so cleanup still runs for empty folders

        log.info(f"Loading {len(df)} rows into Snowflake table: {SNOWFLAKE_TABLE}")
        
        # TODO: Implement the Snowflake loading logic.
        # conn = get_snowflake_connection()
        try:
            # from snowflake.connector.pandas_tools import write_pandas
            # success, n_chunks, n_rows, _ = write_pandas(conn, df, SNOWFLAKE_TABLE)
            # if not success:
            #     raise Exception("Snowflake write_pandas failed.")
            # log.info(f"Successfully loaded {n_rows} rows to {SNOWFLAKE_TABLE}.")

            # --- Log Processed Date on Success ---
            with open(PROCESSED_LOG_FILE, "a") as f:
                f.write(f"{date_str}\n")
            log.info(f"Logged {date_str} to {PROCESSED_LOG_FILE}")

        except Exception as e:
            log.error(f"Snowflake load failed: {e}")
            raise
        finally:
            # if conn: conn.close()
            log.info("Snowflake connection placeholder closed.")
            
        return date_str

    @task
    def cleanup_staging_files(processed_date: str):
        """
        Removes the local directory for the processed date from the staging area.
        """
        if not processed_date:
            log.warning("No date provided for cleanup. Skipping.")
            return

        local_dir = STAGING_AREA / processed_date
        if local_dir.exists():
            log.info(f"Cleaning up staging directory: {local_dir}")
            shutil.rmtree(local_dir)
        else:
            log.warning(f"Staging directory not found for cleanup: {local_dir}")


    # --- Task Chaining ---
    # OPTIONAL: Replace the loop in `transform_data` with a mapped task such as
    # `read_one_file.expand(file_path=local_files)` after the extraction task
    # returns a list. This is an extension exercise; the loop is the required
    # baseline because it is easier to debug.
    extract_result = extract_from_sftp()
    transform_result = transform_data(extract_result)
    loaded_date = load_to_snowflake(transform_result)
    cleanup_staging_files(loaded_date)

# Instantiate the DAG
sftp_template_dag = sftp_template_pipeline()
