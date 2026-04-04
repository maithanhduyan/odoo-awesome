"""
Fix taxes on account.move.line and recompute invoice totals.
Same approach as fix_taxes.py but for account_move_line.
"""
import json
import subprocess
from pathlib import Path
from collections import defaultdict

MAP_FILE = Path(__file__).parent / "migrate" / "id_map.json"

TAX_MAP = {
    1: 1, 2: 3, 3: 4, 4: 11, 5: 13, 6: 14, 7: 12, 8: 2,
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


def main():
    with open(MAP_FILE) as f:
        id_map = json.load(f)

    aml_map = {k: int(v) for k, v in id_map.get("account.move.line", {}).items()}
    print(f"account.move.line mappings: {len(aml_map)}")

    v15_ids = list(aml_map.keys())
    CHUNK = 500

    # Get V15 taxes
    v15_taxes = {}  # v15_id -> set(tax_ids)
    for i in range(0, len(v15_ids), CHUNK):
        chunk = v15_ids[i:i + CHUNK]
        id_list = ",".join(chunk)
        rows = sql("taya_db",
            f"SELECT account_move_line_id, array_agg(account_tax_id) "
            f"FROM account_move_line_account_tax_rel "
            f"WHERE account_move_line_id IN ({id_list}) GROUP BY account_move_line_id")
        for row in rows:
            parts = row.split("|")
            if len(parts) >= 2:
                lid = parts[0]
                tax_str = parts[1].strip("{}")
                taxes = set(int(t) for t in tax_str.split(",") if t.strip())
                v15_taxes[lid] = taxes

    # Get V19 taxes
    v19_ids = [str(aml_map[k]) for k in v15_ids]
    v19_taxes = {}
    for i in range(0, len(v19_ids), CHUNK):
        chunk = v19_ids[i:i + CHUNK]
        id_list = ",".join(chunk)
        rows = sql("taya19_db",
            f"SELECT account_move_line_id, array_agg(account_tax_id) "
            f"FROM account_move_line_account_tax_rel "
            f"WHERE account_move_line_id IN ({id_list}) GROUP BY account_move_line_id")
        for row in rows:
            parts = row.split("|")
            if len(parts) >= 2:
                lid = parts[0]
                tax_str = parts[1].strip("{}")
                taxes = set(int(t) for t in tax_str.split(",") if t.strip())
                v19_taxes[lid] = taxes

    # Compare
    to_remove = []
    to_add = []
    for v15_id in v15_ids:
        v19_id = str(aml_map[v15_id])
        v15_t = v15_taxes.get(v15_id, set())
        v19_t = v19_taxes.get(v19_id, set())

        expected = set()
        for t in v15_t:
            mapped = TAX_MAP.get(t)
            if mapped:
                expected.add(mapped)

        for t in v19_t - expected:
            to_remove.append((v19_id, t))
        for t in expected - v19_t:
            to_add.append((v19_id, t))

    print(f"Taxes to remove: {len(to_remove)}")
    print(f"Taxes to add: {len(to_add)}")

    # Remove
    removed = 0
    by_tax = defaultdict(list)
    for lid, tid in to_remove:
        by_tax[tid].append(lid)
    for tid, lids in by_tax.items():
        for i in range(0, len(lids), 500):
            chunk = lids[i:i + 500]
            id_list = ",".join(chunk)
            if sql_exec("taya19_db",
                f"DELETE FROM account_move_line_account_tax_rel "
                f"WHERE account_move_line_id IN ({id_list}) AND account_tax_id = {tid}"):
                removed += len(chunk)

    # Add
    added = 0
    for i in range(0, len(to_add), 200):
        batch = to_add[i:i + 200]
        values = ",".join(f"({lid}, {tid})" for lid, tid in batch)
        if sql_exec("taya19_db",
            f"INSERT INTO account_move_line_account_tax_rel (account_move_line_id, account_tax_id) "
            f"VALUES {values} ON CONFLICT DO NOTHING"):
            added += len(batch)

    print(f"Removed: {removed}, Added: {added}")

    # Now fix the tax_line_id on tax lines — this is complex.
    # Instead, let's fix the amount fields on account.move directly from V15.
    print("\n--- Fixing account.move amount fields from V15 ---")
    am_map = id_map.get("account.move", {})
    v15_am_ids = list(am_map.keys())
    updated = 0
    SMALL = 100  # smaller batch for Windows cmd line limit

    for i in range(0, len(v15_am_ids), SMALL):
        chunk = v15_am_ids[i:i + SMALL]
        id_list = ",".join(chunk)
        rows = sql("taya_db",
            f"SELECT id, amount_untaxed, amount_tax, amount_total, amount_residual "
            f"FROM account_move WHERE id IN ({id_list})")

        if not rows:
            continue

        cases_untaxed = []
        cases_tax = []
        cases_total = []
        cases_residual = []
        ids = []

        for row in rows:
            parts = row.split("|")
            if len(parts) >= 5:
                v15_id = parts[0]
                v19_id = am_map.get(v15_id)
                if not v19_id:
                    continue
                ids.append(str(v19_id))
                cases_untaxed.append(f"WHEN {v19_id} THEN {parts[1]}")
                cases_tax.append(f"WHEN {v19_id} THEN {parts[2]}")
                cases_total.append(f"WHEN {v19_id} THEN {parts[3]}")
                cases_residual.append(f"WHEN {v19_id} THEN {parts[4]}")

        if not ids:
            continue

        id_list2 = ",".join(ids)
        sql_exec("taya19_db",
            f"UPDATE account_move SET "
            f"amount_untaxed = CASE id {' '.join(cases_untaxed)} ELSE amount_untaxed END, "
            f"amount_tax = CASE id {' '.join(cases_tax)} ELSE amount_tax END, "
            f"amount_total = CASE id {' '.join(cases_total)} ELSE amount_total END, "
            f"amount_residual = CASE id {' '.join(cases_residual)} ELSE amount_residual END "
            f"WHERE id IN ({id_list2})")
        updated += len(ids)

    print(f"Updated {updated} account.move amount fields")

    # Also fix account.move.line debit/credit/balance from V15
    print("\n--- Fixing account.move.line debit/credit/balance from V15 ---")
    aml_updated = 0
    for i in range(0, len(v15_ids), CHUNK):
        chunk = v15_ids[i:i + CHUNK]
        id_list = ",".join(chunk)
        rows = sql("taya_db",
            f"SELECT id, debit, credit, balance, amount_currency, price_total, price_subtotal "
            f"FROM account_move_line WHERE id IN ({id_list})")

        if not rows:
            continue

        cases_debit = []
        cases_credit = []
        cases_balance = []
        cases_amount_currency = []
        cases_price_total = []
        cases_price_subtotal = []
        ids = []

        for row in rows:
            parts = row.split("|")
            if len(parts) >= 7:
                v15_id = parts[0]
                v19_id = aml_map.get(v15_id)
                if not v19_id:
                    continue
                # Handle empty/NULL values - default to 0
                debit = parts[1] if parts[1].strip() else '0'
                credit = parts[2] if parts[2].strip() else '0'
                balance = parts[3] if parts[3].strip() else '0'
                amt_cur = parts[4] if parts[4].strip() else '0'
                p_total = parts[5] if parts[5].strip() else '0'
                p_sub = parts[6] if parts[6].strip() else '0'
                ids.append(str(v19_id))
                cases_debit.append(f"WHEN {v19_id} THEN {debit}")
                cases_credit.append(f"WHEN {v19_id} THEN {credit}")
                cases_balance.append(f"WHEN {v19_id} THEN {balance}")
                cases_amount_currency.append(f"WHEN {v19_id} THEN {amt_cur}")
                cases_price_total.append(f"WHEN {v19_id} THEN {p_total}")
                cases_price_subtotal.append(f"WHEN {v19_id} THEN {p_sub}")

        if not ids:
            continue

        # Process in sub-batches of 80 for Windows cmd line limit (6 CASE cols)
        SUB = 80
        for j in range(0, len(ids), SUB):
            sub_ids = ids[j:j + SUB]
            sub_debit = cases_debit[j:j + SUB]
            sub_credit = cases_credit[j:j + SUB]
            sub_balance = cases_balance[j:j + SUB]
            sub_amount = cases_amount_currency[j:j + SUB]
            sub_pt = cases_price_total[j:j + SUB]
            sub_ps = cases_price_subtotal[j:j + SUB]

            id_list2 = ",".join(sub_ids)
            sql_exec("taya19_db",
                f"UPDATE account_move_line SET "
                f"debit = CASE id {' '.join(sub_debit)} ELSE debit END, "
                f"credit = CASE id {' '.join(sub_credit)} ELSE credit END, "
                f"balance = CASE id {' '.join(sub_balance)} ELSE balance END, "
                f"amount_currency = CASE id {' '.join(sub_amount)} ELSE amount_currency END, "
                f"price_total = CASE id {' '.join(sub_pt)} ELSE price_total END, "
                f"price_subtotal = CASE id {' '.join(sub_ps)} ELSE price_subtotal END "
                f"WHERE id IN ({id_list2})")
            aml_updated += len(sub_ids)

    print(f"Updated {aml_updated} account.move.line amounts")

    # Verification
    print(f"\n{'='*60}")
    print("VERIFICATION")
    print(f"{'='*60}")

    for label, mt in [("out_invoice", "out_invoice"), ("out_refund", "out_refund"),
                       ("in_invoice", "in_invoice"), ("in_refund", "in_refund")]:
        v15 = sql("taya_db", f"SELECT COALESCE(SUM(amount_total),0) FROM account_move WHERE move_type='{mt}'")
        v19 = sql("taya19_db", f"SELECT COALESCE(SUM(amount_total),0) FROM account_move WHERE move_type='{mt}'")
        v15_f = float(v15[0]) if v15 else 0
        v19_f = float(v19[0]) if v19 else 0
        diff = v19_f - v15_f
        print(f"  {label}: V15={v15_f:,.0f} V19={v19_f:,.0f} diff={diff:+,.0f}")

    for label, table in [("sale.order", "sale_order"), ("purchase.order", "purchase_order")]:
        v15 = sql("taya_db", f"SELECT COALESCE(SUM(amount_total),0) FROM {table}")
        v19 = sql("taya19_db", f"SELECT COALESCE(SUM(amount_total),0) FROM {table}")
        v15_f = float(v15[0]) if v15 else 0
        v19_f = float(v19[0]) if v19 else 0
        diff = v19_f - v15_f
        print(f"  {label}: V15={v15_f:,.0f} V19={v19_f:,.0f} diff={diff:+,.0f}")

    # AML tax distribution
    print("\n--- V19 AML tax distribution (customer invoices) ---")
    for row in sql("taya19_db",
        "SELECT t.name, COUNT(*) FROM account_move_line aml "
        "JOIN account_move_line_account_tax_rel r ON r.account_move_line_id = aml.id "
        "JOIN account_tax t ON t.id = r.account_tax_id "
        "JOIN account_move am ON am.id = aml.move_id "
        "WHERE am.move_type IN ('out_invoice','out_refund') "
        "GROUP BY t.name ORDER BY COUNT(*) DESC"):
        print(f"  {row}")


if __name__ == "__main__":
    main()
