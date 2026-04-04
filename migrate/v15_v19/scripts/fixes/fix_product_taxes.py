#!/usr/bin/env python3
"""
Fix product default taxes in V19 by syncing from V15.

Problem: Product migration didn't include taxes_id / supplier_taxes_id.
         V19 defaults to 10% for most products, but V15 has 8% on ~490 products.

Strategy:
  1. Read V15 product_taxes_rel and product_supplier_taxes_rel
  2. Map product IDs (via id_map) and tax IDs (via TAX_MAP)
  3. Replace V19 tax assignments with correct ones from V15

Usage:
    python3 fix_product_taxes.py              # dry-run
    python3 fix_product_taxes.py --execute    # apply
"""

import argparse
import json
import subprocess
from pathlib import Path

MAP_FILE = Path(__file__).parent / "migrate" / "id_map.json"

# V15 tax id → V19 tax id
TAX_MAP = {
    1: 1,    # Deductible VAT 10% (purchase)
    2: 3,    # Deductible VAT 5% (purchase)
    3: 4,    # Deductible VAT 0% (purchase)
    4: 11,   # VAT 10% (sale)
    5: 13,   # VAT 5% (sale)
    6: 14,   # VAT 0% (sale)
    7: 12,   # GTGT 8% (sale)
    8: 2,    # GTGT 8% (purchase)
}


def sql(db, query, container=None):
    """Run SQL and return rows as list of tuples."""
    cmd = ["docker", "exec", container or "postgresql",
           "psql", "-U", "odoo", "-d", db, "-t", "-A", "-c", query]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  SQL ERROR: {r.stderr.strip()}")
        return []
    return [line.split("|") for line in r.stdout.strip().split("\n") if line.strip()]


