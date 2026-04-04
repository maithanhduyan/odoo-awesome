"""
Fix taxes on sale.order.line, purchase.order.line, and recompute totals
to match V15 original tax assignments.

Problem: During XML-RPC migration, V19 auto-applied default 10% tax to lines
that had no tax in V15. This script:
1. Compares tax assignments per line between V15 and V19
2. Removes wrongly added taxes
3. Adds missing taxes
4. Recomputes line amounts and order totals via Odoo ORM
"""
import json
import subprocess
import xmlrpc.client
from pathlib import Path
from collections import defaultdict

MAP_FILE = Path(__file__).parent / "migrate" / "id_map.json"

# V15 tax ID -> V19 tax ID mapping
# V15: 1=Deductible VAT 10%(purchase), 2=5%(purchase), 3=0%(purchase),
#       4=VAT 10%(sale), 5=VAT 5%(sale), 6=VAT 0%(sale), 7=GTGT 8%(sale), 8=GTGT 8%(purchase)
# V19: 1=10%(purchase), 2=8%(purchase), 3=5%(purchase), 4=0%(purchase), 5=KCT(purchase),
#       11=10%(sale), 12=8%(sale), 13=5%(sale), 14=0%(sale), 15=KCT(sale)
TAX_MAP = {
    1: 1,    # Deductible VAT 10% purchase -> 10% purchase
    2: 3,    # Deductible VAT 5% purchase -> 5% purchase
    3: 4,    # Deductible VAT 0% purchase -> 0% purchase
    4: 11,   # VAT 10% sale -> 10% sale
    5: 13,   # VAT 5% sale -> 5% sale
    6: 14,   # VAT 0% sale -> 0% sale
    7: 12,   # GTGT 8% sale -> 8% sale
    8: 2,    # GTGT 8% purchase -> 8% purchase
}


def sql(db, query):
    cmd = ["docker", "exec", "postgres", "psql", "-U", "odoo", "-d", db, "-t", "-A", "-c", query]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  SQL ERROR: {r.stderr.strip()[:300]}")
        return []
    return [l for l in r.stdout.strip().split("\n") if l.strip()]


def sql_exec(db, query):
    cmd = ["docker", "exec", "postgres", "psql", "-U", "odoo", "-d", db, "-t", "-A", "-c", query]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  SQL ERROR: {r.stderr.strip()[:300]}")
        return False
    return True


def get_v15_taxes(table, rel_table, line_col, id_list):
    """Get V15 tax assignments: {line_id: set(tax_ids)}"""
    rows = sql("taya_db",
        f"SELECT {line_col}, array_agg(account_tax_id ORDER BY account_tax_id) "
        f"FROM {rel_table} WHERE {line_col} IN ({id_list}) GROUP BY {line_col}")
    result = {}
    for row in rows:
        parts = row.split("|")
        if len(parts) >= 2:
            line_id = parts[0]
            tax_str = parts[1].strip("{}")
            taxes = set(int(t) for t in tax_str.split(",") if t.strip())
            result[line_id] = taxes
    return result


def get_v19_taxes(rel_table, line_col, id_list):
    """Get V19 tax assignments: {line_id: set(tax_ids)}"""
    rows = sql("taya19_db",
        f"SELECT {line_col}, array_agg(account_tax_id ORDER BY account_tax_id) "
        f"FROM {rel_table} WHERE {line_col} IN ({id_list}) GROUP BY {line_col}")
    result = {}
    for row in rows:
        parts = row.split("|")
        if len(parts) >= 2:
            line_id = parts[0]
            tax_str = parts[1].strip("{}")
            taxes = set(int(t) for t in tax_str.split(",") if t.strip())
            result[line_id] = taxes
    return result


