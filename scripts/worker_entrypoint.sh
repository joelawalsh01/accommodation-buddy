#!/bin/bash
set -e

echo "Starting Celery worker..."
exec uv run celery -A accommodation_buddy.tasks.celery_app worker \
    --loglevel=info --concurrency=2
