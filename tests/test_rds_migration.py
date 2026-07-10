import subprocess
import sys


def test_skip_source_snapshot_requires_existing_id():
    result = subprocess.run(
        [
            sys.executable,
            "scripts/rds_region_migration.py",
            "--source-region",
            "ap-southeast-1",
            "--target-region",
            "ap-southeast-2",
            "--db-instance-identifier",
            "filebackup-db",
            "--target-db-instance-identifier",
            "filebackup-db-sydney",
            "--subnet-group",
            "subnet-group",
            "--security-group-ids",
            "sg-123",
            "--skip-source-snapshot",
        ],
        cwd=".",
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "--existing-snapshot-id" in result.stderr