def fix_order_lines(model_name, v15_table, v19_table, rel_table, line_col, line_map):
    """Fix taxes for order lines."""
    print(f"\n--- {model_name} ---")

    if not line_map:
        print("  No mappings found")
        return 0, 0

    # Get all V15 line IDs
    v15_ids = list(line_map.keys())
    CHUNK = 500
    v15_all_taxes = {}
    for i in range(0, len(v15_ids), CHUNK):
        chunk = v15_ids[i:i + CHUNK]
        id_list = ",".join(chunk)
        taxes = get_v15_taxes(v15_table, rel_table, line_col, id_list)
        v15_all_taxes.update(taxes)

    # Get all V19 line IDs
    v19_ids = [str(line_map[k]) for k in v15_ids]
    v19_all_taxes = {}
    for i in range(0, len(v19_ids), CHUNK):
        chunk = v19_ids[i:i + CHUNK]
        id_list = ",".join(chunk)
        taxes = get_v19_taxes(rel_table, line_col, id_list)
        v19_all_taxes.update(taxes)

    # Compare and build fixes
    to_remove = []  # (v19_line_id, tax_id)
    to_add = []     # (v19_line_id, tax_id)

    for v15_id in v15_ids:
        v19_id = str(line_map[v15_id])
        v15_taxes = v15_all_taxes.get(v15_id, set())
        v19_taxes = v19_all_taxes.get(v19_id, set())

        # Expected V19 taxes based on V15
        expected_v19_taxes = set()
        for v15_tax in v15_taxes:
            v19_tax = TAX_MAP.get(v15_tax)
            if v19_tax:
                expected_v19_taxes.add(v19_tax)

        # Taxes to remove (in V19 but not expected)
        for tax in v19_taxes - expected_v19_taxes:
            to_remove.append((v19_id, tax))

        # Taxes to add (expected but not in V19)
        for tax in expected_v19_taxes - v19_taxes:
            to_add.append((v19_id, tax))

    print(f"  Lines checked: {len(v15_ids)}")
    print(f"  Taxes to remove: {len(to_remove)}")
    print(f"  Taxes to add: {len(to_add)}")

    # Execute removals
    removed = 0
    if to_remove:
        # Group by tax_id for efficiency
        by_tax = defaultdict(list)
        for line_id, tax_id in to_remove:
            by_tax[tax_id].append(line_id)

        for tax_id, line_ids in by_tax.items():
            for i in range(0, len(line_ids), 500):
                chunk = line_ids[i:i + 500]
                id_list = ",".join(chunk)
                if sql_exec("taya19_db",
                    f"DELETE FROM {rel_table} WHERE {line_col} IN ({id_list}) AND account_tax_id = {tax_id}"):
                    removed += len(chunk)

    # Execute additions
    added = 0
    if to_add:
        BATCH = 200
        for i in range(0, len(to_add), BATCH):
            batch = to_add[i:i + BATCH]
            values = ",".join(f"({lid}, {tid})" for lid, tid in batch)
            if sql_exec("taya19_db",
                f"INSERT INTO {rel_table} ({line_col}, account_tax_id) VALUES {values} ON CONFLICT DO NOTHING"):
                added += len(batch)

    print(f"  Removed: {removed}, Added: {added}")
    return removed, added


