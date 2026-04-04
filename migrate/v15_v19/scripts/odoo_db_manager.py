#!/usr/bin/env python3
"""
Odoo Database Manager — XML-RPC automation script.

Usage:
    python odoo_db_manager.py status
    python odoo_db_manager.py init      [--db DB] [--lang LANG] [--demo]
    python odoo_db_manager.py backup    [--db DB] [--output FILE]
    python odoo_db_manager.py restore   --input FILE [--db DB] [--copy]
    python odoo_db_manager.py drop      --db DB
    python odoo_db_manager.py bootstrap [--db DB] [--container CONTAINER]

Commands:
    status      Show server version and list databases
    init        Create a fresh database via XML-RPC (drops existing)
    backup      Dump database to a zip file
    restore     Restore database from a zip backup
    drop        Drop a database (interactive confirm)
    bootstrap   Fix broken state: drop empty DB via psql, restart container,
                then Odoo auto-initializes on startup

Environment variables:
    ODOO_URL            Odoo base URL         (default: http://localhost:8069)
    ODOO_MASTER_PWD     Master admin password  (default: admin)
    ODOO_DB             Database name          (default: odoo)
"""

import argparse
import base64
import os
import subprocess
import sys
import time
import xmlrpc.client
from datetime import datetime
from pathlib import Path


# ── Defaults ────────────────────────────────────────────────────────────────
DEFAULT_URL = os.environ.get("ODOO_URL", "http://localhost:8069")
DEFAULT_MASTER_PWD = os.environ.get("ODOO_MASTER_PWD", "admin")
DEFAULT_DB = os.environ.get("ODOO_DB", "odoo")
BACKUP_DIR = Path(__file__).resolve().parent.parent / "odoo-15" / "backup"


# ── Helpers ─────────────────────────────────────────────────────────────────

def get_db_proxy(url: str) -> xmlrpc.client.ServerProxy:
    return xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/db")


def get_common_proxy(url: str) -> xmlrpc.client.ServerProxy:
    return xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")


def wait_for_odoo(url: str, timeout: int = 120) -> bool:
    """Wait until the Odoo XML-RPC endpoint becomes reachable."""
    print(f"Waiting for Odoo at {url} ...", end="", flush=True)
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            proxy = get_db_proxy(url)
            proxy.list()
            print(" OK")
            return True
        except Exception:
            print(".", end="", flush=True)
            time.sleep(2)
    print(" TIMEOUT")
    return False


# ── Commands ────────────────────────────────────────────────────────────────

def cmd_status(url: str, master_pwd: str, db_name: str):
    """Show server version and list databases."""
    db = get_db_proxy(url)
    common = get_common_proxy(url)

    version = common.version()
    databases = db.list()

    print(f"Server:    {url}")
    print(f"Version:   {version.get('server_version', '?')}")
    print(f"Databases: {', '.join(databases) if databases else '(none)'}")
    print(f"Target DB: {db_name} — {'EXISTS' if db.db_exist(db_name) else 'MISSING'}")


def cmd_init(url: str, master_pwd: str, db_name: str, lang: str, demo: bool):
    """Create a fresh Odoo database (drops existing one if present)."""
    db = get_db_proxy(url)

    if db.db_exist(db_name):
        print(f"Database '{db_name}' exists — dropping first ...")
        db.drop(master_pwd, db_name)
        print(f"  Dropped.")

    print(f"Creating database '{db_name}' (lang={lang}, demo={demo}) ...")
    print("  This may take a few minutes ...")
    db.create_database(
        master_pwd,
        db_name,
        demo,      # demo data
        lang,      # language
        "admin",   # user_password
        "admin",   # login
    )
    print(f"  Database '{db_name}' created successfully.")
    print(f"  Login: admin / admin")


