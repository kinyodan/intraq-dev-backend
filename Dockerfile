# Use slim but add required system dependencies for pandas/numpy
FROM python:3.11-slim

# Install system packages required by pandas/numpy/scipy etc.
# These are runtime dependencies (not build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    libglib2.0-0 \
    libsm6 \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Optional: If you use openpyxl for Excel files
# RUN apt-get update && apt-get install -y libxml2 libxslt1.1 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first for caching
COPY requirements.txt .

# Upgrade pip and install Python packages
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Use $PORT provided by Render, fallback to 8000 for local
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}