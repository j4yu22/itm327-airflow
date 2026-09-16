FROM apache/airflow:3.3.1

# Switch to root only for apt installs
USER root
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Switch back to airflow user before running pip
USER airflow

# Upgrade pip as airflow user
RUN pip install --no-cache-dir --upgrade pip

# Copy requirements and install them
# COPY requirements.txt /requirements.txt
ADD requirements.txt .
RUN pip install apache-airflow==${AIRFLOW_VERSION} -r requirements.txt