def cmd_backup(url: str, master_pwd: str, db_name: str, output: str | None,
               pg_container: str, odoo_container: str):
    """Dump database to a zip file (SQL dump + filestore).

    Uses pg_dump from the postgres container (avoids version mismatch with
    the pg client bundled in the Odoo image) and copies the filestore from
    the Odoo container.
    """
    db = get_db_proxy(url)

    if not db.db_exist(db_name):
        print(f"Error: database '{db_name}' does not exist.", file=sys.stderr)
        sys.exit(1)

    if output is None:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output = str(BACKUP_DIR / f"{db_name}_{ts}.zip")

    import io
    import tempfile
    import zipfile

    with tempfile.TemporaryDirectory() as tmpdir:
        dump_file = Path(tmpdir) / "dump.sql"

        # 1. pg_dump from postgres container
        print(f"Backing up '{db_name}' ...")
        print("  Running pg_dump ...")
        result = subprocess.run(
            ["docker", "exec", pg_container,
             "pg_dump", "--no-owner", "--format=p", "-U", "odoo", db_name],
            capture_output=True, timeout=300,
        )
        if result.returncode != 0:
            print(f"  pg_dump failed: {result.stderr.decode()}", file=sys.stderr)
            sys.exit(1)
        dump_file.write_bytes(result.stdout)

        # 2. Copy filestore from Odoo container
        filestore_dir = Path(tmpdir) / "filestore"
        print("  Copying filestore ...")
        fs_result = subprocess.run(
            ["docker", "cp", f"{odoo_container}:/var/lib/odoo/filestore/{db_name}/.", str(filestore_dir)],
            capture_output=True, text=True, timeout=300,
        )
        if fs_result.returncode != 0:
            print(f"  No filestore found (may be empty): {fs_result.stderr.strip()}")

        # 3. Package into zip
        print(f"  Writing → {output} ...")
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(str(dump_file), "dump.sql")
            if filestore_dir.exists():
                for fpath in filestore_dir.rglob("*"):
                    if fpath.is_file():
                        arcname = "filestore/" + str(fpath.relative_to(filestore_dir))
                        zf.write(str(fpath), arcname)

        size_mb = Path(output).stat().st_size / (1024 * 1024)
        print(f"  Done — {size_mb:.1f} MB written.")


def cmd_restore(url: str, master_pwd: str, db_name: str, input_file: str,
                copy: bool, pg_container: str, odoo_container: str):
    """Restore database from a zip backup (SQL dump + filestore).

    Uses psql from the postgres container for the SQL restore.
    """
    db = get_db_proxy(url)
    path = Path(input_file)

    if not path.exists():
        print(f"Error: file not found: {input_file}", file=sys.stderr)
        sys.exit(1)

    # Validate it's actually a zip
    magic = path.read_bytes()[:4]
    if magic[:2] != b"PK":
        print(f"Error: '{input_file}' is not a valid zip file.", file=sys.stderr)
        sys.exit(1)

    import tempfile
    import zipfile

    if not zipfile.is_zipfile(str(path)):
        print(f"Error: '{input_file}' is not a valid zip file.", file=sys.stderr)
        sys.exit(1)

    if db.db_exist(db_name):
        print(f"Database '{db_name}' exists — dropping first ...")
        db.drop(master_pwd, db_name)
        print(f"  Dropped.")

    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"Extracting '{input_file}' ...")
        with zipfile.ZipFile(str(path), "r") as zf:
            zf.extractall(tmpdir)

        dump_file = Path(tmpdir) / "dump.sql"
        if not dump_file.exists():
            print("Error: dump.sql not found in backup zip.", file=sys.stderr)
            sys.exit(1)

        # 1. Create empty database
        print(f"Creating empty database '{db_name}' ...")
        subprocess.run(
            ["docker", "exec", pg_container,
             "createdb", "-U", "odoo", "--encoding=UTF8",
             "--template=template0", db_name],
            check=True, capture_output=True, timeout=30,
        )

        # 2. Restore SQL dump via docker cp + psql
        print("  Restoring SQL dump ...")

        # Copy dump file into container
        subprocess.run(
            ["docker", "cp", str(dump_file), f"{pg_container}:/tmp/dump.sql"],
            check=True, capture_output=True, timeout=60,
        )

        result = subprocess.run(
            ["docker", "exec", pg_container,
             "psql", "-U", "odoo", "-d", db_name,
             "-f", "/tmp/dump.sql", "--quiet", "--single-transaction"],
            capture_output=True, text=True, timeout=600,
        )
        if result.returncode != 0:
            print(f"  psql restore failed: {result.stderr}", file=sys.stderr)
            sys.exit(1)

        # Cleanup temp file in container
        subprocess.run(
            ["docker", "exec", pg_container, "rm", "-f", "/tmp/dump.sql"],
            capture_output=True, timeout=10,
        )

        # 3. Restore filestore
        filestore_dir = Path(tmpdir) / "filestore"
        if filestore_dir.exists() and any(filestore_dir.iterdir()):
            print("  Restoring filestore ...")
            # Ensure target dir exists
            subprocess.run(
                ["docker", "exec", odoo_container,
                 "mkdir", "-p", f"/var/lib/odoo/filestore/{db_name}"],
                capture_output=True, timeout=10,
            )
            subprocess.run(
                ["docker", "cp",
                 str(filestore_dir) + "/.",
                 f"{odoo_container}:/var/lib/odoo/filestore/{db_name}/"],
                check=True, capture_output=True, timeout=300,
            )
        else:
            print("  No filestore in backup.")

        # 4. Neutralize if copy mode
        if copy:
            print("  Neutralizing database (copy mode) ...")
            subprocess.run(
                ["docker", "exec", pg_container,
                 "psql", "-U", "odoo", "-d", db_name, "-c",
                 "UPDATE ir_config_parameter SET value='copy' WHERE key='database.uuid';"],
                capture_output=True, timeout=10,
            )

    print(f"  Database '{db_name}' restored successfully.")
    print("  Restart Odoo to apply: docker restart", odoo_container)


