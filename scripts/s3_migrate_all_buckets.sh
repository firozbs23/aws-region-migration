#!/usr/bin/env bash
# Runs s3_region_migration.sh across the three category buckets in
# parallel. Bucket names: myco-file-backup-<category>-<region-suffix>.
# Usage: ./scripts/s3_migrate_all_buckets.sh warm|final|verify|create-dest \
#            <source-region> <source-suffix> <dest-region> <dest-suffix>

set -euo pipefail

MODE="${1:-}"
SRC_REGION="${2:-}"
SRC_SUFFIX="${3:-}"
DST_REGION="${4:-}"
DST_SUFFIX="${5:-}"

usage() {
  echo "Usage: $0 {warm|final|verify|create-dest} <source-region> <source-suffix> <dest-region> <dest-suffix>"
  echo "Example: $0 warm ap-southeast-1 sg ap-southeast-2 sydney"
  exit 1
}

[ -z "${DST_SUFFIX:-}" ] && usage

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CATEGORIES=(documents media archives)

pids=()
for category in "${CATEGORIES[@]}"; do
  src_bucket="myco-file-backup-${category}-${SRC_SUFFIX}"
  dst_bucket="myco-file-backup-${category}-${DST_SUFFIX}"
  echo "=== ${category}: ${src_bucket} -> ${dst_bucket} ==="
  "${SCRIPT_DIR}/s3_region_migration.sh" "$MODE" "$src_bucket" "$SRC_REGION" "$dst_bucket" "$DST_REGION" &
  pids+=($!)
done

status=0
for pid in "${pids[@]}"; do
  wait "$pid" || status=1
done

if [ "$status" -ne 0 ]; then
  echo "One or more bucket transfers failed -- check output above." >&2
  exit 1
fi
echo "All three buckets: $MODE complete."
