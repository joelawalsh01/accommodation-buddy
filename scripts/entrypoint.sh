#!/bin/bash
set -e

echo "Running database migrations..."
uv run alembic upgrade head

echo "Starting Accommodation Buddy..."
exec uv run accommodation-buddy serve "$@"