def cmd_drop(url: str, master_pwd: str, db_name: str):
    """Drop a database."""
    db = get_db_proxy(url)

    if not db.db_exist(db_name):
        print(f"Database '{db_name}' does not exist.")
        return

    confirm = input(f"Are you sure you want to DROP '{db_name}'? [y/N] ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        return

    db.drop(master_pwd, db_name)
    print(f"Database '{db_name}' dropped.")


def cmd_bootstrap(db_name: str, odoo_container: str, pg_container: str):
    """Fix broken state: drop empty DB via psql, restart Odoo to auto-init.

    Use when the database exists but is empty (no Odoo tables),
    causing XML-RPC and HTTP 500 errors.
    """
    def docker(*args: str) -> str:
        result = subprocess.run(
            ["docker", *args],
            capture_output=True, text=True, timeout=30,
        )
        return result.stdout.strip()

    # 1. Stop Odoo so there's no active connection to the DB
    print(f"Stopping container '{odoo_container}' ...")
    docker("stop", odoo_container)

    # 2. Drop the broken database via psql (connect to 'postgres' db)
    print(f"Dropping database '{db_name}' via psql ...")
    docker("exec", pg_container, "psql", "-U", "odoo", "-d", "postgres",
           "-c", f"DROP DATABASE IF EXISTS \"{db_name}\";")

    # 3. Start Odoo — it will auto-create & initialize the database
    print(f"Starting container '{odoo_container}' ...")
    docker("start", odoo_container)

    print(f"Odoo will auto-initialize '{db_name}' on startup.")
    print("Wait ~30s for Odoo to finish, then run: python odoo_db_manager.py status")


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Odoo Database Manager (XML-RPC)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="Odoo URL")
    parser.add_argument("--master-pwd", default=DEFAULT_MASTER_PWD, help="Master password")
    parser.add_argument("--db", default=DEFAULT_DB, help="Database name")

    sub = parser.add_subparsers(dest="command", required=True)

    # status
    sub.add_parser("status", help="Show server info and databases")

    # init
    p_init = sub.add_parser("init", help="Create a fresh database")
    p_init.add_argument("--lang", default="vi_VN", help="Language (default: vi_VN)")
    p_init.add_argument("--demo", action="store_true", help="Load demo data")

    # backup
    p_backup = sub.add_parser("backup", help="Backup database to zip")
    p_backup.add_argument("--output", "-o", help="Output file path")
    p_backup.add_argument("--odoo-container", default="odoo15", help="Odoo container name")
    p_backup.add_argument("--pg-container", default="postgres", help="Postgres container name")

    # restore
    p_restore = sub.add_parser("restore", help="Restore database from zip")
    p_restore.add_argument("--input", "-i", required=True, dest="input_file", help="Backup zip file")
    p_restore.add_argument("--copy", action="store_true", help="Neutralize restored DB (copy mode)")
    p_restore.add_argument("--odoo-container", default="odoo15", help="Odoo container name")
    p_restore.add_argument("--pg-container", default="postgres", help="Postgres container name")

    # drop
    sub.add_parser("drop", help="Drop a database")

    # bootstrap
    p_boot = sub.add_parser("bootstrap", help="Fix broken DB: drop via psql + restart")
    p_boot.add_argument("--odoo-container", default="odoo15", help="Odoo container name")
    p_boot.add_argument("--pg-container", default="postgres", help="Postgres container name")

    args = parser.parse_args()

    # bootstrap doesn't need XML-RPC
    if args.command == "bootstrap":
        cmd_bootstrap(args.db, args.odoo_container, args.pg_container)
        return

    # Wait for Odoo to be reachable
    if not wait_for_odoo(args.url):
        print("Error: Odoo is not reachable.", file=sys.stderr)
        sys.exit(1)

    if args.command == "status":
        cmd_status(args.url, args.master_pwd, args.db)
    elif args.command == "init":
        cmd_init(args.url, args.master_pwd, args.db, args.lang, args.demo)
    elif args.command == "backup":
        cmd_backup(args.url, args.master_pwd, args.db, args.output,
                   args.pg_container, args.odoo_container)
    elif args.command == "restore":
        cmd_restore(args.url, args.master_pwd, args.db, args.input_file,
                    args.copy, args.pg_container, args.odoo_container)
    elif args.command == "drop":
        cmd_drop(args.url, args.master_pwd, args.db)


if __name__ == "__main__":
    main()
