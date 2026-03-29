FROM python:3.12-slim

WORKDIR /app

# Install system deps needed by psycopg2, lxml, etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python package with all extras
COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir ".[app]"

# Copy application code
COPY scripts/ scripts/
COPY app/ app/

EXPOSE 8501
