"""
# MongoDB to Snowflake DAG Template

This DAG serves as a template for extracting data from a MongoDB collection,
staging it, transforming it, and loading it into Snowflake. It follows ETL
best practices, including the use of a staging area and a processed-date log
for idempotency.

## Optional Airflow 3 exploration (not required for the baseline exercise)
Once the baseline pipeline works, students can experiment with setup/teardown
tasks for the SSH tunnel and MongoDB client so cleanup still runs after a
failure, `@task.short_circuit` or branching for weekend/holiday decisions, and
dynamic task mapping with `expand()` when processing multiple collections or
partitions. The existing `try/finally` cleanup is the required baseline.

## Instructions for Students:
1.  **Fill in the `TODO` sections** in each task to complete the pipeline.
2.  **MongoDB Connection:** The `extract_from_mongo` task uses an SSH tunnel.
    Review the `create_ssh_tunnel` and `get_mongo_client` functions in `utils.py`
    to understand how the connection is established and closed.
3.  **Staging:** Data is first saved as a CSV to the `staging/mongo/{date}` folder.
4.  **Idempotency:** A log file at `staging/mongo/processed_dates.txt` is checked
    to prevent re-processing already loaded dates.
5.  **Cleanup:** A final task removes the temporary staging folder after a successful run.
6.  **Trading-day guard:** This is the stock pipeline. If a *trading day* (per the NYSE
    calendar) has **no data** in MongoDB, the run **fails on purpose** so the gap is
    visible and Airflow retries / lets you re-run it — instead of silently "succeeding"
    with zero rows (which is how gaps get hidden). Weekends and market holidays with no
    data pass normally, since no data is expected. If you adapt this template to
    non-market data, remove or change that guard in `extract_from_mongo`.
"""

from __future__ import annotations
import logging
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pandas_market_calendars as mcal
from airflow.sdk import dag, task
from airflow.exceptions import AirflowException

# Import necessary utilities
from utils import create_ssh_tunnel, get_mongo_client, get_snowflake_connection

# -- Set up logging
log = logging.getLogger(__name__)

# -- DAG Configuration
# IMPORTANT: These paths are relative to the Airflow project root.
STAGING_AREA = Path("staging/mongo")
PROCESSED_LOG_FILE = STAGING_AREA / "processed_dates.txt"
SNOWFLAKE_TABLE = "YOUR_MONGO_TARGET_TABLE_HERE"  # TODO: Replace with your Snowflake table name



