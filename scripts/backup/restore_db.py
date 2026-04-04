"""Restore PostgreSQL backup to Railway database.

Usage:
    python scripts/restore_db.py
    python scripts/restore_db.py --file backup/taya_db_2026-04-03_02-36-00.sql
    python scripts/restore_db.py --drop-first
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent


def load_env():
    """Load .env file into a dict."""
    env_file = PROJECT_DIR / ".env"
    if not env_file.exists():
        print(f"ERROR: .env not found at {env_file}")
        sys.exit(1)

    env = {}
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            key, _, value = line.partition("=")
            if value:
                env[key.strip()] = value.strip()
    return env


def find_latest_backup():
    """Find the most recent .sql file in backup/ folder."""
    backup_dir = PROJECT_DIR / "backup"
    sql_files = sorted(backup_dir.glob("*.sql"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not sql_files:
        print(f"ERROR: No .sql files found in {backup_dir}")
        sys.exit(1)
    return sql_files[0]


def check_psql():
    """Check if psql is available."""
    try:
        subprocess.run(["psql", "--version"], capture_output=True, check=True)
    except FileNotFoundError:
        print("ERROR: psql not found. Install PostgreSQL client tools and add to PATH.")
        sys.exit(1)


def run_psql(host, port, user, password, database, *args):
    """Run psql command with connection params."""
    env = os.environ.copy()
    env["PGPASSWORD"] = password
    cmd = ["psql", "-h", host, "-p", port, "-U", user, "-d", database, *args]
    return subprocess.run(cmd, env=env, capture_output=True, text=True)


def test_connection(host, port, user, password, database):
    """Test database connection."""
    print("Testing connection...", end=" ", flush=True)
    result = run_psql(host, port, user, password, database, "-c", "SELECT version();")
    if result.returncode != 0:
        print("FAILED")
        print(result.stderr)
        sys.exit(1)
    print("OK")


def restore(host, port, user, password, database, sql_file, drop_first=False):
    """Restore .sql file to database."""
    file_size_mb = sql_file.stat().st_size / (1024 * 1024)

    print("=" * 44)
    print("  Railway PostgreSQL Restore")
    print("=" * 44)
    print(f"  Host     : {host}")
    print(f"  Port     : {port}")
    print(f"  Database : {database}")
    print(f"  User     : {user}")
    print(f"  File     : {sql_file}")
    print(f"  Size     : {file_size_mb:.1f} MB")
    print("=" * 44)

    check_psql()
    test_connection(host, port, user, password, database)

    confirm = input(f"\nRestore '{sql_file.name}' to '{database}'? (y/N): ").strip().lower()
    if confirm != "y":
        print("Cancelled.")
        return

    env = os.environ.copy()
    env["PGPASSWORD"] = password

    # Drop and recreate if requested
    if drop_first:
        print(f"\nDropping and recreating database '{database}'...")
        for sql in [
            f'DROP DATABASE IF EXISTS "{database}";',
            f'CREATE DATABASE "{database}" OWNER "{user}";',
        ]:
            result = subprocess.run(
                ["psql", "-h", host, "-p", port, "-U", user, "-d", "postgres", "-c", sql],
                env=env, capture_output=True, text=True,
            )
            if result.returncode != 0:
                print(f"ERROR: {result.stderr}")
                sys.exit(1)
        print("Database recreated.")

    # Restore
    print(f"\nRestoring database... (this may take a while for {file_size_mb:.0f} MB)")
    start = time.time()

    process = subprocess.Popen(
        ["psql", "-h", host, "-p", port, "-U", user, "-d", database, "-f", str(sql_file)],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )

    # Stream stderr for error reporting
    error_count = 0
    for line in process.stderr:
        line = line.rstrip()
        if "ERROR" in line:
            error_count += 1
            if error_count <= 20:
                print(f"  ERROR: {line}")
            elif error_count == 21:
                print("  ... (suppressing further errors)")

    process.wait()
    elapsed = time.time() - start
    minutes, seconds = divmod(int(elapsed), 60)

    print()
    print("=" * 44)
    if process.returncode == 0 and error_count == 0:
        print(f"  Restore completed successfully!")
    else:
        print(f"  Restore finished with {error_count} error(s)")
    print(f"  Time: {minutes:02d}:{seconds:02d}")
    print("=" * 44)


def main():
    parser = argparse.ArgumentParser(description="Restore PostgreSQL backup to Railway")
    parser.add_argument("--file", "-f", help="Path to .sql backup file (default: latest in backup/)")
    parser.add_argument("--drop-first", action="store_true", help="Drop and recreate database before restore")
    args = parser.parse_args()

    env = load_env()

    required = ["PG_HOST", "PG_PORT", "PG_USER", "PG_PASSWORD", "PG_DATABASE"]
    for key in required:
        if key not in env:
            print(f"ERROR: Missing {key} in .env")
            sys.exit(1)

    sql_file = Path(args.file) if args.file else find_latest_backup()
    if not sql_file.exists():
        print(f"ERROR: File not found: {sql_file}")
        sys.exit(1)

    restore(
        host=env["PG_HOST"],
        port=env["PG_PORT"],
        user=env["PG_USER"],
        password=env["PG_PASSWORD"],
        database=env["PG_DATABASE"],
        sql_file=sql_file,
        drop_first=args.drop_first,
    )


if __name__ == "__main__":
    main()
