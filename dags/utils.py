import pandas as pd
import re
import snowflake.connector
from dotenv import load_dotenv
import os
import pymongo
import sshtunnel
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
import base64
import logging
from sshtunnel import SSHTunnelForwarder
from pymongo import MongoClient
import stat
import paramiko

# -------------------------------------------------------------------
# Utility Functions
# -------------------------------------------------------------------
load_dotenv()

# -------------------------------------------------------------------
# S&P 500 Tickers
# -------------------------------------------------------------------
def get_sp500_tickers() -> list[str]:
    """
    Fetches the current list of S&P 500 tickers from Wikipedia.
    """
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    # Add a User-Agent so Wikipedia doesn't block the request
    dfs = pd.read_html(
        url,
        match="Symbol",
        storage_options={"User-Agent": "Mozilla/5.0"}
    )
    df = dfs[0]

    tickers = (
        df["Symbol"]
        .astype(str)
        .str.strip()
        .dropna()
        .drop_duplicates()
        .apply(lambda t: re.sub(r"\.", "-", t))  # Replace dots with dashes
        .sort_values()  # Sort alphabetically
        .tolist()
    )
    return tickers

# -------------------------------------------------------------------
# Snowflake_keypair
# -------------------------------------------------------------------
def get_snowflake_connection(schema: str = None):
    """
    Connect to Snowflake using ONLY key-pair authentication.
    Requires one of:
      - SNOWFLAKE_PRIVATE_KEY_PATH
      - SNOWFLAKE_PRIVATE_KEY_B64
    Optional:
      - SNOWFLAKE_PRIVATE_KEY_PASSPHRASE
    """
    common = dict(
        user=os.getenv("SNOWFLAKE_USER"),
        account=os.getenv("SNOWFLAKE_ACCOUNT"),
        role=os.getenv("SNOWFLAKE_ROLE"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "STUDENT_WH"),
        database=os.getenv("SNOWFLAKE_DATABASE", "PROJECT_DB"),
        schema=schema or os.getenv("SNOWFLAKE_SCHEMA", "RAW"),
    )

    key_path = os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH")
    key_b64  = os.getenv("SNOWFLAKE_PRIVATE_KEY_B64")
    key_pass = os.getenv("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE")

    if not key_path and not key_b64:
        raise ValueError(
            "❌ Must set SNOWFLAKE_PRIVATE_KEY_PATH or SNOWFLAKE_PRIVATE_KEY_B64 in environment"
        )

    if key_path:
        with open(key_path, "rb") as f:
            key_pem = f.read()
    else:
        key_pem = base64.b64decode(key_b64)

    private_key = serialization.load_pem_private_key(
        key_pem,
        password=(key_pass.encode() if key_pass else None),
        backend=default_backend(),
    ).private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    return snowflake.connector.connect(private_key=private_key, **common)

# -------------------------------------------------------------------
# MongoDB
# -------------------------------------------------------------------
def get_mongo_client(local_port=None):
    """
    Returns a MongoDB client.
    - If using SSH tunnel, pass tunnel.local_bind_port as local_port.
    - If connecting directly, env vars are used.
    """
    from urllib.parse import quote_plus
    host = "127.0.0.1" if local_port else os.getenv("MONGO_HOST")
    port = local_port or int(os.getenv("MONGO_PORT", 27017))
    user = os.getenv("MONGO_USER")
    password = quote_plus(os.getenv("MONGO_PASSWORD"))  # URL-encode the password
    auth_db = os.getenv("MONGO_DB", "admin")

    uri = f"mongodb://{user}:{password}@{host}:{port}/{auth_db}"
    return pymongo.MongoClient(uri)

def get_mongo_collection(client):
    """
    Returns the default MongoDB collection based on env vars.
    """
    db_name = os.getenv("MONGO_DB")
    collection_name = os.getenv("MONGO_COLLECTION")
    return client[db_name][collection_name]


# ---------------------------------------------------------
# SSH Tunnel to MongoDB
# ---------------------------------------------------------
def create_ssh_tunnel():
    """Start an SSH tunnel and return the tunnel object."""
    SSH_HOST = os.getenv("SSH_HOST")
    SSH_PORT = int(os.getenv("SSH_PORT"))
    SSH_USER = os.getenv("SSH_USER")
    SSH_PASSWORD = os.getenv("SSH_PASSWORD")
    MONGO_HOST = os.getenv("MONGO_HOST")
    MONGO_PORT = int(os.getenv("MONGO_PORT"))

    logging.info("Starting SSH tunnel to MongoDB...")
    tunnel = SSHTunnelForwarder(
        (SSH_HOST, SSH_PORT),
        ssh_username=SSH_USER,
        ssh_password=SSH_PASSWORD,
        remote_bind_address=(MONGO_HOST, MONGO_PORT),
        local_bind_address=("127.0.0.1", 27017)
    )
    tunnel.start()
    logging.info(f"SSH tunnel established on local port {tunnel.local_bind_port}")
    return tunnel

