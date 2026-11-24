# Student Airflow Template Setup

This is a ready-to-run Apache Airflow + Docker environment designed for classroom use. Students can use this to run Airflow DAGs that connect to datasources and process data pipelines.

## Before You Start
1. Click `Use this template` and save as your own repo
2. Clone your repo, I prefer the open in GitHub Desktop method
3. Open the cloned repo in VS Code

## Docker Setup
1. Make sure you have Docker installed on your machine. You can download it from the official Docker website. Here is the link: https://docs.docker.com/get-docker/

## Setup your .env file
1. Copy `.env.example` to `.env` and fill in the settings locally. Generate two different passwords with `python -c "import secrets; print(secrets.token_hex(32))"` (run it twice). Put one in `POSTGRES_PASSWORD` and the other in `_AIRFLOW_WWW_USER_PASSWORD`. Keep the database password URL-safe, as it is used in connection URLs. Never paste your credentials into an issue or commit them.
   - If you use `ENV_FILE_PATH` to select a different file, also pass that same file with `docker compose --env-file path/to/file` so Compose can read the required settings.
   - **Existing installs:** Changing these initializer values does not change passwords in an existing database volume or overwrite the Airflow account. Before switching an existing setup, back up the metadata database and work with the administrator to rotate both existing account passwords in place. Do not delete the volume just to update credentials. Keep the existing Fernet key if the instance already uses one; rotate it with Airflow's supported procedure, not by replacing it blindly.
2. Your instructor will share the `SNOWFLAKE_ACCOUNT` value in Slack. It uses the `ORG-ACCOUNT` format (e.g. `VXZJSRC-AG60135`), not the retired `SFEDU02` account or the older `xyz12345.us-west-2` locator. If you look up your account in Snowsight, the snippet there may include `authenticator = "externalbrowser"` — ignore that line; this stack uses key-pair auth (next section).
3. For FA26, Airflow project DAGs load into `PROJECT_DB.RAW`. The SQL modeling labs use `SNOWBEARAIR_DB.PUBLIC` as their source and `SNOWBEARAIR_DB.MODELED` for student-built tables.


## Local environment setup for local testing and key generation
Note: this `pip install` includes all the other libraries needed for the scripts in the Test folder to run locally outside of Docker. It also lets you run a key generation setup script for Airflow.

1. Open a new terminal in VS Code -> Terminal -> New Terminal
2. Run this code in the terminal
```bash
pip install cryptography paramiko==3.5.1 python-dotenv sshtunnel==0.4.0
```

3. Run the `airflow-core-fernet-key.py` script to generate a fernet key. This key is used to encrypt sensitive data in Airflow, such as passwords and connection strings.
```bash
python airflow-core-fernet-key.py
```

4. Set `FERNET_KEY` in `.env` to the generated key on a new setup. Keep it private and stable; Airflow uses it for existing encrypted connections.

## WINDOWS Generate a Public Key for Snowflake
1. Generate SSH Keys for Snowflake Connection. Run the following commands in a `git-bash shell`. (Windows users do not run in powershell, use a git-bash shell only)

```bash
mkdir -p ~/.ssh
openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out ~/.ssh/dbt_key.p8 -nocrypt
openssl rsa -in ~/.ssh/dbt_key.p8 -pubout -out ~/.ssh/dbt_key.pub
cat ~/.ssh/dbt_key.pub | clip
```

2. Set `SNOWFLAKE_KEY_HOST_PATH` in `.env` to the absolute path of this **private** file on your computer, for example `C:/Users/your-username/.ssh/dbt_key.p8`. Use forward slashes. Compose makes only this file available to the Airflow worker.
3. Your public key is now copied to your clipboard — paste it when prompted by your Snowflake admin (your teacher) to set up key pair authentication.

## MAC Generate a Public Key for Snowflake

1. Generate SSH Keys for Snowflake Connection. Run the following commands in a `terminal shell`.

```bash
mkdir -p ~/.ssh
openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out ~/.ssh/dbt_key.p8 -nocrypt
openssl rsa -in ~/.ssh/dbt_key.p8 -pubout -out ~/.ssh/dbt_key.pub
cat ~/.ssh/dbt_key.pub | pbcopy
```

2. Set `SNOWFLAKE_KEY_HOST_PATH` in `.env` to the absolute path of this **private** file on your computer, for example `/Users/your-username/.ssh/dbt_key.p8`. Compose makes only this file available to the Airflow worker.
3. Your public key is now copied to your clipboard — paste it when prompted by your Snowflake admin (your teacher) to set up key pair authentication.

