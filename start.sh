#!/bin/bash
set -e

echo "=== VAN Startup ==="
PORT="${PORT:-5000}"
echo "PORT=$PORT"
echo "DATABASE_URL=***"

echo "--- Running migrate.py ---"
python migrate.py || echo "⚠️  migrate.py falló, continúa de todos modos"
echo "--- migrate.py done ---"

echo "--- Starting server (app.py hará _ensure_columns) ---"
exec waitress-serve --listen=0.0.0.0:$PORT backend.app:app
