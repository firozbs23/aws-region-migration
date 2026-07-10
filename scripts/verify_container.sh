#!/usr/bin/env bash
# Quick check that the running container has the pyodbc-based DB code (not pymssql).
set -euo pipefail

echo "==> database.py driver check"
docker compose exec file-server python3 -c "
from pathlib import Path
src = Path('/app/app/database.py').read_text()
if 'pymssql' in src:
    raise SystemExit('FAIL: container still has old pymssql code -- run: git pull && docker compose build --no-cache && docker compose up -d')
if 'pyodbc' not in src:
    raise SystemExit('FAIL: pyodbc not found in database.py')
print('OK: pyodbc code deployed')
"

echo "==> ODBC driver check"
docker compose exec file-server python3 -c "import pyodbc; print('OK: pyodbc', pyodbc.version)"

echo "==> env check (no secrets)"
docker compose exec file-server python3 -c "
import os
for k in ('DB_HOST', 'DB_USER', 'DB_NAME'):
    print(f'{k}={os.environ.get(k, \"MISSING\")}')
print('DB_PASSWORD=' + ('set' if os.environ.get('DB_PASSWORD') else 'MISSING'))
"
