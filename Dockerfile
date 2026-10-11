FROM apache/airflow:3.3.1-python3.12

USER airflow
ARG AIRFLOW_VERSION=3.3.1
ARG PYTHON_VERSION=3.12

# Install ETL/database dependencies while keeping the Airflow version aligned with
# the image and official constraints to reduce dependency conflicts.
RUN pip install --no-cache-dir \
    --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt" \
    "apache-airflow==${AIRFLOW_VERSION}" \
    pandas numpy SQLAlchemy psycopg2-binary
