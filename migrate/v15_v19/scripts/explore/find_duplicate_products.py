#!/usr/bin/env python3
"""
Find and optionally delete duplicate products in Odoo V19.

Duplicates are detected by:
  1. default_code (if not empty) — exact match
  2. name (exact match) — for products without default_code

The OLDEST record (lowest id) is kept; newer duplicates are listed for deletion.

Usage:
    python find_duplicate_products.py              # report only
    python find_duplicate_products.py --delete     # delete duplicates (asks confirmation)
"""

import argparse
import xmlrpc.client
from collections import defaultdict

from migrate.config import V19_DB, V19_PASSWORD, V19_URL, V19_USER


def connect():
    common = xmlrpc.client.ServerProxy(f"{V19_URL}/xmlrpc/2/common")
    uid = common.authenticate(V19_DB, V19_USER, V19_PASSWORD, {})
    models = xmlrpc.client.ServerProxy(f"{V19_URL}/xmlrpc/2/object")
    print(f"Connected to {V19_DB} as uid={uid}")
    return uid, models


def execute(models, uid, model, method, *args, **kwargs):
    return models.execute_kw(V19_DB, uid, V19_PASSWORD, model, method, args, kwargs)


def find_duplicates(models, uid):
    """Find duplicate product.template records."""

    # Read ALL templates (id, name, default_code, create_date)
    templates = execute(
        models, uid, "product.template", "search_read",
        [],  # all records, including archived
        fields=["id", "name", "default_code", "create_date", "active"],
        order="id asc",
        context={"active_test": False},
    )
    print(f"\nTotal product.template records: {len(templates)}")

    # Group by default_code (non-empty)
    by_code = defaultdict(list)
    by_name_no_code = defaultdict(list)

    for t in templates:
        code = (t.get("default_code") or "").strip()
        if code:
            by_code[code].append(t)
        else:
            by_name_no_code[t["name"]].append(t)

    # Find duplicates
    duplicates = []  # list of (keep, [to_delete])

    for code, group in sorted(by_code.items()):
        if len(group) > 1:
            keep = group[0]  # oldest = original
            to_delete = group[1:]
            duplicates.append((code, keep, to_delete))

    for name, group in sorted(by_name_no_code.items()):
        if len(group) > 1:
            keep = group[0]
            to_delete = group[1:]
            duplicates.append((f"(name) {name}", keep, to_delete))

    return duplicates


def find_variant_duplicates(models, uid):
    """Find duplicate product.product records per template."""
    variants = execute(
        models, uid, "product.product", "search_read",
        [],
        fields=["id", "product_tmpl_id", "default_code", "active"],
        order="id asc",
        context={"active_test": False},
    )
    print(f"Total product.product records: {len(variants)}")

    by_tmpl = defaultdict(list)
    for v in variants:
        tmpl_id = v["product_tmpl_id"][0] if isinstance(v["product_tmpl_id"], (list, tuple)) else v["product_tmpl_id"]
        by_tmpl[tmpl_id].append(v)

    # Templates with more than 1 variant may be legitimate (attribute-based)
    # but migration duplicates would have same default_code
    dup_variants = []
    for tmpl_id, group in by_tmpl.items():
        if len(group) <= 1:
            continue
        codes = defaultdict(list)
        for v in group:
            c = (v.get("default_code") or "").strip() or f"__no_code_{v['id']}"
            codes[c].append(v)
        for code, vlist in codes.items():
            if len(vlist) > 1 and not code.startswith("__no_code_"):
                keep = vlist[0]
                to_delete = vlist[1:]
                dup_variants.append((code, tmpl_id, keep, to_delete))

    return dup_variants


