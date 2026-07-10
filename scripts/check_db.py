#!/usr/bin/env python3
"""Test RDS connectivity before starting the app. Run inside the container."""
import os
import sys

import pyodbc


def main() -> int:
    host = os.environ.get("DB_HOST", "")
    port = os.environ.get("DB_PORT", "1433")
    user = os.environ.get("DB_USER", "")
    password = os.environ.get("DB_PASSWORD", "")
    database = os.environ.get("DB_NAME", "master")

    missing = [k for k, v in {
        "DB_HOST": host, "DB_USER": user, "DB_PASSWORD": password,
    }.items() if not v]
    if missing:
        print(f"FAIL: missing env vars: {', '.join(missing)}", file=sys.stderr)
        return 1

    cs = (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={host},{port};"
        f"DATABASE=master;"
        f"UID={user};"
        f"PWD={password};"
        "Encrypt=yes;"
        "TrustServerCertificate=yes;"
    )
    print(f"Checking RDS login: {user}@{host}:{port}")
    try:
        conn = pyodbc.connect(cs, timeout=15)
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        cur.execute("SELECT DB_ID(?)", database)
        row = cur.fetchone()
        if row[0] is None:
            print(f"Database '{database}' does not exist yet (app will create it)")
        else:
            print(f"Database '{database}' exists")
        conn.close()
    except pyodbc.Error as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        print(
            "Hint: verify DB_PASSWORD in .env matches the RDS master password. "
            "Reset it in AWS RDS console if needed.",
            file=sys.stderr,
        )
        return 1

    print("OK: RDS connection verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