def load_id_map():
    data = json.loads(MAP_FILE.read_text())
    tmpl_map = {int(k): v for k, v in data.get("product.template", {}).items()}
    return tmpl_map


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    dry_run = not args.execute
    print("=" * 60)
    print("DRY-RUN" if dry_run else "⚡ EXECUTE", "— Fix product default taxes")
    print("=" * 60)

    tmpl_map = load_id_map()
    print(f"Loaded {len(tmpl_map)} product.template mappings")

    # ── Read V15 tax assignments ──
    v15_customer = sql("taya_db",
        "SELECT prod_id, tax_id FROM product_taxes_rel ORDER BY prod_id")
    v15_supplier = sql("taya_db",
        "SELECT prod_id, tax_id FROM product_supplier_taxes_rel ORDER BY prod_id")

    print(f"V15 customer tax assignments: {len(v15_customer)}")
    print(f"V15 supplier tax assignments: {len(v15_supplier)}")

    # ── Read V19 current tax assignments ──
    v19_customer = sql("taya19_db",
        "SELECT prod_id, tax_id FROM product_taxes_rel ORDER BY prod_id",
        container="postgres-18")
    v19_supplier = sql("taya19_db",
        "SELECT prod_id, tax_id FROM product_supplier_taxes_rel ORDER BY prod_id",
        container="postgres-18")

    # Build V19 current state: {prod_id: set(tax_ids)}
    v19_cust_map = {}
    for row in v19_customer:
        pid, tid = int(row[0]), int(row[1])
        v19_cust_map.setdefault(pid, set()).add(tid)

    v19_supp_map = {}
    for row in v19_supplier:
        pid, tid = int(row[0]), int(row[1])
        v19_supp_map.setdefault(pid, set()).add(tid)

    # ── Build expected V19 state from V15 ──
    expected_cust = {}  # {v19_tmpl_id: set(v19_tax_ids)}
    expected_supp = {}

    unmapped_tmpl = 0
    unmapped_tax = 0

    for row in v15_customer:
        v15_tmpl, v15_tax = int(row[0]), int(row[1])
        v19_tmpl = tmpl_map.get(v15_tmpl)
        v19_tax = TAX_MAP.get(v15_tax)
        if not v19_tmpl:
            unmapped_tmpl += 1
            continue
        if not v19_tax:
            unmapped_tax += 1
            continue
        expected_cust.setdefault(v19_tmpl, set()).add(v19_tax)

    for row in v15_supplier:
        v15_tmpl, v15_tax = int(row[0]), int(row[1])
        v19_tmpl = tmpl_map.get(v15_tmpl)
        v19_tax = TAX_MAP.get(v15_tax)
        if not v19_tmpl:
            unmapped_tmpl += 1
            continue
        if not v19_tax:
            unmapped_tax += 1
            continue
        expected_supp.setdefault(v19_tmpl, set()).add(v19_tax)

    if unmapped_tmpl:
        print(f"  ⚠️  {unmapped_tmpl} V15 templates not in id_map (pre-migration products?)")
    if unmapped_tax:
        print(f"  ⚠️  {unmapped_tax} V15 taxes not in TAX_MAP")

    # ── Diff: what needs to change ──
    cust_to_remove = []  # (v19_tmpl, v19_tax)
    cust_to_add = []
    supp_to_remove = []
    supp_to_add = []

    # All V19 templates that have taxes (current or expected)
    all_tmpl_ids = set(v19_cust_map.keys()) | set(expected_cust.keys()) | \
                   set(v19_supp_map.keys()) | set(expected_supp.keys())

    for tmpl_id in all_tmpl_ids:
        # Customer taxes
        current = v19_cust_map.get(tmpl_id, set())
        expected = expected_cust.get(tmpl_id, set())
        for t in current - expected:
            cust_to_remove.append((tmpl_id, t))
        for t in expected - current:
            cust_to_add.append((tmpl_id, t))

        # Supplier taxes
        current = v19_supp_map.get(tmpl_id, set())
        expected = expected_supp.get(tmpl_id, set())
        for t in current - expected:
            supp_to_remove.append((tmpl_id, t))
        for t in expected - current:
            supp_to_add.append((tmpl_id, t))

    print(f"\n--- Customer taxes (product_taxes_rel) ---")
    print(f"  To remove: {len(cust_to_remove)}")
    print(f"  To add:    {len(cust_to_add)}")
    print(f"\n--- Supplier taxes (product_supplier_taxes_rel) ---")
    print(f"  To remove: {len(supp_to_remove)}")
    print(f"  To add:    {len(supp_to_add)}")

    # Show summary by tax
    from collections import Counter
    if cust_to_remove:
        print("\n  Customer REMOVE breakdown:")
        for tax_id, cnt in Counter(t for _, t in cust_to_remove).most_common():
            print(f"    tax#{tax_id}: {cnt} products")
    if cust_to_add:
        print("\n  Customer ADD breakdown:")
        for tax_id, cnt in Counter(t for _, t in cust_to_add).most_common():
            print(f"    tax#{tax_id}: {cnt} products")
    if supp_to_remove:
        print("\n  Supplier REMOVE breakdown:")
        for tax_id, cnt in Counter(t for _, t in supp_to_remove).most_common():
            print(f"    tax#{tax_id}: {cnt} products")
    if supp_to_add:
        print("\n  Supplier ADD breakdown:")
        for tax_id, cnt in Counter(t for _, t in supp_to_add).most_common():
            print(f"    tax#{tax_id}: {cnt} products")

    if dry_run:
        print(f"\n[DRY-RUN] No changes made. Run with --execute to apply.")
        return

    # ── Apply changes via SQL ──
    CHUNK = 500

    # Remove wrong customer taxes
    if cust_to_remove:
        print(f"\nRemoving {len(cust_to_remove)} wrong customer tax assignments...")
        for i in range(0, len(cust_to_remove), CHUNK):
            chunk = cust_to_remove[i:i + CHUNK]
            conditions = " OR ".join(
                f"(prod_id = {pid} AND tax_id = {tid})" for pid, tid in chunk
            )
            sql("taya19_db",
                f"DELETE FROM product_taxes_rel WHERE {conditions}",
                container="postgres-18")

    # Add correct customer taxes
    if cust_to_add:
        print(f"Adding {len(cust_to_add)} correct customer tax assignments...")
        for i in range(0, len(cust_to_add), CHUNK):
            chunk = cust_to_add[i:i + CHUNK]
            values = ", ".join(f"({pid}, {tid})" for pid, tid in chunk)
            sql("taya19_db",
                f"INSERT INTO product_taxes_rel (prod_id, tax_id) VALUES {values} "
                f"ON CONFLICT DO NOTHING",
                container="postgres-18")

    # Remove wrong supplier taxes
    if supp_to_remove:
        print(f"Removing {len(supp_to_remove)} wrong supplier tax assignments...")
        for i in range(0, len(supp_to_remove), CHUNK):
            chunk = supp_to_remove[i:i + CHUNK]
            conditions = " OR ".join(
                f"(prod_id = {pid} AND tax_id = {tid})" for pid, tid in chunk
            )
            sql("taya19_db",
                f"DELETE FROM product_supplier_taxes_rel WHERE {conditions}",
                container="postgres-18")

    # Add correct supplier taxes
    if supp_to_add:
        print(f"Adding {len(supp_to_add)} correct supplier tax assignments...")
        for i in range(0, len(supp_to_add), CHUNK):
            chunk = supp_to_add[i:i + CHUNK]
            values = ", ".join(f"({pid}, {tid})" for pid, tid in chunk)
            sql("taya19_db",
                f"INSERT INTO product_supplier_taxes_rel (prod_id, tax_id) VALUES {values} "
                f"ON CONFLICT DO NOTHING",
                container="postgres-18")

    # ── Verify ──
    print("\n--- Verification ---")
    result = sql("taya19_db",
        "SELECT at.id, at.amount, at.type_tax_use, count(*) "
        "FROM product_taxes_rel ptr JOIN account_tax at ON at.id = ptr.tax_id "
        "GROUP BY at.id, at.amount, at.type_tax_use ORDER BY count(*) DESC",
        container="postgres-18")
    print("Customer taxes:")
    for row in result:
        print(f"  tax#{row[0]} ({row[1]}% {row[2]}): {row[3]} products")

    result = sql("taya19_db",
        "SELECT at.id, at.amount, at.type_tax_use, count(*) "
        "FROM product_supplier_taxes_rel ptr JOIN account_tax at ON at.id = ptr.tax_id "
        "GROUP BY at.id, at.amount, at.type_tax_use ORDER BY count(*) DESC",
        container="postgres-18")
    print("Supplier taxes:")
    for row in result:
        print(f"  tax#{row[0]} ({row[1]}% {row[2]}): {row[3]} products")

    print("\n✅ Done!")


if __name__ == "__main__":
    main()