def check_references(models, uid, template_ids):
    """Check if templates are referenced in sale.order.line, purchase.order.line, etc."""
    # Get variant ids for these templates
    variants = execute(
        models, uid, "product.product", "search_read",
        [("product_tmpl_id", "in", template_ids)],
        fields=["id", "product_tmpl_id"],
        context={"active_test": False},
    )
    variant_ids = [v["id"] for v in variants]

    refs = {}
    ref_models = [
        ("sale.order.line", "product_id"),
        ("purchase.order.line", "product_id"),
        ("account.move.line", "product_id"),
        ("stock.move", "product_id"),
        ("stock.move.line", "product_id"),
        ("mrp.bom", "product_tmpl_id"),
    ]

    for model, field in ref_models:
        try:
            if "tmpl" in field:
                count = execute(models, uid, model, "search_count",
                                [(field, "in", template_ids)],
                                context={"active_test": False})
            else:
                count = execute(models, uid, model, "search_count",
                                [(field, "in", variant_ids)],
                                context={"active_test": False})
            if count:
                refs[model] = count
        except Exception:
            pass  # model may not be installed

    return refs


def main():
    parser = argparse.ArgumentParser(description="Find/delete duplicate products in V19")
    parser.add_argument("--delete", action="store_true", help="Delete duplicates (with confirmation)")
    args = parser.parse_args()

    uid, models = connect()

    # ── Template duplicates ──
    print("\n" + "=" * 70)
    print("DUPLICATE PRODUCT TEMPLATES")
    print("=" * 70)

    duplicates = find_duplicates(models, uid)

    if not duplicates:
        print("\n  No duplicate templates found!")
    else:
        total_dups = sum(len(d) for _, _, d in duplicates)
        print(f"\n  Found {len(duplicates)} groups with {total_dups} duplicate(s):\n")

        all_delete_ids = []
        for key, keep, to_delete in duplicates:
            delete_ids = [t["id"] for t in to_delete]
            all_delete_ids.extend(delete_ids)
            print(f"  [{key}]")
            print(f"    KEEP:   id={keep['id']:>6}  created={keep['create_date']}")
            for d in to_delete:
                print(f"    DELETE: id={d['id']:>6}  created={d['create_date']}")

        # Check references for duplicates
        print(f"\n  Checking references for {len(all_delete_ids)} duplicate templates...")
        refs = check_references(models, uid, all_delete_ids)
        if refs:
            print("  ⚠️  WARNING: Duplicates are referenced in:")
            for model, count in refs.items():
                print(f"    - {model}: {count} records")
            print("  Deleting these will fail or cascade. Fix references first!")
        else:
            print("  ✅ No references found — safe to delete.")

        if args.delete and not refs:
            print(f"\n  About to delete {len(all_delete_ids)} duplicate templates: {all_delete_ids}")
            confirm = input("  Type 'yes' to confirm: ")
            if confirm.strip().lower() == "yes":
                # Archive first (safer), then delete
                try:
                    execute(models, uid, "product.template", "write",
                            all_delete_ids, {"active": False})
                    execute(models, uid, "product.template", "unlink", all_delete_ids)
                    print(f"  ✅ Deleted {len(all_delete_ids)} duplicate templates.")
                except Exception as e:
                    print(f"  ❌ Delete failed: {e}")
                    print("  Try archiving instead (set active=False).")
            else:
                print("  Cancelled.")
        elif args.delete and refs:
            print("\n  ⚠️  Cannot delete — references exist. Clean up references first.")

    # ── Variant duplicates ──
    print("\n" + "=" * 70)
    print("DUPLICATE PRODUCT VARIANTS (same default_code per template)")
    print("=" * 70)

    var_dups = find_variant_duplicates(models, uid)
    if not var_dups:
        print("\n  No duplicate variants found!")
    else:
        total_var_dups = sum(len(d) for _, _, _, d in var_dups)
        print(f"\n  Found {len(var_dups)} groups with {total_var_dups} duplicate variant(s):\n")
        for code, tmpl_id, keep, to_delete in var_dups:
            print(f"  [code={code}, tmpl={tmpl_id}]")
            print(f"    KEEP:   id={keep['id']}")
            for d in to_delete:
                print(f"    DELETE: id={d['id']}")

    print()


if __name__ == "__main__":
    main()
