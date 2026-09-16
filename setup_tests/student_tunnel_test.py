#%% start_mongo_tunnel.py
import os
from dotenv import load_dotenv
from sshtunnel import SSHTunnelForwarder
import time
from pathlib import Path

load_dotenv(Path(__file__).parent / 'student.env')

# SSH credentials
SSH_HOST = os.getenv("SSH_HOST")
SSH_PORT = int(os.getenv("SSH_PORT"))
SSH_USER = os.getenv("SSH_USER")
SSH_PASSWORD = os.getenv("SSH_PASSWORD")

# MongoDB credentials
MONGO_HOST = os.getenv("MONGO_HOST")
MONGO_PORT = int(os.getenv("MONGO_PORT"))

tunnel = SSHTunnelForwarder(
    (SSH_HOST, SSH_PORT),
    ssh_username=SSH_USER,
    ssh_password=SSH_PASSWORD,
    remote_bind_address=(MONGO_HOST, MONGO_PORT),
    local_bind_address=('127.0.0.1', 27017)
)

tunnel.start()
print(f"Tunnel running on port {tunnel.local_bind_port}. Press Ctrl+C to stop.")
try:
    while True:
        time.sleep(10)
except KeyboardInterrupt:
    print("Shutting down tunnel...")
    tunnel.stop()
# %%