@dag(
    dag_id="mongo_template_dag",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["template", "mongo", "snowflake", "best-practice"],
    default_args={
        "owner": "airflow",
        "retries": 1,
        "retry_delay": timedelta(minutes=3),
    },
)
def mongo_template_pipeline():
    """
    ### MongoDB to Snowflake ELT Best Practices

    This DAG demonstrates a robust ELT pipeline that:
    1.  **Extracts** data from MongoDB, checking a log to prevent duplicates.
    2.  **Stages** the data locally as a CSV file.
    3.  **Transforms** the staged data using pandas.
    4.  **Loads** the data into Snowflake.
    5.  **Logs** the processed date upon success.
    6.  **Cleans up** the staging directory.
    """

    @task
    def extract_from_mongo(data_interval_start=None):
        """
        Connects to MongoDB via an SSH tunnel, queries for data based on the
        execution date, and saves it to a local staging file.
        """
        date_str = data_interval_start.strftime('%Y-%m-%d')
        local_dir = STAGING_AREA / date_str

        # --- Idempotency Check ---
        with open(PROCESSED_LOG_FILE, "r") as f:
            if date_str in f.read().splitlines():
                log.info(f"Date {date_str} has already been processed. Skipping.")
                return None, date_str

        local_dir.mkdir(exist_ok=True)
        
        tunnel = None
        mongo_client = None
        try:
            # --- Establish Connections ---
            log.info("Starting SSH tunnel to MongoDB...")
            tunnel = create_ssh_tunnel()
            mongo_client = get_mongo_client(local_port=tunnel.local_bind_port)
            
            # TODO: Specify your database and collection name
            db = mongo_client["your_db_name"]
            collection = db["your_collection_name"]
            log.info(f"Connected to MongoDB collection: {collection.name}")

            # --- Define Query ---
            # This query finds documents where the 'datetime' field matches the execution day.
            start_of_day = f"{date_str}T00:00:00Z"
            end_date = (datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=1)).strftime('%Y-%m-%d')
            end_of_day = f"{end_date}T00:00:00Z"
            
            # TODO: Adjust the query field ('datetime') and logic as needed for your collection.
            query = {"datetime": {"$gte": start_of_day, "$lt": end_of_day}}
            log.info(f"Executing query: {query}")
            
            # TODO: Define the projection to select specific fields from the document.
            # An empty projection `{}` will retrieve all fields.
            projection = {"_id": 0} # Exclude the default MongoDB ID
            
            # --- Fetch Data and Stage ---
            records = list(collection.find(query, projection))
            if not records:
                # No data for this date. If it's a TRADING DAY, the upstream source is
                # missing data -> fail loudly so the run is visible and retries, instead of
                # silently "succeeding" with zero rows (which hides the gap). If it's a
                # weekend or market holiday, no data is expected -> skip successfully.
                is_trading_day = not mcal.get_calendar("NYSE").schedule(
                    start_date=date_str, end_date=date_str
                ).empty
                if is_trading_day:
                    raise AirflowException(
                        f"No MongoDB records for trading day {date_str}. Upstream data is "
                        "missing for this date -- failing so the gap is visible and can be "
                        "retried / re-run once the source is backfilled."
                    )
                log.info(f"{date_str} is not a trading day (weekend/holiday); no data expected. Skipping.")
                return None, date_str

            df = pd.DataFrame(records)
            output_path = local_dir / "mongo_data.csv"
            df.to_csv(output_path, index=False)
            
            log.info(f"Successfully staged {len(df)} records to {output_path}")
            return str(output_path), date_str

        except Exception as e:
            log.error(f"MongoDB Extract failed: {e}")
            raise
        finally:
            # --- Close Connections ---
            if mongo_client:
                mongo_client.close()
                log.info("MongoDB connection closed.")
            if tunnel:
                tunnel.stop()
                log.info("SSH tunnel closed.")
    
    @task
    def transform_data(extract_result: tuple):
        """
        Reads the staged CSV, applies transformations, and returns a DataFrame.
        """
        filepath, date_str = extract_result
        if not filepath:
            log.info("No file to transform. Skipping.")
            return None, date_str

        log.info(f"Transforming data from {filepath}...")
        df = pd.read_csv(filepath)

        # TODO: Add your transformation logic.
        # Examples:
        # - Rename columns: df.rename(columns={"old_name": "NEW_NAME"}, inplace=True)
        # - Convert data types: df['amount'] = pd.to_numeric(df['amount'])
        # - Create a unique hash ID: df['record_id'] = df.apply(lambda row: hash(tuple(row)), axis=1)

        log.info(f"Transformation complete. DataFrame has {len(df)} rows.")
        return df, date_str

    @task
    def load_to_snowflake(transform_result: tuple):
        """
        Loads the transformed data into Snowflake and logs the processed date.
        """
        df, date_str = transform_result
        if df is None or df.empty:
            log.info("No data to load. Skipping Snowflake and logging steps.")
            return date_str

        log.info(f"Loading {len(df)} rows into Snowflake table: {SNOWFLAKE_TABLE}")
        # conn = get_snowflake_connection() # TODO: Uncomment
        try:
            # TODO: Use conn.cursor() or write_pandas() to load the DataFrame.
            # A MERGE statement is recommended to prevent duplicates if the DAG is re-run
            # before the date is logged.
            log.info("Placeholder for Snowflake load logic.")

            # --- Log Processed Date on Success ---
            with open(PROCESSED_LOG_FILE, "a") as f:
                f.write(f"{date_str}\n")
            log.info(f"Successfully loaded data and logged {date_str} as processed.")
        
        except Exception as e:
            log.error(f"Snowflake load failed: {e}")
            raise
        finally:
            # if conn: conn.close() # TODO: Uncomment
            log.info("Snowflake connection placeholder closed.")
        
        return date_str

    @task
    def cleanup_staging_area(processed_date: str):
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
    # OPTIONAL: Model the tunnel/client lifecycle with Airflow setup/teardown
    # tasks. A teardown task is designed to run even when work in its scope
    # fails. Do not remove the working `try/finally` cleanup until the extension
    # has been tested in the local Airflow environment.
    extract_result = extract_from_mongo()
    transform_result = transform_data(extract_result)
    loaded_date = load_to_snowflake(transform_result)
    cleanup_staging_area(loaded_date)


# Instantiate the DAG
mongo_template_dag = mongo_template_pipeline()
