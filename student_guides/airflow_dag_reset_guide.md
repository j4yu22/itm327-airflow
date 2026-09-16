# 🧹 Managing and Resetting Airflow DAG History (ITM 327)

## 📘 Overview
Sometimes your Airflow DAGs keep running old “catch-up” runs or show many historical dates still in progress.  
This happens when:
- `catchup=True` and there are missing daily runs  
- or your DAG marked empty runs as *success* instead of *failed*

This guide shows how to:
1. Open a terminal inside your Airflow container  
2. Clear or delete old DAG runs safely  
3. Add logic so empty folders fail properly next time  

---

## 🐳 Step 1: Open a terminal inside Airflow

From the folder containing your `docker-compose.yaml` file:

```bash
docker ps
```

You’ll see containers like:
```
apache_airflow-airflow-scheduler-1
apache_airflow-airflow-apiserver-1
apache_airflow-airflow-worker-1
...
```

Connect to one (the **scheduler** is best):

```bash
docker exec -it apache_airflow-airflow-scheduler-1 bash
```

You should see:
```
airflow@<container-id>:/opt/airflow$
```

---

## 🧠 Step 2: Verify Airflow CLI works

Inside the container:

```bash
airflow version
```

Expected output: `3.0.0` (or another valid version)

---

## 🧹 Step 3: Clear or Delete DAG Runs

### Option A – *Clear* all task states (keeps DAG runs visible)
```bash
airflow tasks clear sftp_to_snowflake_dag --yes --include-upstream --include-downstream
```

### Option B – *Delete* all historical DAG runs (fresh start)
```bash
airflow dags delete sftp_to_snowflake_dag --yes
```

> 💡 *Tip:* You can replace `sftp_to_snowflake_dag` with any DAG ID.

---

## ⏸️ Step 4 (Optional): Pause Before Clearing

To avoid Airflow immediately rescheduling while you reset:

```bash
airflow dags pause sftp_to_snowflake_dag
airflow dags delete sftp_to_snowflake_dag --yes
airflow dags unpause sftp_to_snowflake_dag
```

---

## 🧩 Step 5: Exit the Container

```bash
exit
```

Then refresh the Airflow web UI — all previous runs should be gone.

---

## ✅ Step 6: Improve Your DAG’s File-Check Logic

Add this to your SFTP DAG to **fail** when no files exist:

```python
if not files:
    raise FileNotFoundError(f"No files found in {full_path}")
```

Failing the task ensures Airflow marks the run as **failed** instead of “successful,”  
so backfills don’t appear complete when no data was processed.

---

## 🧠 Quick Reset Script (One-Liner)

You can run this anytime from your host machine:

```bash
docker exec -it apache_airflow-airflow-scheduler-1 bash -c "airflow dags pause sftp_to_snowflake_dag &&  airflow dags delete sftp_to_snowflake_dag --yes &&  airflow dags unpause sftp_to_snowflake_dag"
```

---

## 🧭 Summary Table

| Action | Command | Result |
|--------|----------|--------|
| View running containers | `docker ps` | Lists Airflow services |
| Enter scheduler | `docker exec -it apache_airflow-airflow-scheduler-1 bash` | Opens container shell |
| Clear runs | `airflow tasks clear <dag_id>` | Keeps DAG but resets task states |
| Delete runs | `airflow dags delete <dag_id>` | Removes all run history |
| Pause DAG | `airflow dags pause <dag_id>` | Prevents new runs while fixing |
| Exit container | `exit` | Return to host terminal |

---

**Author:** ITM 327 — Data Engineering Fundamentals  
**Topic:** Airflow 3.0+ DAG Management and History Reset  
**Last Updated:** October 2025  
