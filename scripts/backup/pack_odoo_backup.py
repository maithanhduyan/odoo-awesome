"""Package SQL dump + filestore into Odoo-compatible backup ZIP.

Odoo backup format (.zip):
  - dump.sql          : PostgreSQL plain SQL dump
  - filestore/        : attachment files
  - manifest.json     : backup metadata

Usage:
    python scripts/pack_odoo_backup.py
    python scripts/pack_odoo_backup.py --sql backup/dump.sql --filestore backup/filestore.tar.gz --db taya15_db
"""

import argparse
import gzip
import json
import os
import sys
import tarfile
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent


def create_manifest(db_name: str, odoo_version: str = "15.0"):
    """Create Odoo backup manifest."""
    return {
        "odoo_dump": "1",
        "db_name": db_name,
        "version": odoo_version,
        "version_info": [int(odoo_version.split(".")[0]), 0, 0, "final", 0],
        "major_version": odoo_version,
        "pg_version": "14.0",
        "modules": {},
        "manifest_version": "2",
        "env": "production",
        "create_date": datetime.now().isoformat(),
    }


def pack_backup(sql_path: Path, filestore_path: Path, output_path: Path, db_name: str, odoo_version: str):
    """Pack SQL + filestore into Odoo backup ZIP."""

    sql_size = sql_path.stat().st_size / (1024 * 1024)
    fs_size = filestore_path.stat().st_size / (1024 * 1024)

    print("=" * 50)
    print("  Pack Odoo Backup")
    print("=" * 50)
    print(f"  SQL dump   : {sql_path.name} ({sql_size:.1f} MB)")
    print(f"  Filestore  : {filestore_path.name} ({fs_size:.1f} MB)")
    print(f"  Database   : {db_name}")
    print(f"  Version    : {odoo_version}")
    print(f"  Output     : {output_path}")
    print("=" * 50)

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. Add manifest.json
        print("\n[1/3] Writing manifest.json...")
        manifest = create_manifest(db_name, odoo_version)
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))

        # 2. Add dump.sql
        print(f"[2/3] Adding dump.sql ({sql_size:.1f} MB)...")
        zf.write(sql_path, "dump.sql")

        # 3. Extract filestore tar.gz and add to zip
        print(f"[3/3] Extracting and adding filestore ({fs_size:.1f} MB)...")
        file_count = 0

        # Handle both .tar.gz and .gz formats
        with tarfile.open(filestore_path, "r:gz") as tar:
            members = tar.getmembers()
            for member in members:
                if member.isfile():
                    f = tar.extractfile(member)
                    if f:
                        # Normalize path: ensure it's under filestore/
                        name = member.name
                        # Strip leading directory if it exists (e.g., "filestore/xxx" or "xxx")
                        if name.startswith("filestore/"):
                            arcname = name
                        else:
                            arcname = f"filestore/{name}"

                        zf.writestr(arcname, f.read())
                        file_count += 1

                        if file_count % 500 == 0:
                            print(f"    ... {file_count} files added")

    output_size = output_path.stat().st_size / (1024 * 1024)
    print()
    print("=" * 50)
    print(f"  Backup created: {output_path}")
    print(f"  Size: {output_size:.1f} MB")
    print(f"  Files in filestore: {file_count}")
    print("=" * 50)


def main():
    parser = argparse.ArgumentParser(description="Pack SQL dump + filestore into Odoo backup ZIP")
    parser.add_argument("--sql", help="Path to .sql dump file")
    parser.add_argument("--filestore", help="Path to filestore .tar.gz")
    parser.add_argument("--output", "-o", help="Output .zip path")
    parser.add_argument("--db", default="taya15_db", help="Database name (default: taya15_db)")
    parser.add_argument("--version", default="15.0", help="Odoo version (default: 15.0)")
    args = parser.parse_args()

    backup_dir = Path(r"E:\Project\odoo-tayafood\odoo-15\backup")

    # Default paths
    sql_path = Path(args.sql) if args.sql else backup_dir / "taya_db_2026-04-03_02-36-00.sql"
    fs_path = Path(args.filestore) if args.filestore else backup_dir / "taya_db_filestore_2026-04-03_02-00-01.tar.gz"

    if not sql_path.exists():
        print(f"ERROR: SQL file not found: {sql_path}")
        sys.exit(1)
    if not fs_path.exists():
        print(f"ERROR: Filestore archive not found: {fs_path}")
        sys.exit(1)

    if args.output:
        output_path = Path(args.output)
    else:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_path = backup_dir / f"{args.db}_{timestamp}.zip"

    pack_backup(sql_path, fs_path, output_path, args.db, args.version)


if __name__ == "__main__":
    main()
