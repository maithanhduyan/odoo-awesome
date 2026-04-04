#!/usr/bin/env python3
"""
Merge duplicate products in Odoo V19.

Handles 3 cases where V19 default products conflict with migrated V15 products:
  - Delivery_007: V19#2 (keep) ← V19#52 (migrated dup)
  - EXP_GEN:      V19#9 (keep) ← V19#148 (migrated dup)
  - TIPS:         V19#1 (keep) ← V19#262 (migrated dup)

Strategy:
  1. Find variant (product.product) IDs for both keep and delete templates
  2. Reassign ALL references from dup variant → keep variant (via SQL for speed)
  3. Update id_map.json so future phases point to the correct V19 IDs
  4. Delete the duplicate templates

Usage:
    python3 merge_duplicate_products.py              # dry-run (report only)
    python3 merge_duplicate_products.py --execute     # execute merge
"""

import argparse
import json
import subprocess
import sys
import xmlrpc.client
from pathlib import Path

from migrate.config import V19_DB, V19_PASSWORD, V19_URL, V19_USER

MAP_FILE = Path(__file__).parent / "migrate" / "id_map.json"

# Templates to merge: (keep_tmpl_id, delete_tmpl_id, label)
MERGE_PAIRS = [
    (2, 52, "Delivery_007"),
    (9, 148, "EXP_GEN"),
    (1, 262, "TIPS"),
]

# All models with product_id (variant) FK
VARIANT_REFS = [
    ("sale_order_line", "product_id"),
    ("purchase_order_line", "product_id"),
    ("account_move_line", "product_id"),
    ("stock_move", "product_id"),
    ("stock_move_line", "product_id"),
    ("stock_quant", "product_id"),
    ("mrp_bom_line", "product_id"),
]

# Models with product_tmpl_id FK
TEMPLATE_REFS = [
    ("mrp_bom", "product_tmpl_id"),
    ("product_supplierinfo", "product_tmpl_id"),
]


def connect_xmlrpc():
    common = xmlrpc.client.ServerProxy(f"{V19_URL}/xmlrpc/2/common")
    uid = common.authenticate(V19_DB, V19_USER, V19_PASSWORD, {})
    models = xmlrpc.client.ServerProxy(f"{V19_URL}/xmlrpc/2/object")
    print(f"Connected to {V19_DB} as uid={uid}")
    return uid, models


def execute(models, uid, model, method, *args, **kwargs):
    return models.execute_kw(V19_DB, uid, V19_PASSWORD, model, method, args, kwargs)