def recompute_totals_via_sql(id_map):
    """Recompute sale_order and purchase_order totals via SQL."""
    print("\n--- Recomputing sale.order line amounts ---")

    so_line_map = id_map.get("sale.order.line", {})
    v19_sol_ids = [str(v) for v in so_line_map.values()]

    # Recompute sale.order.line price_tax and price_total
    # price_tax = sum of taxes applied to price_subtotal
    # For simplicity, recalculate based on tax rates
    CHUNK = 500
    updated_lines = 0
    for i in range(0, len(v19_sol_ids), CHUNK):
        chunk = v19_sol_ids[i:i + CHUNK]
        id_list = ",".join(chunk)

        # Get line + tax info
        rows = sql("taya19_db",
            f"SELECT sol.id, sol.price_subtotal, "
            f"COALESCE((SELECT SUM(at.amount) FROM account_tax_sale_order_line_rel r "
            f"JOIN account_tax at ON at.id = r.account_tax_id "
            f"WHERE r.sale_order_line_id = sol.id), 0) as tax_pct "
            f"FROM sale_order_line sol WHERE sol.id IN ({id_list})")

        if not rows:
            continue

        cases_tax = []
        cases_total = []
        ids = []
        for row in rows:
            parts = row.split("|")
            if len(parts) >= 3:
                lid = parts[0]
                subtotal = float(parts[1]) if parts[1] else 0
                tax_pct = float(parts[2]) if parts[2] else 0
                price_tax = round(subtotal * tax_pct / 100, 2)
                price_total = round(subtotal + price_tax, 2)
                ids.append(lid)
                cases_tax.append(f"WHEN {lid} THEN {price_tax}")
                cases_total.append(f"WHEN {lid} THEN {price_total}")

        if ids:
            id_list2 = ",".join(ids)
            sql_exec("taya19_db",
                f"UPDATE sale_order_line SET "
                f"price_tax = CASE id {' '.join(cases_tax)} ELSE price_tax END, "
                f"price_total = CASE id {' '.join(cases_total)} ELSE price_total END "
                f"WHERE id IN ({id_list2})")
            updated_lines += len(ids)

    print(f"  Updated {updated_lines} sale.order.line amounts")

    # Recompute sale.order totals
    so_map = id_map.get("sale.order", {})
    v19_so_ids = [str(v) for v in so_map.values()]
    print("\n--- Recomputing sale.order totals ---")
    updated_so = 0
    for i in range(0, len(v19_so_ids), CHUNK):
        chunk = v19_so_ids[i:i + CHUNK]
        id_list = ",".join(chunk)
        sql_exec("taya19_db",
            f"UPDATE sale_order SET "
            f"amount_untaxed = (SELECT COALESCE(SUM(price_subtotal), 0) FROM sale_order_line WHERE order_id = sale_order.id), "
            f"amount_tax = (SELECT COALESCE(SUM(price_tax), 0) FROM sale_order_line WHERE order_id = sale_order.id), "
            f"amount_total = (SELECT COALESCE(SUM(price_total), 0) FROM sale_order_line WHERE order_id = sale_order.id) "
            f"WHERE id IN ({id_list})")
        updated_so += len(chunk)
    print(f"  Updated {updated_so} sale.order totals")

    # Recompute purchase.order.line amounts
    po_line_map = id_map.get("purchase.order.line", {})
    v19_pol_ids = [str(v) for v in po_line_map.values()]
    print("\n--- Recomputing purchase.order.line amounts ---")
    updated_pol = 0
    for i in range(0, len(v19_pol_ids), CHUNK):
        chunk = v19_pol_ids[i:i + CHUNK]
        id_list = ",".join(chunk)

        rows = sql("taya19_db",
            f"SELECT pol.id, pol.price_subtotal, "
            f"COALESCE((SELECT SUM(at.amount) FROM account_tax_purchase_order_line_rel r "
            f"JOIN account_tax at ON at.id = r.account_tax_id "
            f"WHERE r.purchase_order_line_id = pol.id), 0) as tax_pct "
            f"FROM purchase_order_line pol WHERE pol.id IN ({id_list})")

        if not rows:
            continue

        cases_tax = []
        cases_total = []
        ids = []
        for row in rows:
            parts = row.split("|")
            if len(parts) >= 3:
                lid = parts[0]
                subtotal = float(parts[1]) if parts[1] else 0
                tax_pct = float(parts[2]) if parts[2] else 0
                price_tax = round(subtotal * tax_pct / 100, 2)
                price_total = round(subtotal + price_tax, 2)
                ids.append(lid)
                cases_tax.append(f"WHEN {lid} THEN {price_tax}")
                cases_total.append(f"WHEN {lid} THEN {price_total}")

        if ids:
            id_list2 = ",".join(ids)
            sql_exec("taya19_db",
                f"UPDATE purchase_order_line SET "
                f"price_tax = CASE id {' '.join(cases_tax)} ELSE price_tax END, "
                f"price_total = CASE id {' '.join(cases_total)} ELSE price_total END "
                f"WHERE id IN ({id_list2})")
            updated_pol += len(ids)

    print(f"  Updated {updated_pol} purchase.order.line amounts")

    # Recompute purchase.order totals
    po_map = id_map.get("purchase.order", {})
    v19_po_ids = [str(v) for v in po_map.values()]
    print("\n--- Recomputing purchase.order totals ---")
    updated_po = 0
    for i in range(0, len(v19_po_ids), CHUNK):
        chunk = v19_po_ids[i:i + CHUNK]
        id_list = ",".join(chunk)
        sql_exec("taya19_db",
            f"UPDATE purchase_order SET "
            f"amount_untaxed = (SELECT COALESCE(SUM(price_subtotal), 0) FROM purchase_order_line WHERE order_id = purchase_order.id), "
            f"amount_tax = (SELECT COALESCE(SUM(price_tax), 0) FROM purchase_order_line WHERE order_id = purchase_order.id), "
            f"amount_total = (SELECT COALESCE(SUM(price_total), 0) FROM purchase_order_line WHERE order_id = purchase_order.id) "
            f"WHERE id IN ({id_list})")
        updated_po += len(chunk)
    print(f"  Updated {updated_po} purchase.order totals")


