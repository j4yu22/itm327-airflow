# 🧹 Cleaning Up "Ghost" DAGs in Apache Airflow

## Overview
Sometimes you’ll see **many DAGs (10–20+) in Airflow** even though you only have **one `.py` file** in your `/dags` folder.  
This happens because Airflow **remembers every DAG it has ever seen** — even after the file is renamed, moved, or deleted.

---

## 🧠 Why It Happens
- Airflow scans `/opt/airflow/dags` and registers any file that defines a `@dag()` or `DAG()` object.
- When you delete or rename that file, Airflow **does not automatically remove** the old DAG from its metadata database.
- Those leftover entries appear in the UI as “ghost” DAGs — they have no code but still exist in Airflow’s records.

---

## 🧹 How to Fix It

### ✅ Option 1: Delete from CLI
Open a terminal in your Airflow project folder and run:

```bash
docker-compose exec airflow-cli bash
airflow dags delete <dag_id> --yes
```

Repeat for each old DAG you want to remove.

Or remove *all inactive/stale DAGs* (use carefully):

```bash
airflow dags list | grep -v <your_active_dag_id> | awk '{print $1}' | xargs -I {} airflow dags delete {} --yes
```

---

### ✅ Option 2: Delete from the Airflow UI
1. Go to the **DAGs** page.
2. Click the **🗑️ (trash can)** icon next to each unused DAG.
3. Confirm deletion.

---

## 🛡️ Preventing Ghost DAGs
- Keep **only one active DAG file** per project.
- If you rename a DAG file, also update the **`dag_id`** inside the file.
- After deleting or renaming, run  
  ```bash
  airflow dags delete old_dag_id --yes
  ```
- Avoid leaving backups like `my_dag_copy.py` or `v2_dag.py` inside `/dags`.

---

**Author:** ITM 327 — Data Engineering Fundamentals  
**Topic:** Cleaning Up Ghost DAGs in Apache Airflow  
**Last Updated:** October 2025