def run_sql(sql, fetch=True):
    """Run SQL against V19 PostgreSQL via docker exec."""
    cmd = [
        "docker", "exec", "postgres-18",
        "psql", "-U", "odoo", "-d", V19_DB,
        "-t", "-A", "-c", sql,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  SQL ERROR: {result.stderr.strip()}")
        return None
    if fetch:
        lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
        return lines
    return result.stdout


def get_variant_id(models, uid, tmpl_id):
    """Get the product.product (variant) ID for a template."""
    variants = execute(
        models, uid, "product.product", "search_read",
        [("product_tmpl_id", "=", tmpl_id)],
        fields=["id"],
        context={"active_test": False},
    )
    if not variants:
        return None
    return variants[0]["id"]


def count_refs(tmpl_id, variant_id):
    """Count references to a template/variant across all relevant tables."""
    counts = {}
    for table, col in VARIANT_REFS:
        rows = run_sql(f"SELECT count(*) FROM {table} WHERE {col} = {variant_id}")
        if rows and rows[0].isdigit():
            c = int(rows[0])
            if c > 0:
                counts[f"{table}.{col}"] = c

    for table, col in TEMPLATE_REFS:
        rows = run_sql(f"SELECT count(*) FROM {table} WHERE {col} = {tmpl_id}")
        if rows and rows[0].isdigit():
            c = int(rows[0])
            if c > 0:
                counts[f"{table}.{col}"] = c

    return counts


def merge_one(models, uid, keep_tmpl, delete_tmpl, label, dry_run=True):
    """Merge one duplicate pair: reassign refs from delete → keep, then delete."""
    print(f"\n{'─' * 60}")
    print(f"  [{label}] keep=tmpl#{keep_tmpl} → delete=tmpl#{delete_tmpl}")

    keep_var = get_variant_id(models, uid, keep_tmpl)
    delete_var = get_variant_id(models, uid, delete_tmpl)

    if not keep_var or not delete_var:
        print(f"  ❌ Missing variants: keep_var={keep_var}, delete_var={delete_var}")
        return False

    print(f"  Variants: keep=pp#{keep_var}, delete=pp#{delete_var}")

    # Count references on the duplicate
    refs = count_refs(delete_tmpl, delete_var)
    if refs:
        print(f"  References on duplicate:")
        for k, v in refs.items():
            print(f"    {k}: {v}")
    else:
        print(f"  No references on duplicate — just needs deletion.")

    if dry_run:
        print(f"  [DRY-RUN] Would reassign {sum(refs.values())} references and delete tmpl#{delete_tmpl}")
        return True

    # ── Reassign variant references ──
    for table, col in VARIANT_REFS:
        sql = f"UPDATE {table} SET {col} = {keep_var} WHERE {col} = {delete_var}"
        result = run_sql(sql, fetch=False)
        rows = run_sql(f"SELECT count(*) FROM {table} WHERE {col} = {delete_var}")
        remaining = int(rows[0]) if rows and rows[0].isdigit() else -1
        if remaining > 0:
            print(f"  ⚠️  {table}.{col}: {remaining} still pointing to delete variant!")

    # ── Reassign template references ──
    for table, col in TEMPLATE_REFS:
        sql = f"UPDATE {table} SET {col} = {keep_tmpl} WHERE {col} = {delete_tmpl}"
        run_sql(sql, fetch=False)

    # ── Verify no remaining refs ──
    remaining_refs = count_refs(delete_tmpl, delete_var)
    if remaining_refs:
        print(f"  ⚠️  Still has references after reassignment: {remaining_refs}")
        print(f"  Skipping deletion — check manually.")
        return False

    # ── Copy useful data from dup → keep (if keep is missing it) ──
    # e.g., keep template is V19 default and may lack some V15 data
    keep_data = execute(models, uid, "product.template", "read", [keep_tmpl],
                        ["default_code", "image_1920"])
    del_data = execute(models, uid, "product.template", "read", [delete_tmpl],
                       ["default_code", "image_1920"])
    if keep_data and del_data:
        update = {}
        if not keep_data[0].get("image_1920") and del_data[0].get("image_1920"):
            update["image_1920"] = del_data[0]["image_1920"]
        if update:
            execute(models, uid, "product.template", "write", [keep_tmpl], update)
            print(f"  Copied fields to keep template: {list(update.keys())}")

    # ── Delete duplicate: archive variant first, then unlink template ──
    try:
        # Unlink variant
        execute(models, uid, "product.product", "write", [delete_var], {"active": False})
        execute(models, uid, "product.product", "unlink", [delete_var])
        # Unlink template
        execute(models, uid, "product.template", "write", [delete_tmpl], {"active": False})
        execute(models, uid, "product.template", "unlink", [delete_tmpl])
        print(f"  ✅ Deleted tmpl#{delete_tmpl} + pp#{delete_var}")
    except Exception as e:
        # If ORM delete fails, use SQL
        print(f"  ORM delete failed ({e}), trying SQL...")
        run_sql(f"DELETE FROM product_product WHERE id = {delete_var}", fetch=False)
        run_sql(f"DELETE FROM product_template WHERE id = {delete_tmpl}", fetch=False)
        print(f"  ✅ SQL-deleted tmpl#{delete_tmpl} + pp#{delete_var}")

    return True


def update_id_map(keep_tmpl, delete_tmpl, keep_var, delete_var):
    """Update id_map.json: find v15 IDs pointing to delete IDs, remap to keep IDs."""
    if not MAP_FILE.exists():
        print("  id_map.json not found, skipping.")
        return

    data = json.loads(MAP_FILE.read_text())
    changed = False

    # Fix product.template mapping
    tmpl_map = data.get("product.template", {})
    for v15_id, v19_id in list(tmpl_map.items()):
        if v19_id == delete_tmpl:
            tmpl_map[v15_id] = keep_tmpl
            print(f"  id_map: product.template v15#{v15_id}: {delete_tmpl} → {keep_tmpl}")
            changed = True

    # Fix product.product mapping
    pp_map = data.get("product.product", {})
    for v15_id, v19_id in list(pp_map.items()):
        if v19_id == delete_var:
            pp_map[v15_id] = keep_var
            print(f"  id_map: product.product v15#{v15_id}: {delete_var} → {keep_var}")
            changed = True

    if changed:
        MAP_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        print(f"  ✅ id_map.json updated")


def main():
    parser = argparse.ArgumentParser(description="Merge duplicate products in V19")
    parser.add_argument("--execute", action="store_true", help="Actually execute (default: dry-run)")
    args = parser.parse_args()

    dry_run = not args.execute
    if dry_run:
        print("=" * 60)
        print("DRY-RUN MODE — no changes will be made")
        print("Run with --execute to apply changes")
        print("=" * 60)
    else:
        print("=" * 60)
        print("⚡ EXECUTE MODE — will modify data!")
        print("=" * 60)

    uid, models = connect_xmlrpc()

    success = 0
    for keep_tmpl, delete_tmpl, label in MERGE_PAIRS:
        keep_var = get_variant_id(models, uid, keep_tmpl)
        delete_var = get_variant_id(models, uid, delete_tmpl)

        ok = merge_one(models, uid, keep_tmpl, delete_tmpl, label, dry_run=dry_run)

        if ok and not dry_run and keep_var and delete_var:
            update_id_map(keep_tmpl, delete_tmpl, keep_var, delete_var)
            success += 1

    print(f"\n{'=' * 60}")
    if dry_run:
        print(f"DRY-RUN complete. {len(MERGE_PAIRS)} pairs analyzed.")
        print(f"Run with --execute to apply.")
    else:
        print(f"Done. {success}/{len(MERGE_PAIRS)} pairs merged.")
    print()


if __name__ == "__main__":
    main()
