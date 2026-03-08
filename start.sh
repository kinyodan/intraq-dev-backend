#!/usr/bin/env bash
set -e

echo "========================================"
echo "Starting Celery worker in background..."
echo "========================================"

# Start Celery worker
# IMPORTANT: Change -A app.celery to match YOUR actual Celery app location
# Examples:
#   -A app.celery           if celery_app is defined in app/celery.py
#   -A main.celery_app      if defined in main.py
#   -A app.tasks            if defined in app/tasks/__init__.py
celery -A main.celery_app.celery worker --loglevel=info --concurrency=1 --max-tasks-per-child=50 &

# Give worker 3–5 seconds to connect and log startup (adjust if needed)
sleep 5

echo "========================================"
echo "Starting FastAPI (Uvicorn)..."
echo "========================================"

# Run FastAPI in foreground (Render requires this process to stay alive)
exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2