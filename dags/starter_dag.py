from __future__ import annotations

import json
import os
import logging
from datetime import datetime, timedelta, timezone

import requests
import pandas as pd # Import pandas for DataFrame operations
from snowflake.connector.pandas_tools import write_pandas

from airflow.sdk import dag, task, get_current_context

# Import utility functions from utils.py (need to ensure it's on the path if not already)
# This project's setup seems to handle dags/utils.py imports automatically for DAGs.
from utils import get_snowflake_connection

# -------------------------------------------------------------------
# Configuration
# -------------------------------------------------------------------
ON_OFF_SNOWFLAKE_LOAD_ENABLED = False  # Set to True to enable Snowflake loading
SNOWFLAKE_DATABASE = os.getenv("SNOWFLAKE_DATABASE", "PROJECT_DB") # Default to PROJECT_DB
SNOWFLAKE_SCHEMA = os.getenv("SNOWFLAKE_SCHEMA", "RAW") # Default to RAW
SNOWFLAKE_TABLE = "BORED_API_ACTIVITIES" # Table name for Bored API data

@dag(
    dag_id="starter_dag",
    # Dynamic: "7 days ago at midnight UTC", evaluated at DAG parse time. Safety net for the starter — even if you flip catchup=True, the worst-case backfill is ~7 daily runs. For DAG 2 / DAG 3 with real backfill, use a fixed date like datetime(2026, 1, 6, tzinfo=timezone.utc) and let catchup=True walk from there.
    start_date=(datetime.now(timezone.utc) - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0),
    schedule="@daily",
    catchup=False, # Flip to True only after you understand backfill; with an old start_date + @daily this can enqueue 100+ runs at once and stall the local stack
    tags=["starter", "example", "elt", "snowflake"],
)
def starter_dag_elt():
    """
    ### Starter ELT DAG
    This DAG demonstrates a simple ELT (Extract, Load, Transform) pattern
    with an optional Snowflake loading step.

    1.  **Extract:** Fetches a random activity from the Bored API.
    2.  **Load (Staging):** Saves the raw JSON response to a local staging file.
    3.  **Transform:** Reads the staged file, extracts and cleans up the data.
    4.  **Load (Snowflake - Optional):** Loads the transformed data into a Snowflake table.
        This step can be enabled/disabled via the `ON_OFF_SNOWFLAKE_LOAD_ENABLED` switch.
    """

    @task(retries=3, retry_delay=timedelta(seconds=10))
    def extract_activity():
        """
        Fetches a random activity from the Bored API (community replacement).
        """
        response = requests.get("https://bored-api.appbrewery.com/random", timeout=15)
        response.raise_for_status()  # Raise an exception for bad status codes
        return response.json()

    @task
    def load_raw_activity(activity_data: dict):
        """
        Saves the raw activity data to a local staging file.
        This simulates loading data into a staging area (like S3 or a staging table).
        """
        # Using a fixed directory within the Airflow container's volume mount
        # (defined in docker-compose.yaml as /opt/airflow/staging)
        staging_dir = "/opt/airflow/staging/activities"
        os.makedirs(staging_dir, exist_ok=True)
        
        # Use a timestamp in the filename to ensure uniqueness for each run
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        file_path = os.path.join(staging_dir, f"activity_{activity_data.get('key', timestamp)}.json")
        
        with open(file_path, "w") as f:
            json.dump(activity_data, f)
            
        logging.info(f"Raw activity data saved to: {file_path}")
        return file_path

    @task
    def transform_data(file_path: str):
        """
        Reads the staged file, transforms the data.

        Demonstrates the Airflow runtime-context pattern you'll reuse in DAG 2 and DAG 3:
        instead of stamping rows with wall-clock `datetime.now()`, ask Airflow which
        logical date this run represents via `get_current_context()`. When catchup=True
        backfills 100 days, each run's FETCH_DATE will be its own historical date —
        not all stamped with today.
        """
        # data_interval_start is the start of the schedule interval this run represents.
        # For a backfilled run on 2026-02-15, this is 2026-02-15T00:00:00+00:00 — not "now".
        context = get_current_context()
        logical_date = context["data_interval_start"]

        with open(file_path, "r") as f:
            data = json.load(f)

        # Map accessibility string values to numeric (API changed from numeric to string)
        accessibility_mapping = {
            "Few to no challenges": 0.0,
            "Minor challenges": 0.25,
            "Some challenges": 0.5,
            "Major challenges": 0.75,
            "Significant challenges": 1.0,
        }
        raw_accessibility = data.get("accessibility")
        if isinstance(raw_accessibility, str):
            accessibility_value = accessibility_mapping.get(raw_accessibility, 0.5)
        else:
            accessibility_value = raw_accessibility

        # Simple transformation: select specific fields and create a DataFrame
        transformed_record = {
            "ACTIVITY_IDEA": data.get("activity"),
            "CATEGORY": data.get("type"),
            "PARTICIPANTS_NEEDED": data.get("participants"),
            "PRICE": data.get("price"),
            "LINK": data.get("link"),
            "ACCESSIBILITY": accessibility_value,
            "UNIQUE_KEY": data.get("key"), # Bored API provides a unique key per activity
            "FETCH_DATE": logical_date.isoformat()  # Airflow's run date — historical on backfills, today on a live run
        }
        
        # Convert to pandas DataFrame for easy loading to Snowflake
        df = pd.DataFrame([transformed_record])
        
        logging.info("Transformed activity data (first 5 rows):")
        logging.info(df.head().to_string())
        
        return df

    @task
    def load_transformed_data_to_snowflake(df: pd.DataFrame):
        """
        Loads the transformed DataFrame into Snowflake.
        """
        if not ON_OFF_SNOWFLAKE_LOAD_ENABLED:
            logging.info("Snowflake loading is disabled by configuration. Skipping.")
            return

        if df.empty:
            logging.info("No data to load into Snowflake. Skipping.")
            return

        logging.info(f"Attempting to load {len(df)} rows to Snowflake table: {SNOWFLAKE_DATABASE}.{SNOWFLAKE_SCHEMA}.{SNOWFLAKE_TABLE}")

        # Establish Snowflake connection using credentials from .env
        # Ensure SNOWFLAKE_USER, SNOWFLAKE_PASSWORD/KEY, SNOWFLAKE_ACCOUNT are set in your .env
        conn = get_snowflake_connection(schema=SNOWFLAKE_SCHEMA)
        
        try:
            # Create table if it doesn't exist (DML based on DataFrame columns)
            # This is a basic example; for production, use DDL in version control.
            # Example DDL for your Snowflake table (run this manually in Snowflake once):
            #
            # CREATE TABLE IF NOT EXISTS PROJECT_DB.RAW.STARTER_DAG_LASTNAME_FI (
            #     ACTIVITY_IDEA VARCHAR,
            #     CATEGORY VARCHAR,
            #     PARTICIPANTS_NEEDED NUMBER(38,0),
            #     PRICE FLOAT,
            #     LINK VARCHAR,
            #     ACCESSIBILITY FLOAT,
            #     UNIQUE_KEY VARCHAR,
            #     FETCH_DATE TIMESTAMP_NTZ
            # );
            #
            # Adjust data types as needed based on your specific requirements.

            success, nchunks, nrows, _ = write_pandas(
                conn=conn,
                df=df,
                table_name=SNOWFLAKE_TABLE,
                database=SNOWFLAKE_DATABASE,
                schema=SNOWFLAKE_SCHEMA,
                auto_create_table=False, # Set to True if you want Pandas to auto-create (not recommended for prod)
                overwrite=False,         # Set to True for full refresh each run, False to append
                quote_identifiers=False  # Set to True if your column names have spaces/special chars
            )
            
            if success:
                logging.info(f"✅ Successfully loaded {nrows} rows to Snowflake table {SNOWFLAKE_TABLE}.")
            else:
                logging.error(f"❌ Failed to load data to Snowflake.")

        except Exception as e:
            logging.error(f"❌ Error loading data to Snowflake: {e}")
            raise # Re-raise the exception to fail the Airflow task
        finally:
            conn.close()
            logging.info("Snowflake connection closed.")


    # Define the ELT flow
    raw_activity_data = extract_activity()
    staged_activity_file = load_raw_activity(raw_activity_data)
    transformed_activity_df = transform_data(staged_activity_file)
    load_transformed_data_to_snowflake(transformed_activity_df)

# Instantiate DAG
starter_dag_elt()