# ---------------------------------------------------------
# Weather Record Builder
# ---------------------------------------------------------

def build_weather_record(weather_dict, target_date, city):
    """Extract weather metrics safely from API response."""
    daily_data = weather_dict.get("daily", {})
    return {
        "date": target_date,
        "city": city,
        "max_temp": daily_data.get("temperature_2m_max", [None])[0],
        "min_temp": daily_data.get("temperature_2m_min", [None])[0],
        "precip": daily_data.get("precipitation_sum", [None])[0],
        "max_wind": daily_data.get("windspeed_10m_max", [None])[0],
    }

# ---------------------------------------------------------
# Snowflake MERGE SQL Builder
# ---------------------------------------------------------

def build_merge_sql(rec, table):
    """Return a parameterized Snowflake MERGE statement."""
    return f"""
        MERGE INTO {table} t
        USING (SELECT
            '{rec["date"]}' AS DATE,
            '{rec["city"]}' AS CITY,
            {rec["max_temp"] if rec["max_temp"] is not None else 'NULL'} AS MAX_TEMP,
            {rec["min_temp"] if rec["min_temp"] is not None else 'NULL'} AS MIN_TEMP,
            {rec["max_wind"] if rec["max_wind"] is not None else 'NULL'} AS MAX_WIND,
            {rec["precip"] if rec["precip"] is not None else 'NULL'} AS PRECIP
        ) s
        ON t.DATE = s.DATE AND t.CITY = s.CITY
        WHEN MATCHED THEN UPDATE SET
            MAX_TEMP = s.MAX_TEMP,
            MIN_TEMP = s.MIN_TEMP,
            MAX_WIND = s.MAX_WIND,
            PRECIP   = s.PRECIP
        WHEN NOT MATCHED THEN INSERT
            (DATE, CITY, MAX_TEMP, MIN_TEMP, MAX_WIND, PRECIP)
        VALUES
            (s.DATE, s.CITY, s.MAX_TEMP, s.MIN_TEMP, s.MAX_WIND, s.PRECIP);
    """

# ---------------------------------------------------------------
# SFTP Helper Utilities for Airflow DAGs
# ---------------------------------------------------------------

def create_sftp_connection():
    """
    Establish an SFTP connection using username/password from .env.
    Returns a live paramiko SFTP client.
    """
    host = os.getenv("SFTP_HOST")
    port = int(os.getenv("SFTP_PORT", 22))
    username = os.getenv("SFTP_USER")
    password = os.getenv("SFTP_PASSWORD")

    try:
        transport = paramiko.Transport((host, port))
        transport.connect(username=username, password=password)
        sftp = paramiko.SFTPClient.from_transport(transport)
        logging.info(f"✅ Connected to SFTP: {host}")
        return sftp
    except Exception as e:
        logging.error(f"❌ Failed to connect to SFTP: {e}")
        raise

def is_directory(sftp, path):
    """Check if a given SFTP path is a directory."""
    try:
        return stat.S_ISDIR(sftp.stat(path).st_mode)
    except IOError:
        return False

def list_folders(sftp):
    """Return list of top-level folders on SFTP."""
    try:
        folders = [f for f in sftp.listdir() if is_directory(sftp, f)]
        logging.info(f"📂 Found {len(folders)} folders on SFTP.")
        return folders
    except Exception as e:
        logging.error(f"Error listing folders: {e}")
        return []

def list_files(sftp, folder):
    """Return list of files within a given folder."""
    try:
        sftp.chdir(folder)
        files = [f for f in sftp.listdir() if not is_directory(sftp, f)]
        logging.info(f"🧾 Found {len(files)} files in {folder}")
        return files
    except Exception as e:
        logging.error(f"Error listing files in {folder}: {e}")
        return []

def read_file_from_sftp(sftp, folder, filename):
    """Read a file from SFTP and return its content as text."""
    try:
        remote_path = os.path.join(folder, filename)
        with sftp.open(remote_path, "r") as f:
            content = f.read().decode("utf-8")
        return content
    except Exception as e:
        logging.error(f"Error reading {filename}: {e}")
        raise


def save_dataframe(df, filepath):
    """Save a pandas DataFrame to CSV."""
    df.to_csv(filepath, index=False)
    logging.info(f"💾 Saved DataFrame to {filepath}")