Resource: [Snowflake Documentation on Key Pair Auth](https://docs.snowflake.com/en/user-guide/key-pair-auth)

## LINUX Generate a Public Key for Snowflake

1. Generate SSH keys for the Snowflake connection. Run the following in a terminal:

```bash
mkdir -p ~/.ssh
openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out ~/.ssh/dbt_key.p8 -nocrypt
openssl rsa -in ~/.ssh/dbt_key.p8 -pubout -out ~/.ssh/dbt_key.pub
cat ~/.ssh/dbt_key.pub | xclip -selection clipboard
```

If `xclip` is not installed, either install it (`sudo apt install xclip`) or run `cat ~/.ssh/dbt_key.pub` and copy the output manually.

2. Set `SNOWFLAKE_KEY_HOST_PATH` in `.env` to the absolute path of this **private** file on your computer, for example `/home/your-username/.ssh/dbt_key.p8`. Set `AIRFLOW_UID` in `.env` to the output of `id -u` on Linux so the worker has the same UID. Compose makes only this file available to the worker.
3. Your public key is on your clipboard (or in `~/.ssh/dbt_key.pub`) — paste it when prompted by your Snowflake admin (your teacher) to set up key pair authentication.

# ✅ Getting Airflow Started

## Configure the trusted SSH server keys

Obtain each server's public host key from your instructor or the server administrator via a trusted channel. In `.env`, set `SSH_HOST_KEY` for the MongoDB SSH tunnel and `SFTP_HOST_KEY` for SFTP. Use the key type and base64 data from the trusted OpenSSH public key, in quotes and without a hostname prefix. This is the server's public key, not your personal public or private key. If you do not use one service, its variable may remain blank; attempts to use that service will fail before connecting. If the server rotates its key, verify the replacement with the administrator before updating your pin.

## How to Build and Spin Up the Docker Container

1. Make sure the docker app is open on your machine
2. Open a new terminal in VS Code -> Terminal -> New Terminal
3. Run this code in the terminal
```bash
docker compose up --build -d
```
Note: you only run the `--build` flag the first time or if you change something in the Dockerfile or requirements.txt. After that you can just run `docker compose up -d`

4. Open [http://localhost:8080](http://localhost:8080)

Login with:
- **Username:** `airflow`
- **Password:** the unique value you set for `_AIRFLOW_WWW_USER_PASSWORD` on a fresh install.

## How to shut down docker
1. Run this in the terminal in VS Code
```bash
docker compose down
```

## Docker container troubleshooting
### Stop everything and remove containers + volumes for this project
1. This will stop all running containers, remove the containers, and delete any associated volumes for this project.
```bash
docker compose down --volumes --remove-orphans
```

### The worker cannot read the Snowflake private key

Set `SNOWFLAKE_KEY_HOST_PATH` to the dedicated private key **file** on the host. Do not point to the whole SSH directory. `HOST_USERNAME` and your old `SNOWFLAKE_PRIVATE_KEY_PATH` settings are not needed in the Compose setup. Do not put a base64 copy of the key in the shared `.env`. If the file has a passphrase, set `SNOWFLAKE_PRIVATE_KEY_PASSPHRASE` locally.

Check readability without displaying or copying the key:

```bash
docker compose exec airflow-worker test -r /run/secrets/snowflake_private_key
```

If it is not readable, check the host path, Docker Desktop file sharing settings, and the host file's ownership. On Linux, set `AIRFLOW_UID` to your host UID. Keep the key readable only to its owner (`chmod 600` on Unix); do not broaden access to make the container work. Recreate the worker after changing mount settings.

### DAG runs stuck "Running" or repeatedly retrying on first startup
Symptom: shortly after `docker compose up`, the `starter_dag` (or any DAG) shows many DAG runs queued up at once, the first task (e.g. `extract_activity`) is stuck "Running" through multiple retries, and the Docker stack feels sluggish or unresponsive.

Cause: Airflow is **backfilling**. If a DAG has `catchup=True` and a `start_date` that's weeks or months in the past, the scheduler enqueues one run for *every* missed schedule interval between `start_date` and today. For a `@daily` schedule that's 100+ concurrent runs hitting the same API on a single-laptop Docker setup, which throttles the worker and causes timeouts and retries.

Fix: in your DAG file (e.g. [dags/starter_dag.py](dags/starter_dag.py) around lines 28–30), either:
1. Set `catchup=False` — recommended for most student DAGs; you don't need historical backfills, and
2. Move `start_date` forward to a recent date (e.g. yesterday or a few days ago).

After editing, save the file, then in the Airflow UI go to the DAG → **Browse → DAG Runs** and delete any queued/stuck runs. New runs will follow the updated config.

## Snowflake troubleshooting
### `Table '...' does not exist` when the DAG tries to load
Symptom: the Snowflake connection opens fine but the load step fails with `SQL compilation error: Table 'PROJECT_DB.RAW.STARTER_DAG_<NAME>' does not exist`.

Cause: `write_pandas` is called with `auto_create_table=False`, so the target table must already exist in Snowflake before the DAG runs. Each student is responsible for creating their own table once.

Fix: run the `CREATE TABLE IF NOT EXISTS` DDL from the comment block in your DAG file (e.g. [dags/starter_dag.py](dags/starter_dag.py)) against your table name. **Run it in a SQL worksheet or a SQL cell — not a Python cell.** A Snowsight notebook cell defaults to Python, and pasting SQL into a Python cell will throw `SyntaxError: invalid syntax` at the word `CREATE`. To change cell language, click the `Python` dropdown at the top-left of the cell and switch to `SQL`, or open a plain SQL Worksheet from the left nav.

Verify the table exists after creating:
```sql
SHOW TABLES LIKE 'STARTER_DAG_<YOUR_NAME>' IN SCHEMA PROJECT_DB.RAW;
```
