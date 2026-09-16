#%%
import os
import time
import logging
from dotenv import load_dotenv
import paramiko

## you may need to install these packages in your environment:
# pip install paramiko==3.5.1 python-dotenv sshtunnel==0.4.0

# Load env
load_dotenv("../.env")

SFTP_HOST = os.getenv("SFTP_HOST")
SFTP_PORT = int(os.getenv("SFTP_PORT"))
# SFTP_PORT = 219
SFTP_USER = os.getenv("SFTP_USER")
SFTP_PASSWORD = os.getenv("SFTP_PASSWORD")
SFTP_DIR = os.getenv("SFTP_DIR")
LOCAL_FILE = "example.csv"
REMOTE_FILE = "AAPL_2025-01-01.csv"

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s"
)
logger = logging.getLogger(__name__)

def download_file():
    try:
        logger.info("Connecting to SFTP…")
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(SFTP_HOST, port=SFTP_PORT, username=SFTP_USER, password=SFTP_PASSWORD)
        logger.info("✅ SSH connection established.")

        sftp = ssh.open_sftp()
        logger.info("✅ SFTP session established.")

        # Check if SFTP_DIR exists
        try:
            sftp.listdir(SFTP_DIR)
            logger.info(f"📂 Remote directory exists: {SFTP_DIR}")
        except IOError:
            logger.error(f"❌ Remote directory does not exist: {SFTP_DIR}")
            return

        # Download one file from the 2025-01-01 folder to verify with AAPL_2026-01-01.csv
        remote_path = f"{SFTP_DIR}/2025-01-01/{os.path.basename(REMOTE_FILE)}"
        logger.info(f"⬇️ Downloading back to verify upload: {remote_path}")
        # Ensure the local directory exists before downloading
        local_dir = "sftp_downloads"
        os.makedirs(local_dir, exist_ok=True)
        local_path = os.path.join(local_dir, os.path.basename(REMOTE_FILE))
        sftp.get(remote_path, local_path)
        logger.info("✅ Download completed for verification.")

        # Verify downloaded file size
        # downloaded_size = os.path.getsize(local_path +os.path.basename(REMOTE_FILE))
        downloaded_size = os.path.getsize(local_path)
        remote_size = sftp.stat(remote_path).st_size
        if downloaded_size == remote_size:
            logger.info(f"✅ Download verified: {downloaded_size} bytes.")
        else:
            logger.warning(f"⚠️ Size mismatch: downloaded {downloaded_size} vs remote {remote_size}")

        sftp.close()
        ssh.close()
        logger.info("🔒 Connection closed.")

    except Exception as e:
        logger.error(f"❌ SFTP session failed: {e}")
        raise

# Retry logic
for attempt in range(2):
    try:
        download_file()
        break
    except Exception as e:
        if attempt == 0:
            logger.warning("🔄 Retrying in 3 seconds…")
            time.sleep(3)
        else:
            logger.error("❌ Failed to upload after retries.")

#%%