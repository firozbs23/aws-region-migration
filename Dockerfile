# syntax=docker/dockerfile:1
#
# Multi-stage: builder has a full Debian userland to install deps, then is
# discarded. Runtime is Google's distroless Python base (no shell, no
# package manager) matched to the same Python/Debian version as the builder.
# All deps (including pymssql) ship prebuilt wheels, so the builder needs no
# compiler either.

FROM python:3.11-slim-bookworm AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --target=/deps -r requirements.txt

FROM gcr.io/distroless/python3-debian12:nonroot AS runtime
# ":nonroot" already runs as uid/gid 65532, no shell, no setuid binaries.
WORKDIR /app
ENV PYTHONPATH=/deps \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
COPY --from=builder /deps /deps
COPY app ./app
EXPOSE 8000

# No curl/wget in distroless; the interpreter itself probes the process.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python3", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"]

ENTRYPOINT ["python3", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
