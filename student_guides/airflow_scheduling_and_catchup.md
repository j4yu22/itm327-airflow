# 📅 Airflow 3.0+ Scheduling, Catchup, and DAG Timing

## Overview
In Apache Airflow 3.0 and later, scheduling behavior is more predictable but slightly stricter.  
This guide explains how `schedule`, `catchup`, and `max_active_runs` work together — and how to design DAGs that behave correctly when running daily or performing backfills.

---

## 1️⃣  The `@dag()` Schedule Parameters

### Example
```python
from airflow.decorators import dag
from datetime import datetime, timedelta

# Dynamically set start_date to the most recent Saturday before today
today = datetime.today()
days_since_saturday = (today.weekday() - 5) % 7  # 5 = Saturday
last_saturday = today - timedelta(days=days_since_saturday)
start_date = datetime(last_saturday.year, last_saturday.month, last_saturday.day)

@dag(
    dag_id="mongo_to_snowflake_dag",
    start_date=start_date,
    schedule="@daily",
    catchup=True,
    max_active_runs=3,
    tags=["stocks", "mongo", "snowflake"]
)
def mongo_to_snowflake():
    pass
```

| Parameter | Purpose |
|------------|----------|
| `start_date` | The first logical execution date for the DAG. |
| `schedule` | Defines how often Airflow should create runs (`@daily`, `@weekly`, or cron string). |
| `catchup` | If `True`, Airflow creates *all* missed runs since `start_date`; if `False`, only the next run is triggered. |
| `max_active_runs` | Limits how many DAG runs can execute at once (important for catch-up). |

---

## 2️⃣  Daily Scheduling

Setting  
```python
schedule="@daily"
catchup=False
```
means the DAG will run **once per day at midnight (UTC)** starting from the next day after `start_date`.  
Each run represents a *logical day* of data.

### 🗓️ Why Use `@daily` Instead of `@weekly`
Even if students only *run* their DAG once a week, using `@daily` defines **daily data intervals**.  
With `catchup=True`, Airflow automatically backfills one run per day for the past week when restarted.  
If you used `@weekly`, you’d only get one run per week — losing per-day visibility and control.  
Think of `@daily` as defining the *data grain*, and `catchup` as controlling *when those days run*.

---

## 3️⃣  Understanding Catch-Up

When `catchup=True`, Airflow will:
1. Look at `start_date` and today’s date.
2. Create one DAG Run for each day between them.
3. Run them sequentially or in limited parallel depending on `max_active_runs`.

### Example
If your DAG’s `start_date` is **2025-10-18** (last Saturday) and today is **2025-10-25**,  
Airflow will queue 7 runs — one per day — until it “catches up.”

Each run’s logical data window:
```
2025-10-18 → 2025-10-19
2025-10-19 → 2025-10-20
...
```

---

## 4️⃣  Controlling Backfill Speed: `max_active_runs`

| Setting | Effect |
|----------|--------|
| `max_active_runs=1` | One DAG Run executes at a time (safest). |
| `max_active_runs=5` | Up to 5 days run concurrently. |
| `max_active_runs=7` | Seven backfill days run in parallel until all catch up. |

Example:
```python
@dag(
    ...,
    catchup=True,
    max_active_runs=7
)
```
This lets the scheduler keep 7 daily runs active at once, starting new ones as old ones finish — like a sliding window through time.

---

## 5️⃣  Writing Date-Aware Tasks

Airflow automatically provides each task with two powerful context variables:
- `data_interval_start` → The start of the logical data window
- `data_interval_end` → The end of the logical data window

Use these to make your ETL logic aware of which day’s data it’s processing.

```python
from airflow.decorators import task

@task()
def print_date_range(data_interval_start=None, data_interval_end=None):
    print(f"Processing data for window: {data_interval_start.date()} → {data_interval_end.date()}")
```

Each run will print a different date window, depending on which logical day Airflow is executing.

---

## 6️⃣  When *Not* to Use Catch-Up

If your pipeline:
- always performs a **full refresh** (re-loads all data each run), or  
- doesn’t parameterize by execution date (`{{ ds }}` or `data_interval_start`)

then `catchup=True` will simply repeat the same work many times.  
Keep `catchup=False` for these DAGs.

Use `catchup=True` only when your extract logic filters data by **execution date**, for example:

```python
@task()
def extract_from_mongo(data_interval_start=None, data_interval_end=None):
    query = {
        "date": {
            "$gte": data_interval_start.date().isoformat(),
            "$lt": data_interval_end.date().isoformat()
        }
    }
    print(query)
```

This ensures each historical run loads only its day’s slice of data — safe and idempotent.

---

## 7️⃣  Summary Table

| Goal | Recommended Settings |
|------|-----------------------|
| Daily full refresh | `@daily`, `catchup=False`, `max_active_runs=1` |
| Daily incremental load | `@daily`, `catchup=True`, `max_active_runs=3–7` |
| Initial backfill of a year | Temporarily set `catchup=True`, tune `max_active_runs` for parallel speed, then disable afterward |

---

## 8️⃣  🧪 Mini Lab: Testing Catch-Up Behavior

This mini DAG lets you see catch-up and date windows in action — no external APIs required.

```python
from airflow.decorators import dag, task
from datetime import datetime, timedelta

# --- Calculate last Saturday dynamically ---
today = datetime.today()
days_since_saturday = (today.weekday() - 5) % 7  # 5 = Saturday
last_saturday = today - timedelta(days=days_since_saturday)
start_date = datetime(last_saturday.year, last_saturday.month, last_saturday.day)

@dag(
    dag_id="catchup_demo_dag",
    start_date=start_date,
    schedule="@daily",
    catchup=True,
    max_active_runs=3,
    tags=["demo", "catchup", "itm327"]
)
def catchup_demo_dag():

    @task()
    def print_date_window(data_interval_start=None, data_interval_end=None):
        print(f"Run window: {data_interval_start.date()} → {data_interval_end.date()}")

    print_date_window()

catchup_demo_dag()
```

### 💡 Lab Steps
1. Save this DAG as `catchup_demo_dag.py` in your `dags/` folder.
2. Run your Airflow containers (`docker-compose up -d`).
3. In the Airflow UI, unpause **`catchup_demo_dag`**.
4. Observe the scheduler automatically create multiple DAG runs — one for each missed day since last Saturday.
5. Open **Logs → print_date_window** to see each run’s logical data interval printed.

---
