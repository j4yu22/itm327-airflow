# Airflow Docker Quick Reference (Airflow 3.3.1)

## Starting Airflow
Start all Airflow services (scheduler, apiserver, dag processor, worker, triggerer, etc.) in the background:

```bash
docker-compose up -d
```

Check running containers:

```bash
docker ps
```

---

## Stopping Airflow
Stop all Airflow services:

```bash
docker-compose down
```

This removes the running containers but keeps volumes (so your metadata DB persists).

---

## Restarting Services
If a DAG is not showing up in the UI, most often you only need to restart the **scheduler** and **dag-processor**:

```bash
docker-compose restart airflow-scheduler airflow-dag-processor
```

If in doubt, restart everything:

```bash
docker-compose down
docker-compose up -d
```

---

## Viewing Logs
See scheduler logs (useful to check DAG parsing):

```bash
docker-compose logs -f airflow-scheduler
```

See apiserver logs (the web UI):

```bash
docker-compose logs -f airflow-apiserver
```

---

## Forcing DAG Refresh
1. Make sure your DAG file is in the `dags/` folder.  
2. Restart `airflow-scheduler` and `airflow-dag-processor`.  
3. Check the scheduler logs to confirm it processed your DAG.  

---

✅ That’s the minimum workflow to get new DAGs to show up reliably in **Airflow 3.3.1**.
