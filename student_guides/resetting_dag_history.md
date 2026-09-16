# 🔄 Resetting DAG History in Apache Airflow

This guide explains how to **clear, delete, or reset DAG run history** when testing or demonstrating workflows.

---

## 🧭 Why Reset DAG History?

Resetting DAG history is useful when:

- You want to **re-run all past days** after fixing a DAG or data issue.  
- You need to **remove stale task results** or failed runs before grading or demoing.  
- You’re preparing a **fresh environment** for students or automation tests.

---

## 🖥️ Option 1 — Reset Using the Airflow Web UI (Recommended)

1. Open the **Airflow UI** at [http://localhost:8080](http://localhost:8080).
2. Click the DAG you want to reset (e.g., `sftp_to_snowflake_dag`).
3. Go to the **Graph** or **Grid** view.
4. Click the **☰ Actions** (three-dot) menu in the top-right.
5. Choose one of:

   | Action | Effect |
   |---------|---------|
   | **Clear → All Task Instances** | Marks all task instances as “cleared”; Airflow will re-run them if `catchup=True`. |
   | **Mark as Success** | Marks runs successful without re-running. |
   | **Delete** | Permanently removes run records from the metadata database. |

---

## 🧱 Option 2 — Reset via the CLI (Inside the Airflow Container)

1. Open a shell in the Airflow scheduler container:
   ```bash
   docker exec -it airflow-scheduler-1 bash
   ```

2. **List all DAG runs**:
   ```bash
   airflow dags list-runs -d sftp_to_snowflake_dag
   ```

3. **Clear all task instances** (forces re-execution on next scheduler cycle):
   ```bash
   airflow tasks clear sftp_to_snowflake_dag --yes --dag-run-state all --task-state all
   ```

4. **Delete all DAG run records** (removes history without re-running):
   ```bash
   airflow dags delete sftp_to_snowflake_dag --yes
   ```

---

## 💣 Option 3 — Full Environment Reset (All DAGs)

If you want to completely wipe the Airflow metadata database:

```bash
docker-compose down -v
docker-compose up -d
```

This drops all PostgreSQL volumes, clearing **every DAG’s history**, logs, and scheduler state.

---

## ✅ Summary

| Goal | Action |
|------|---------|
| Re-run all past tasks | Clear All Task Instances |
| Remove all history for one DAG | `airflow dags delete <dag_id> --yes` |
| Start completely fresh | `docker-compose down -v` then `up -d` |

---

**Tip for Students:**  
When testing backfill and catch-up behavior, always clear task instances instead of deleting runs — this lets Airflow re-run the historical dates automatically.

---

**Author:** ITM 327 — Data Engineering Fundamentals  
**Last Updated:** November 12, 2025
