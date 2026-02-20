FROM python:3.11-slim

WORKDIR /app

# Lightweight system dependencies for API/beat/flower
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    netcat-traditional \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . /app

# Default command (overridden by docker-compose for each service)
CMD ["uvicorn", "app.console.main:app", "--host", "0.0.0.0", "--port", "8000"]