def main():
    with open(MAP_FILE) as f:
        id_map = json.load(f)

    # Build line-level maps: {v15_id_str: v19_id}
    sol_map = {k: int(v) for k, v in id_map.get("sale.order.line", {}).items()}
    pol_map = {k: int(v) for k, v in id_map.get("purchase.order.line", {}).items()}

    # Fix sale.order.line taxes
    r1, a1 = fix_order_lines(
        "sale.order.line",
        "sale_order_line",
        "sale_order_line",
        "account_tax_sale_order_line_rel",
        "sale_order_line_id",
        sol_map
    )

    # Fix purchase.order.line taxes
    r2, a2 = fix_order_lines(
        "purchase.order.line",
        "purchase_order_line",
        "purchase_order_line",
        "account_tax_purchase_order_line_rel",
        "purchase_order_line_id",
        pol_map
    )

    print(f"\n{'='*60}")
    print(f"TAX FIX TOTAL: removed {r1+r2}, added {a1+a2}")
    print(f"{'='*60}")

    # Recompute totals
    recompute_totals_via_sql(id_map)

    # Verification
    print(f"\n{'='*60}")
    print("VERIFICATION")
    print(f"{'='*60}")

    # SO tax distribution
    print("\n--- V19 sale.order.line tax distribution ---")
    for row in sql("taya19_db",
        "SELECT t.name, COUNT(*) FROM sale_order_line sol "
        "JOIN account_tax_sale_order_line_rel r ON r.sale_order_line_id = sol.id "
        "JOIN account_tax t ON t.id = r.account_tax_id "
        "GROUP BY t.name ORDER BY COUNT(*) DESC"):
        print(f"  {row}")

    no_tax = sql("taya19_db",
        "SELECT COUNT(*) FROM sale_order_line sol "
        "WHERE NOT EXISTS (SELECT 1 FROM account_tax_sale_order_line_rel r WHERE r.sale_order_line_id = sol.id)")
    print(f"  No tax: {no_tax[0] if no_tax else '?'}")

    # PO tax distribution
    print("\n--- V19 purchase.order.line tax distribution ---")
    for row in sql("taya19_db",
        "SELECT t.name, COUNT(*) FROM purchase_order_line pol "
        "JOIN account_tax_purchase_order_line_rel r ON r.purchase_order_line_id = pol.id "
        "JOIN account_tax t ON t.id = r.account_tax_id "
        "GROUP BY t.name ORDER BY COUNT(*) DESC"):
        print(f"  {row}")

    no_tax = sql("taya19_db",
        "SELECT COUNT(*) FROM purchase_order_line pol "
        "WHERE NOT EXISTS (SELECT 1 FROM account_tax_purchase_order_line_rel r WHERE r.purchase_order_line_id = pol.id)")
    print(f"  No tax: {no_tax[0] if no_tax else '?'}")

    # Financial totals
    print("\n--- Financial totals comparison ---")
    for label, move_type in [("out_invoice", "out_invoice"), ("in_invoice", "in_invoice")]:
        v15 = sql("taya_db", f"SELECT SUM(amount_total) FROM account_move WHERE move_type = '{move_type}'")
        v19 = sql("taya19_db", f"SELECT SUM(amount_total) FROM account_move WHERE move_type = '{move_type}'")
        print(f"  {label}: V15={v15[0] if v15 else '?'} V19={v19[0] if v19 else '?'}")

    for label, table in [("sale.order", "sale_order"), ("purchase.order", "purchase_order")]:
        v15 = sql("taya_db", f"SELECT SUM(amount_total) FROM {table}")
        v19 = sql("taya19_db", f"SELECT SUM(amount_total) FROM {table}")
        print(f"  {label}: V15={v15[0] if v15 else '?'} V19={v19[0] if v19 else '?'}")


if __name__ == "__main__":
    main()
