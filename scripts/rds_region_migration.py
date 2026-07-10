#!/usr/bin/env python3
"""
Cross-region RDS migration: snapshot the source, copy the snapshot
cross-region, restore a new instance from it, print the new endpoint.
Engine-agnostic (same API for SQL Server/PostgreSQL/MySQL). Non-destructive:
never modifies or deletes the source; decommissioning is a separate manual
step after the cutover is verified (doc/POC.pdf "Region Migration Runbook").

Usage:
    python scripts/rds_region_migration.py \\
        --source-region ap-southeast-1 \\
        --target-region ap-southeast-2 \\
        --db-instance-identifier filebackup-db \\
        --target-db-instance-identifier filebackup-db-sydney \\
        --db-instance-class db.t3.small \\
        --kms-key-id <target-region-kms-key-arn>   # omit if source is unencrypted

Requires AWS credentials with rds:CreateDBSnapshot, rds:CopyDBSnapshot,
rds:RestoreDBInstanceFromDBSnapshot, and rds:Describe* in both regions.
"""
import argparse
import sys
import time
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def wait_for_snapshot(client, snapshot_id: str, poll_seconds: int = 30) -> None:
    while True:
        resp = client.describe_db_snapshots(DBSnapshotIdentifier=snapshot_id)
        snap = resp["DBSnapshots"][0]
        status = snap["Status"]
        pct = snap.get("PercentProgress", 0)
        log(f"  snapshot '{snapshot_id}' status={status} progress={pct}%")
        if status == "available":
            return
        if status in ("failed", "incompatible-restore", "incompatible-network"):
            raise RuntimeError(f"Snapshot {snapshot_id} entered terminal failure state: {status}")
        time.sleep(poll_seconds)


def wait_for_instance(client, instance_id: str, poll_seconds: int = 30) -> dict:
    while True:
        resp = client.describe_db_instances(DBInstanceIdentifier=instance_id)
        inst = resp["DBInstances"][0]
        status = inst["DBInstanceStatus"]
        log(f"  instance '{instance_id}' status={status}")
        if status == "available":
            return inst
        if status in ("failed", "incompatible-restore"):
            raise RuntimeError(f"Instance {instance_id} entered terminal failure state: {status}")
        time.sleep(poll_seconds)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source-region", required=True, help="e.g. ap-southeast-1 (Singapore)")
    p.add_argument("--target-region", required=True, help="e.g. ap-southeast-2 (Sydney)")
    p.add_argument("--db-instance-identifier", required=True, help="Source RDS instance identifier")
    p.add_argument("--target-db-instance-identifier", required=True, help="Name for the new instance in the target region")
    p.add_argument("--db-instance-class", default="db.t3.small", help="Instance class for the restored instance (verify orderable for your engine/region first)")
    p.add_argument("--subnet-group", required=True, help="DB subnet group name that already exists in the target region")
    p.add_argument("--security-group-ids", nargs="+", required=True, help="VPC security group id(s) in the target region")
    p.add_argument("--kms-key-id", default=None, help="KMS key ARN in the TARGET region, required only if the source DB is encrypted")
    p.add_argument("--multi-az", action="store_true", help="Provision the restored instance as Multi-AZ (recommended for production, not POC)")
    p.add_argument("--skip-source-snapshot", action="store_true", help="Skip step 1 and reuse an existing snapshot via --existing-snapshot-id")
    p.add_argument("--existing-snapshot-id", default=None, help="Reuse this existing source-region snapshot instead of creating a new one")
    args = p.parse_args()

    if args.skip_source_snapshot and not args.existing_snapshot_id:
        p.error("--skip-source-snapshot requires --existing-snapshot-id")

    source_client = boto3.client("rds", region_name=args.source_region)
    target_client = boto3.client("rds", region_name=args.target_region)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    source_snapshot_id = args.existing_snapshot_id or f"{args.db_instance_identifier}-migration-{timestamp}"
    copied_snapshot_id = f"{source_snapshot_id}-{args.target_region}"

    # ---- Step 1: snapshot the source instance ----
    if not args.skip_source_snapshot and not args.existing_snapshot_id:
        log(f"Step 1/4: creating snapshot '{source_snapshot_id}' of '{args.db_instance_identifier}' in {args.source_region}")
        source_client.create_db_snapshot(
            DBSnapshotIdentifier=source_snapshot_id,
            DBInstanceIdentifier=args.db_instance_identifier,
        )
        wait_for_snapshot(source_client, source_snapshot_id)
    else:
        log(f"Step 1/4: reusing existing snapshot '{source_snapshot_id}'")

    # ---- Step 2: copy snapshot cross-region ----
    log(f"Step 2/4: copying snapshot to {args.target_region} as '{copied_snapshot_id}'")
    source_snapshot_arn = (
        f"arn:aws:rds:{args.source_region}:"
        f"{boto3.client('sts', region_name=args.source_region).get_caller_identity()['Account']}:"
        f"snapshot:{source_snapshot_id}"
    )
    copy_kwargs = dict(
        SourceDBSnapshotIdentifier=source_snapshot_arn,
        TargetDBSnapshotIdentifier=copied_snapshot_id,
        SourceRegion=args.source_region,
    )
    if args.kms_key_id:
        copy_kwargs["KmsKeyId"] = args.kms_key_id
    try:
        target_client.copy_db_snapshot(**copy_kwargs)
    except ClientError as exc:
        log(f"ERROR copying snapshot: {exc}")
        return 1
    wait_for_snapshot(target_client, copied_snapshot_id)

    # ---- Step 3: restore a new instance from the copied snapshot ----
    log(f"Step 3/4: restoring '{args.target_db_instance_identifier}' in {args.target_region}")
    target_client.restore_db_instance_from_db_snapshot(
        DBInstanceIdentifier=args.target_db_instance_identifier,
        DBSnapshotIdentifier=copied_snapshot_id,
        DBInstanceClass=args.db_instance_class,
        DBSubnetGroupName=args.subnet_group,
        VpcSecurityGroupIds=args.security_group_ids,
        MultiAZ=args.multi_az,
        PubliclyAccessible=False,
    )
    inst = wait_for_instance(target_client, args.target_db_instance_identifier)

    # ---- Step 4: report the new endpoint ----
    endpoint = inst["Endpoint"]["Address"]
    port = inst["Endpoint"]["Port"]
    log(f"Step 4/4: done. New RDS endpoint: {endpoint}:{port}")
    log("Next: update DB_HOST/DB_PASSWORD, restart the app, run the verification checklist.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
