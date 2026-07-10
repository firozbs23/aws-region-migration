#!/bin/sh
set -e
python3 /app/scripts/check_db.py
python3 /app/scripts/check_aws.py
exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
