# ----------------------------------------------------------------
# tutorial.py
# Airflow 3.0 TaskFlow API — Tutorial DAG
# Demonstrates a dependency-free ETL flow:
# Extract → Transform → Quality Check → Load
# ----------------------------------------------------------------

from airflow.sdk import dag, task
from datetime import datetime, timedelta, timezone

# ----------------------------------------------------------------
# DAG Definition
# ----------------------------------------------------------------
@dag(
    dag_id="tutorial_etl_dag",
    description="Tutorial DAG showing a simple ETL flow (no external dependencies)",
    start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    schedule="@daily",
    catchup=True,
    max_active_runs=1,
    tags=["tutorial", "etl"],
)
def tutorial_etl_dag():
    """
    Educational ETL DAG for students.
    Uses `data_interval_start` to show the recommended Airflow 3 date context.
    Runs daily from a fixed start date to keep backfills predictable.
    Each task only logs text — no APIs, no databases, no external dependencies.
    """

    @task(retries=1, retry_delay=timedelta(minutes=1))
    def extract(data_interval_start=None):
        run_date = data_interval_start.date()
        print(f"\n--- EXTRACT ({run_date}) ---")
        print("Pretend we fetch raw data here (API call, DB query, etc).")
        records = [f"record_{i}_{run_date}" for i in range(1, 6)]
        print(f"Extracted records: {records}")
        return records

    @task(retries=1, retry_delay=timedelta(minutes=1))
    def transform(records: list, data_interval_start=None):
        run_date = data_interval_start.date()
        print(f"\n--- TRANSFORM ({run_date}) ---")
        print("Pretend we clean or enrich the raw data here.")
        transformed = [r.upper() for r in records]
        print(f"Transformed records: {transformed}")
        return transformed

    @task(retries=1, retry_delay=timedelta(minutes=1))
    def quality_check(records: list, data_interval_start=None):
        run_date = data_interval_start.date()
        print(f"\n--- QUALITY CHECK ({run_date}) ---")
        if not records:
            raise ValueError("No records to load!")
        print(f"Quality check passed: {len(records)} records ready for load.")
        return records

    @task(retries=1, retry_delay=timedelta(minutes=1))
    def load(records: list, data_interval_start=None):
        run_date = data_interval_start.date()
        print(f"\n--- LOAD ({run_date}) ---")
        print("Pretend we load the records into a warehouse or database.")
        print(f"Loaded {len(records)} records successfully.")
        return "Load complete."

    # DAG flow: extract → transform → quality_check → load
    raw = extract()
    clean = transform(raw)
    checked = quality_check(clean)
    load(checked)

# ----------------------------------------------------------------
# DAG Exposure
# ----------------------------------------------------------------
tutorial_etl_dag()
