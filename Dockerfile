FROM python:3.12-slim

WORKDIR /app

# System deps — cached unless this block changes
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

# PyTorch CPU-only wheel (~200 MB vs ~800 MB with CUDA)
# Installed separately so it stays cached even when other deps change
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Install remaining dependencies
# Stub out the package so pip can resolve deps without the real source
COPY pyproject.toml .
RUN mkdir -p src/mm_forum && touch src/mm_forum/__init__.py && \
    pip install --no-cache-dir ".[app]"

# Copy real source and reinstall the package (no-deps = reuse cached deps above)
COPY src/ src/
RUN pip install --no-cache-dir --no-deps .
COPY alembic.ini .
COPY scripts/ scripts/
COPY app/ app/

EXPOSE 8501
