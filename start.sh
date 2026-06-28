#!/bin/bash
set -e

echo "=== MotoTaxi Startup ==="
PORT="${PORT:-5000}"
echo "PORT=$PORT"
echo "DATABASE_URL=${DATABASE_URL:0:50}..."

echo "--- Running migration ---"
python migrate.py
echo "--- Migration done ---"

echo "--- Starting server ---"
exec waitress-serve --bind=0.0.0.0:$PORT backend.app:app
