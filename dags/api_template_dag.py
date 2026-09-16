"""
# API to Snowflake DAG Template

This DAG provides a skeleton for fetching data from an API, staging it,
transforming it, and loading it into Snowflake, following ETL best practices.

## Optional Airflow 3 exploration (not required for the baseline exercise)
The starter DAG intentionally stays simple. After this pipeline works, students
can experiment with `expand()` for dynamic task mapping (one mapped task per
city), `@task_group` to group extract/transform/load stages, or
`@task.short_circuit` to make the no-data path explicit. Keep the original
linear version working before trying these extensions.

## Instructions for Students:
1.  **Fill in the `TODO` sections** in each task to complete the pipeline.
2.  **API Connection:** The `extract_from_api` task connects to the Open-Meteo API.
    Review the `openmeteopy` library and the `build_weather_record` function in
    `utils.py` to understand how it works. If the pip install fails, comment out
    the `openmeteopy` line in `requirements.txt` and rebuild; this DAG will use
    the vendored copy in `dags/libs/openmeteopy`.
3.  **Staging:** Data is saved to a CSV in the `staging/api/{date}` folder.
4.  **Idempotency:** The DAG checks a log file (`staging/api/processed_dates.txt`) 
    to avoid re-processing dates.
5.  **Cleanup:** A final task removes temporary files after a successful run.
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
from utils import get_snowflake_connection, build_weather_record

# Import weather data libraries.
# Prefer the pip-installed package when available; fall back to the vendored copy in dags/libs.
try:
    from openmeteopy import OpenMeteo
    from openmeteopy.daily import DailyHistorical
    from openmeteopy.options import HistoricalOptions
except ImportError:  # Use the vendored library if pip install fails in the container.
    from libs.openmeteopy.client import OpenMeteo
    from libs.openmeteopy.daily.historical import DailyHistorical
    from libs.openmeteopy.options.historical import HistoricalOptions


# -- Set up logging
log = logging.getLogger(__name__)

# -- DAG Configuration
STAGING_AREA = Path("staging/api")
PROCESSED_LOG_FILE = STAGING_AREA / "processed_dates.txt"
SNOWFLAKE_TABLE = "YOUR_WEATHER_TABLE_NAME_HERE"  # TODO: Replace with your target table name

# A dictionary of cities and their coordinates for the API call
CITIES = {
    "New York": {"latitude": 40.7128, "longitude": -74.0060},
    "London": {"latitude": 51.5074, "longitude": -0.1278},
    "Tokyo": {"latitude": 35.6895, "longitude": 139.6917},
}



@dag(
    dag_id="api_template_dag",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["template", "api", "snowflake", "best-practice"],
    default_args={
        "owner": "airflow",
        "retries": 1,
        "retry_delay": timedelta(minutes=3),
    },
)
def api_template_pipeline():
    """
    ### API to Snowflake ELT Best Practices

    This DAG demonstrates a robust ELT pipeline that:
    1.  **Extracts** data from the Open-Meteo API for a list of cities.
    2.  **Stages** the data locally as a CSV file.
    3.  **Transforms** the data using pandas.
    4.  **Loads** the transformed data into Snowflake.
    5.  **Logs** the processed date to ensure idempotency.
    6.  **Cleans up** the staging directory.
    """

    @task
    def extract_from_api(data_interval_start=None):
        """
        Connects to the API, downloads data for the execution date, and saves it to a staging file.
        """
        date_str = data_interval_start.strftime('%Y-%m-%d')
        local_dir = STAGING_AREA / date_str
        
        # --- Idempotency Check ---
        with open(PROCESSED_LOG_FILE, "r") as f:
            if date_str in f.read().splitlines():
                log.info(f"Date {date_str} already processed. Skipping.")
                return None, date_str

        local_dir.mkdir(exist_ok=True)
        all_cities_data = []

        log.info(f"Fetching weather data for {date_str}")

        try:
            for city, coords in CITIES.items():
                log.info(f"Getting data for {city}...")
                
                # --- Setup API Connection ---
                # This uses the openmeteopy library to define the API parameters.
                options = HistoricalOptions(
                    latitude=coords["latitude"],
                    longitude=coords["longitude"],
                    start_date=date_str,
                    end_date=date_str,
                )
                
                # TODO: Add more daily variables here!
                # Refer to the `openmeteopy.daily.DailyHistorical` class for available options.
                # Example: .weather_code().sunrise().sunset()
                daily = DailyHistorical().temperature_2m_max().temperature_2m_min().precipitation_sum().windspeed_10m_max()

                mgr = OpenMeteo(options, daily=daily.all())
                response = mgr.get_dict()
                
                # The `build_weather_record` function from utils.py helps safely parse the API response. 
                # If you added columns above to the daily object, update this `build_weather_record` function accordingly inside utils.py.
                record = build_weather_record(response, date_str, city)
                all_cities_data.append(record)

            if not all_cities_data:
                log.warning("No data was fetched from the API.")
                return None, date_str

            # --- Stage the Data ---
            df = pd.DataFrame(all_cities_data)
            output_path = local_dir / "weather_data.csv"
            df.to_csv(output_path, index=False)
            
            log.info(f"Successfully staged {len(df)} records to {output_path}")
            return str(output_path), date_str

        except Exception as e:
            log.error(f"API Extract failed: {e}")
            raise


    @task
    def transform_data(extract_result: tuple):
        """
        Reads the staged data, applies transformations, and returns a DataFrame.
        """
        filepath, date_str = extract_result
        if not filepath:
            log.info("No file path provided. Skipping transformation.")
            return None, date_str

        log.info(f"Transforming data from {filepath}...")
        df = pd.read_csv(filepath)

        # TODO: Add your data transformation logic here.
        # For example, you could add a unique ID, convert units, or derive new columns.
        # df['temp_range_c'] = df['max_temp'] - df['min_temp']
        # df['load_ts'] = datetime.utcnow()
        
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
        # conn = get_snowflake_connection() # TODO: Uncomment when ready
        try:
            # TODO: Use conn.cursor() to execute a MERGE statement or `write_pandas`.
            # A MERGE statement is recommended for idempotency.
            # Example:
            # from snowflake.connector.pandas_tools import write_pandas
            # success, _, _, _ = write_pandas(conn, df, SNOWFLAKE_TABLE, auto_create_table=True, overwrite=False)
            # if not success:
            #     raise Exception("Failed to write to Snowflake.")
            
            # --- Log Processed Date on Success ---
            with open(PROCESSED_LOG_FILE, "a") as f:
                f.write(f"{date_str}\n")
            log.info(f"Successfully loaded data and logged {date_str} as processed.")
        
        except Exception as e:
            log.error(f"Snowflake load failed: {e}")
            raise
        finally:
            # if conn: conn.close() # TODO: Uncomment when ready
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
    # OPTIONAL: Once the linear pipeline works, try mapping the city-level API
    # work with `fetch_city.expand(city=list(CITIES))` instead of looping over
    # CITIES inside one task. Airflow will create one task instance per city.
    # Another optional extension is to put extract/transform/load in a
    # `@task_group` so the Graph view stays readable as the DAG grows.
    extract_result = extract_from_api()
    transform_result = transform_data(extract_result)
    loaded_date = load_to_snowflake(transform_result)
    cleanup_staging_area(loaded_date)

# Instantiate the DAG
api_template_dag = api_template_pipeline()
