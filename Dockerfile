# syntax=docker/dockerfile:1
#
# Multi-stage build: builder installs Python deps; runtime adds Microsoft's
# ODBC Driver 18 for SQL Server (AWS-recommended for RDS; pymssql/FreeTDS
# often fails TLS auth with misleading "login failed" errors).

FROM python:3.11-slim-bookworm AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --target=/deps -r requirements.txt

FROM python:3.11-slim-bookworm AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates gnupg unixodbc \
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
        | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" \
        > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y msodbcsql18 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PYTHONPATH=/deps \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
COPY --from=builder /deps /deps
COPY app ./app
COPY scripts/check_db.py scripts/check_aws.py scripts/docker-entrypoint.sh ./scripts/
RUN chmod +x /app/scripts/docker-entrypoint.sh \
    && useradd -u 65532 -r -M -s /usr/sbin/nologin appuser \
    && chown -R 65532:65532 /app /deps
USER 65532
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=5 \
    CMD ["python3", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"]

ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]
