#!/usr/bin/env bash
#
# Cross-region S3 bucket migration: create-dest, warm sync (repeatable,
# pre-cutover), final sync (post-cutover, catches deltas), verify (object
# count/size match). See doc/POC.pdf "Region Migration Runbook".
#
# Usage: ./scripts/s3_region_migration.sh {warm|final|verify|create-dest} \
#            <source-bucket> <source-region> <dest-bucket> <dest-region>
set -euo pipefail

MODE="${1:-}"
SRC_BUCKET="${2:-}"
SRC_REGION="${3:-}"
DST_BUCKET="${4:-}"
DST_REGION="${5:-}"

usage() {
  echo "Usage: $0 {warm|final|verify|create-dest} <source-bucket> <source-region> <dest-bucket> <dest-region>"
  exit 1
}

[ -z "$MODE" ] && usage

case "$MODE" in
  create-dest)
    [ -z "${DST_REGION:-}" ] && usage
    echo "Creating destination bucket '$DST_BUCKET' in $DST_REGION ..."
    aws s3api create-bucket \
      --bucket "$DST_BUCKET" \
      --region "$DST_REGION" \
      --create-bucket-configuration LocationConstraint="$DST_REGION"
    aws s3api put-public-access-block \
      --bucket "$DST_BUCKET" --region "$DST_REGION" \
      --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
    echo "Done. Bucket '$DST_BUCKET' created with public access blocked. (Versioning intentionally left off -- see doc/POC.pdf Section 3.3.)"
    ;;

  warm|final)
    [ -z "${DST_REGION:-}" ] && usage
    echo "[$MODE sync] $SRC_BUCKET ($SRC_REGION) -> $DST_BUCKET ($DST_REGION)"
    # --source-region: bucket owning the source objects
    # --region: applies to the destination bucket
    aws s3 sync "s3://${SRC_BUCKET}" "s3://${DST_BUCKET}" \
      --source-region "$SRC_REGION" \
      --region "$DST_REGION" \
      --only-show-errors
    echo "[$MODE sync] complete."
    ;;

  verify)
    [ -z "${DST_REGION:-}" ] && usage
    SRC_COUNT=$(aws s3 ls "s3://${SRC_BUCKET}" --recursive --region "$SRC_REGION" | wc -l)
    DST_COUNT=$(aws s3 ls "s3://${DST_BUCKET}" --recursive --region "$DST_REGION" | wc -l)
    SRC_SIZE=$(aws s3 ls "s3://${SRC_BUCKET}" --recursive --region "$SRC_REGION" | awk '{sum+=$3} END {print sum}')
    DST_SIZE=$(aws s3 ls "s3://${DST_BUCKET}" --recursive --region "$DST_REGION" | awk '{sum+=$3} END {print sum}')
    echo "Source: $SRC_COUNT objects, ${SRC_SIZE:-0} bytes"
    echo "Dest:   $DST_COUNT objects, ${DST_SIZE:-0} bytes"
    if [ "$SRC_COUNT" == "$DST_COUNT" ] && [ "${SRC_SIZE:-0}" == "${DST_SIZE:-0}" ]; then
      echo "OK: object count and total size match."
    else
      echo "MISMATCH: re-run '$0 final ...' before cutting over." >&2
      exit 2
    fi
    ;;

  *)
    usage
    ;;
esac
