### Testing MongoDB Integration
This document outlines the steps to test the MongoDB integration within the Apache Airflow environment. Follow the instructions below to set up and run the tests successfully.

#### Prerequisites
- Fill in the following credentials in you `.env` file:
  - `SSH_USER`
  - `SSH_PASSWORD`
  - `SSH_HOST`
  - `SSH_HOST_KEY` (the trusted server public key supplied by your instructor)
  - `SSH_PORT`
  - `MONGO_HOST`
  - `MONGO_PORT`

#### Steps to Test MongoDB Integration
1. **Open New Terminal Window**: Start by opening a new terminal window on your local machine.
2. **Copy Paste Command**: Copy and paste the following command into your terminal to execute the MongoDB test script locally from the repository root:
   ```bash
    python setup_tests/student_tunnel_test.py
   ```
3. **Review Output**: After executing the command, review the output in the terminal to verify that the MongoDB integration is functioning as expected. It will display **"Tunnel running on port 27017."** if the connection is successful.
