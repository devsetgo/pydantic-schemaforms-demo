# Use Python 3.14 
FROM python:3.14

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/

# Alembic migrations
COPY alembic.ini ./
COPY migrations/ ./migrations/
COPY scripts/docker_entrypoint.sh ./scripts/docker_entrypoint.sh
RUN chmod +x ./scripts/docker_entrypoint.sh

# Build-time migration smoke-test (uses a temp DB inside the image).
RUN ANALYTICS_DB_PATH=/tmp/alembic_smoke.db python -m alembic -c alembic.ini upgrade head \
    && rm -f /tmp/alembic_smoke.db

# Persist analytics DB in a volume by default.
VOLUME ["/data"]

# Expose the port the app runs on
EXPOSE 5000

# # Health check
# HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
#     CMD python -c "import requests; requests.get('http://localhost:5000/', timeout=5)"

# Run the application (includes runtime migrations).
CMD ["./scripts/docker_entrypoint.sh"]
