#!/usr/bin/env python3
"""
CLI entry point for Odoo v15 → v19 migration.

Usage:
    python -m migrate.run                    # run all base phases (1-7)
    python -m migrate.run --phase 1          # run specific phase
    python -m migrate.run --phase 1 2 3      # run phases 1, 2, 3
    python -m migrate.run --phase 8          # attachments (optional)
    python -m migrate.run --list              # list available phases
    python -m migrate.run --reset             # delete id_map.json and start fresh

Run from odoo-migration/:
    cd /home/odoo-migration
    python -m migrate.run
"""

import argparse
import logging
import sys
import time
from pathlib import Path

# Ensure odoo-migration root is on path (migrate/ package lives here)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from migrate.config import (
    V15_DB, V15_PASSWORD, V15_URL, V15_USER,
    V19_DB, V19_PASSWORD, V19_URL, V19_USER,
)
from migrate.migrator import MAP_FILE, Migrator, OdooConnection
from migrate.models.base import PHASES as BASE_PHASES, migrate_all
from migrate.models.product import PHASES as PRODUCT_PHASES
from migrate.models.accounting import PHASES as ACCOUNTING_PHASES
from migrate.models.hr import PHASES as HR_PHASES
from migrate.models.orders import PHASES as ORDER_PHASES
from migrate.models.stock import PHASES as STOCK_PHASES
from migrate.models.mrp import PHASES as MRP_PHASES
from migrate.models.invoices import PHASES as INVOICE_PHASES
from migrate.models.payments import PHASES as PAYMENT_PHASES
from migrate.models.reconcile import PHASES as RECONCILE_PHASES
from migrate.models.stock_detail import PHASES as STOCK_DETAIL_PHASES
from migrate.models.crm_project import PHASES as CRM_PROJECT_PHASES
from migrate.models.attachments import PHASES as ATTACHMENT_PHASES
from migrate.models.mail import PHASES as MAIL_PHASES
from migrate.models.sequences import PHASES as SEQUENCE_PHASES

# Merge all phases
PHASES = {**BASE_PHASES, **PRODUCT_PHASES, **ACCOUNTING_PHASES, **HR_PHASES, **ORDER_PHASES, **STOCK_PHASES, **MRP_PHASES, **INVOICE_PHASES, **PAYMENT_PHASES, **RECONCILE_PHASES, **STOCK_DETAIL_PHASES, **CRM_PROJECT_PHASES, **ATTACHMENT_PHASES, **MAIL_PHASES, **SEQUENCE_PHASES}


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(level=level, format=fmt, datefmt="%H:%M:%S")


def main():
    parser = argparse.ArgumentParser(description="Odoo v15 → v19 migration")
    parser.add_argument("--phase", type=int, nargs="*", help="Run specific phase(s)")
    parser.add_argument("--list", action="store_true", help="List available phases")
    parser.add_argument("--reset", action="store_true", help="Delete id_map.json before running")
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging")
    args = parser.parse_args()

    setup_logging(args.verbose)
    log = logging.getLogger("migrate")

    if args.list:
        print("Available phases:")
        for num, (name, _) in sorted(PHASES.items()):
            print(f"  {num}: {name}")
        return

    if args.reset and MAP_FILE.exists():
        MAP_FILE.unlink()
        log.info("Deleted %s", MAP_FILE)

    # Connect to both instances
    src = OdooConnection(V15_URL, V15_DB, V15_USER, V15_PASSWORD, label="v15")
    dst = OdooConnection(V19_URL, V19_DB, V19_USER, V19_PASSWORD, label="v19")
    m = Migrator(src, dst)

    log.info("Connecting to Odoo instances...")
    m.connect()

    t0 = time.time()

    if args.phase:
        for p in args.phase:
            if p not in PHASES:
                log.error("Unknown phase %d. Use --list to see available phases.", p)
                sys.exit(1)
            name, func = PHASES[p]
            log.info(">>> Running phase %d: %s", p, name)
            func(m)
    else:
        log.info(">>> Running all base phases (1-7)")
        migrate_all(m)

    elapsed = time.time() - t0
    log.info("Migration completed in %.1f seconds", elapsed)
    log.info("ID map saved to %s (%d models)", MAP_FILE, len(m.id_map._map))


if __name__ == "__main__":
    main()
