"""
Fix 222 paid invoices whose receivable/payable AML lines are not in id_map.

These invoices have:
1. Extra tax lines added by V19 auto-tax (not present in V15)
2. Wrong receivable/payable amounts (inflated by auto-tax)
3. No reconciliation records linking invoice to payment
4. payment_state = 'not_paid' (should be 'paid')

Approach:
Phase 1: Fix AML amounts to match V15
  - Restore receivable/payable line to V15 debit/credit values
  - Zero out extra AML lines (lines in V19 that don't match any V15 line)
Phase 2: Create reconciliation records
  - Create partial reconcile (invoice recv ↔ payment credit)
  - Create full reconcile
  - Set amount_residual=0, reconciled=true
  - Set payment_state='paid'
"""
import json
import subprocess
from pathlib import Path
from collections import defaultdict

MAP_FILE = Path(__file__).parent / "migrate" / "id_map.json"


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


def sql_val(db, query):
    rows = sql(db, query)
    return rows[0] if rows else None


def main():
    with open(MAP_FILE) as f:
        id_map = json.load(f)

    aml_map = {k: int(v) for k, v in id_map.get("account.move.line", {}).items()}
    am_map = {k: int(v) for k, v in id_map.get("account.move", {}).items()}
    # Build reverse aml_map: v19_id -> v15_id
    aml_map_rev = {v: int(k) for k, v in aml_map.items()}

    print(f"AML mappings: {len(aml_map)}, AM mappings: {len(am_map)}")

    # =========================================================================
    # Find the 222 unmapped paid invoices
    # =========================================================================
    print("\n=== Finding unmapped paid invoices ===")

    # V15: paid invoices with receivable/payable AMLs
    v15_paid_rows = sql("taya_db", """
        SELECT am.id, am.name, am.move_type, aml.id as recv_aml,
               aml.debit, aml.credit, aml.balance
        FROM account_move am
        JOIN account_move_line aml ON aml.move_id = am.id
        JOIN account_account aa ON aa.id = aml.account_id
        WHERE am.state = 'posted'
        AND am.move_type IN ('out_invoice','out_refund','in_invoice','in_refund')
        AND am.payment_state = 'paid'
        AND aa.internal_type IN ('receivable','payable')
        ORDER BY am.id
    """)

    unmapped_invoices = []
    for r in v15_paid_rows:
        p = r.split("|")
        v15_am_id, name, move_type = p[0], p[1], p[2]
        v15_recv_aml, debit, credit, balance = p[3], p[4], p[5], p[6]

        if v15_recv_aml not in aml_map:
            v19_am_id = am_map.get(v15_am_id)
            if v19_am_id:
                unmapped_invoices.append({
                    "v15_am": int(v15_am_id),
                    "v19_am": v19_am_id,
                    "name": name,
                    "move_type": move_type,
                    "v15_recv_aml": int(v15_recv_aml),
                    "v15_debit": float(debit) if debit else 0,
                    "v15_credit": float(credit) if credit else 0,
                    "v15_balance": float(balance) if balance else 0,
                })

    print(f"Found {len(unmapped_invoices)} unmapped paid invoices")

    # =========================================================================
    # Phase 1: Fix AML amounts
    # =========================================================================
    print("\n=== PHASE 1: Fix AML amounts for unmapped invoices ===")

    # Get V15 AML lines grouped by account for each invoice
    # Get all V15 AML lines for these invoices in one query
    v15_am_ids = ",".join(str(inv["v15_am"]) for inv in unmapped_invoices)
    v15_aml_rows = sql("taya_db", f"""
        SELECT aml.id, aml.move_id, aa.code, aml.debit, aml.credit, aml.balance,
               aa.internal_type
        FROM account_move_line aml
        JOIN account_account aa ON aa.id = aml.account_id
        WHERE aml.move_id IN ({v15_am_ids})
        ORDER BY aml.move_id, aml.id
    """)

    # Build V15 AML data per invoice
    v15_amls_by_move = defaultdict(list)
    for r in v15_aml_rows:
        p = r.split("|")
        v15_amls_by_move[int(p[1])].append({
            "id": int(p[0]),
            "code": p[2],
            "debit": float(p[3]) if p[3] else 0,
            "credit": float(p[4]) if p[4] else 0,
            "balance": float(p[5]) if p[5] else 0,
            "internal_type": p[6],
        })

    # Get V19 AML lines for these invoices
    v19_am_ids = ",".join(str(inv["v19_am"]) for inv in unmapped_invoices)
    v19_aml_rows = sql("taya19_db", f"""
        SELECT aml.id, aml.move_id, aa.code_store, aml.debit, aml.credit,
               aml.balance, aa.account_type, aml.amount_residual
        FROM account_move_line aml
        JOIN account_account aa ON aa.id = aml.account_id
        WHERE aml.move_id IN ({v19_am_ids})
        ORDER BY aml.move_id, aml.id
    """)

    # Build V19 AML data per invoice
    v19_amls_by_move = defaultdict(list)
    for r in v19_aml_rows:
        p = r.split("|")
        # code_store is JSON like {"1": "5111"}, extract the code
        code_raw = p[2]
        # Parse JSON to get code value
        code = ""
        if code_raw and "{" in code_raw:
            try:
                code = list(json.loads(code_raw).values())[0]
            except (json.JSONDecodeError, IndexError):
                code = code_raw
        else:
            code = code_raw

        v19_amls_by_move[int(p[1])].append({
            "id": int(p[0]),
            "code": code,
            "debit": float(p[3]) if p[3] else 0,
            "credit": float(p[4]) if p[4] else 0,
            "balance": float(p[5]) if p[5] else 0,
            "account_type": p[6],
            "amount_residual": float(p[7]) if p[7] else 0,
        })

    # For each invoice, match V15 and V19 lines and compute fixes
    aml_updates = []  # (v19_aml_id, new_debit, new_credit, new_balance, new_residual)
    v19_recv_aml_map = {}  # v15_am_id -> v19_recv_aml_id

    for inv in unmapped_invoices:
        v15_am = inv["v15_am"]
        v19_am = inv["v19_am"]
        v15_lines = v15_amls_by_move.get(v15_am, [])
        v19_lines = v19_amls_by_move.get(v19_am, [])

        if not v15_lines or not v19_lines:
            continue

        # Identify V19 receivable/payable line
        v19_recv = None
        for vl in v19_lines:
            if vl["account_type"] in ("asset_receivable", "liability_payable"):
                v19_recv = vl
                break

        if not v19_recv:
            print(f"  WARNING: No V19 recv line for {inv['name']}")
            continue

        v19_recv_aml_map[v15_am] = v19_recv["id"]

        # Identify V15 receivable/payable line
        v15_recv = None
        for vl in v15_lines:
            if vl["internal_type"] in ("receivable", "payable"):
                v15_recv = vl
                break

        if not v15_recv:
            continue

        # Check if V19 recv needs fixing
        if (abs(v19_recv["debit"] - v15_recv["debit"]) > 0.01 or
                abs(v19_recv["credit"] - v15_recv["credit"]) > 0.01):
            # Fix receivable line to match V15
            aml_updates.append((
                v19_recv["id"],
                v15_recv["debit"],
                v15_recv["credit"],
                v15_recv["balance"],
                0,  # Will be fully reconciled
            ))

        # Match V15 non-recv lines to V19 non-recv lines by account code and amount
        v15_non_recv = [l for l in v15_lines if l["internal_type"] not in ("receivable", "payable")]
        v19_non_recv = [l for l in v19_lines if l["account_type"] not in ("asset_receivable", "liability_payable")]

        # Lines in V19 that are in id_map were already fixed by fix_invoice_taxes.py
        # Lines NOT in id_map need to be matched with V15 by code+amount
        v19_unmapped = [l for l in v19_non_recv if l["id"] not in aml_map_rev]

        # Match by code: for each V15 non-recv line NOT in id_map, find matching V19 line
        v15_non_recv_unmapped = [l for l in v15_non_recv if str(l["id"]) not in aml_map]

        # Create a pool of V15 unmapped lines by code
        v15_by_code = defaultdict(list)
        for l in v15_non_recv_unmapped:
            v15_by_code[l["code"]].append(l)

        # Try to match V19 unmapped lines to V15 unmapped lines
        matched_v19 = set()
        for v19_line in v19_unmapped:
            code = v19_line["code"]
            candidates = v15_by_code.get(code, [])
            # Try exact match first
            found = False
            for i, c in enumerate(candidates):
                if (abs(c["debit"] - v19_line["debit"]) < 0.01 and
                        abs(c["credit"] - v19_line["credit"]) < 0.01):
                    matched_v19.add(v19_line["id"])
                    candidates.pop(i)
                    found = True
                    break
            if not found and candidates:
                # Match by code only; fix amount to V15
                c = candidates.pop(0)
                if (abs(c["debit"] - v19_line["debit"]) > 0.01 or
                        abs(c["credit"] - v19_line["credit"]) > 0.01):
                    aml_updates.append((
                        v19_line["id"],
                        c["debit"],
                        c["credit"],
                        c["balance"],
                        0,
                    ))
                matched_v19.add(v19_line["id"])

        # V19 unmapped lines that don't match any V15 line = EXTRA lines (auto-tax)
        extra_v19 = [l for l in v19_unmapped if l["id"] not in matched_v19]
        for el in extra_v19:
            if el["debit"] != 0 or el["credit"] != 0:
                aml_updates.append((el["id"], 0, 0, 0, 0))

    print(f"AML lines to update: {len(aml_updates)}")

    # Apply AML updates in batches
    if aml_updates:
        for i in range(0, len(aml_updates), 100):
            batch = aml_updates[i:i + 100]
            debit_cases = " ".join(f"WHEN {aid} THEN {d}" for aid, d, c, b, r in batch)
            credit_cases = " ".join(f"WHEN {aid} THEN {c}" for aid, d, c, b, r in batch)
            balance_cases = " ".join(f"WHEN {aid} THEN {b}" for aid, d, c, b, r in batch)
            ids = ",".join(str(aid) for aid, d, c, b, r in batch)
            sql_exec("taya19_db",
                f"UPDATE account_move_line SET "
                f"debit = CASE id {debit_cases} ELSE debit END, "
                f"credit = CASE id {credit_cases} ELSE credit END, "
                f"balance = CASE id {balance_cases} ELSE balance END "
                f"WHERE id IN ({ids})")
        print(f"  Applied {len(aml_updates)} AML line fixes")

    # =========================================================================
    # Phase 2: Create reconciliation records
    # =========================================================================
    print("\n=== PHASE 2: Create reconciliation records ===")

    # Get V15 partial reconcile for these invoices
    v15_apr_data = {}  # v15_am_id -> [(debit_aml, credit_aml, amount, fr_id)]
    for inv in unmapped_invoices:
        v15_recv = inv["v15_recv_aml"]
        apr_rows = sql("taya_db", f"""
            SELECT debit_move_id, credit_move_id, amount, full_reconcile_id,
                   max_date, debit_currency_id, credit_currency_id,
                   debit_amount_currency, credit_amount_currency
            FROM account_partial_reconcile
            WHERE debit_move_id = {v15_recv} OR credit_move_id = {v15_recv}
        """)
        if apr_rows:
            records = []
            for ar in apr_rows:
                p = ar.split("|")
                records.append({
                    "debit_move_id": int(p[0]),
                    "credit_move_id": int(p[1]),
                    "amount": p[2],
                    "full_reconcile_id": int(p[3]) if p[3] else None,
                    "max_date": p[4],
                    "debit_currency_id": p[5] if p[5] else "NULL",
                    "credit_currency_id": p[6] if p[6] else "NULL",
                    "debit_amount_currency": p[7],
                    "credit_amount_currency": p[8],
                })
            v15_apr_data[inv["v15_am"]] = records

    print(f"Invoices with V15 partial reconcile data: {len(v15_apr_data)}")

    # Build V19 partial reconcile records
    # For each V15 partial reconcile:
    #   debit_move_id = V19 recv AML (from v19_recv_aml_map)
    #   credit_move_id = mapped V19 payment AML (from aml_map)
    # Note: debit=invoice receivable, credit=payment credit

    new_apr_records = []
    for inv in unmapped_invoices:
        v15_am = inv["v15_am"]
        v19_recv_id = v19_recv_aml_map.get(v15_am)
        if not v19_recv_id:
            continue

        apr_records = v15_apr_data.get(v15_am, [])
        for rec in apr_records:
            v15_debit = rec["debit_move_id"]
            v15_credit = rec["credit_move_id"]

            # Determine which is the invoice recv and which is the payment
            if v15_debit == inv["v15_recv_aml"]:
                v19_debit = v19_recv_id
                v19_credit = aml_map.get(str(v15_credit))
            else:
                v19_credit = v19_recv_id
                v19_debit = aml_map.get(str(v15_debit))

            if not v19_debit or not v19_credit:
                continue

            new_apr_records.append({
                "debit_move_id": v19_debit,
                "credit_move_id": v19_credit,
                "amount": rec["amount"],
                "max_date": rec["max_date"],
                "debit_currency_id": rec["debit_currency_id"],
                "credit_currency_id": rec["credit_currency_id"],
                "debit_amount_currency": rec["debit_amount_currency"],
                "credit_amount_currency": rec["credit_amount_currency"],
                "v15_am": v15_am,
            })

    print(f"New partial reconcile records to create: {len(new_apr_records)}")

    # Check which already exist in V19
    v19_existing_pairs = set()
    v19_existing = sql("taya19_db", "SELECT debit_move_id, credit_move_id FROM account_partial_reconcile")
    for r in v19_existing:
        p = r.split("|")
        v19_existing_pairs.add((int(p[0]), int(p[1])))

    new_apr_filtered = [
        rec for rec in new_apr_records
        if (rec["debit_move_id"], rec["credit_move_id"]) not in v19_existing_pairs
    ]
    print(f"New partial reconcile after dedup: {len(new_apr_filtered)}")

    # Insert new partial reconcile records
    if new_apr_filtered:
        next_apr_id = int(sql_val("taya19_db", "SELECT COALESCE(MAX(id),0)+1 FROM account_partial_reconcile"))
        inserted = 0
        for i in range(0, len(new_apr_filtered), 50):
            batch = new_apr_filtered[i:i + 50]
            values = []
            for rec in batch:
                values.append(
                    f"({next_apr_id}, {rec['debit_move_id']}, {rec['credit_move_id']}, "
                    f"{rec['amount']}, {rec['debit_amount_currency']}, {rec['credit_amount_currency']}, "
                    f"{rec['debit_currency_id']}, {rec['credit_currency_id']}, "
                    f"1, 1, 1, '{rec['max_date']}', NOW(), NOW())"
                )
                next_apr_id += 1
            vals_str = ",".join(values)
            if sql_exec("taya19_db",
                "INSERT INTO account_partial_reconcile "
                "(id, debit_move_id, credit_move_id, amount, debit_amount_currency, "
                "credit_amount_currency, debit_currency_id, credit_currency_id, "
                "company_id, create_uid, write_uid, max_date, create_date, write_date) "
                f"VALUES {vals_str} ON CONFLICT DO NOTHING"):
                inserted += len(batch)
        print(f"  Inserted {inserted} partial reconcile records")

    # Create full reconcile records for fully reconciled groups
    print("\n--- Creating full reconcile records ---")
    # For each new partial reconcile, create a full reconcile and link
    next_fr_id = int(sql_val("taya19_db", "SELECT COALESCE(MAX(id),0)+1 FROM account_full_reconcile"))

    # Group by invoice (v15_am) to create one full reconcile per invoice
    fr_by_inv = defaultdict(list)  # v15_am -> [apr records]
    for rec in new_apr_filtered:
        fr_by_inv[rec["v15_am"]].append(rec)

    fr_inserts = []
    apr_fr_updates = []  # (v19_debit, v19_credit, fr_id)
    aml_fr_updates = []  # (aml_id, fr_id)

    for v15_am, records in fr_by_inv.items():
        fr_id = next_fr_id
        fr_inserts.append(fr_id)
        next_fr_id += 1

        v19_recv_id = v19_recv_aml_map.get(v15_am)
        if v19_recv_id:
            aml_fr_updates.append((v19_recv_id, fr_id))

        for rec in records:
            apr_fr_updates.append((rec["debit_move_id"], rec["credit_move_id"], fr_id))
            # Also update the payment AML full_reconcile_id
            if rec["debit_move_id"] != v19_recv_id:
                aml_fr_updates.append((rec["debit_move_id"], fr_id))
            if rec["credit_move_id"] != v19_recv_id:
                aml_fr_updates.append((rec["credit_move_id"], fr_id))

    # Insert full reconcile records
    if fr_inserts:
        for i in range(0, len(fr_inserts), 100):
            batch = fr_inserts[i:i + 100]
            values = ",".join(f"({fid}, 1, 1, NOW(), NOW())" for fid in batch)
            sql_exec("taya19_db",
                f"INSERT INTO account_full_reconcile (id, create_uid, write_uid, create_date, write_date) "
                f"VALUES {values} ON CONFLICT DO NOTHING")
        print(f"  Inserted {len(fr_inserts)} full reconcile records")

    # Update partial reconcile with full_reconcile_id
    if apr_fr_updates:
        for i in range(0, len(apr_fr_updates), 100):
            batch = apr_fr_updates[i:i + 100]
            for debit, credit, fr_id in batch:
                sql_exec("taya19_db",
                    f"UPDATE account_partial_reconcile SET full_reconcile_id = {fr_id} "
                    f"WHERE debit_move_id = {debit} AND credit_move_id = {credit}")
        print(f"  Updated {len(apr_fr_updates)} partial reconcile full_reconcile_id")

    # Update AML full_reconcile_id
    if aml_fr_updates:
        for i in range(0, len(aml_fr_updates), 100):
            batch = aml_fr_updates[i:i + 100]
            cases = " ".join(f"WHEN {aid} THEN {fid}" for aid, fid in batch)
            ids = ",".join(str(aid) for aid, _ in batch)
            sql_exec("taya19_db",
                f"UPDATE account_move_line SET full_reconcile_id = CASE id {cases} "
                f"ELSE full_reconcile_id END WHERE id IN ({ids})")
        print(f"  Updated {len(aml_fr_updates)} AML full_reconcile_id")

    # =========================================================================
    # Phase 3: Fix amount_residual and reconciled flag
    # =========================================================================
    print("\n=== PHASE 3: Fix amount_residual, reconciled, payment_state ===")

    # Get all recv AML IDs we just created reconciliation for
    recv_aml_ids = list(v19_recv_aml_map.values())
    # Also collect all payment AMLs involved
    payment_aml_ids = set()
    for rec in new_apr_filtered:
        v19_recv = v19_recv_aml_map.get(rec["v15_am"])
        if rec["debit_move_id"] != v19_recv:
            payment_aml_ids.add(rec["debit_move_id"])
        if rec["credit_move_id"] != v19_recv:
            payment_aml_ids.add(rec["credit_move_id"])

    all_aml_ids = set(recv_aml_ids) | payment_aml_ids

    # Set amount_residual=0, amount_residual_currency=0, reconciled=true
    if all_aml_ids:
        ids_str = ",".join(str(i) for i in all_aml_ids)
        sql_exec("taya19_db",
            f"UPDATE account_move_line SET "
            f"amount_residual = 0, amount_residual_currency = 0, reconciled = true "
            f"WHERE id IN ({ids_str})")
        print(f"  Set amount_residual=0 and reconciled=true on {len(all_aml_ids)} AMLs")

    # Fix payment_state on the invoices
    v19_invoice_ids = [inv["v19_am"] for inv in unmapped_invoices]
    if v19_invoice_ids:
        ids_str = ",".join(str(i) for i in v19_invoice_ids)

        # Recalculate: check if ALL receivable/payable lines have residual=0
        sql_exec("taya19_db", f"""
            UPDATE account_move am SET
                payment_state = CASE
                    WHEN NOT EXISTS (
                        SELECT 1 FROM account_move_line aml
                        JOIN account_account aa ON aa.id = aml.account_id
                        WHERE aml.move_id = am.id
                        AND aa.account_type IN ('asset_receivable','liability_payable')
                        AND aml.amount_residual != 0
                    ) THEN 'paid'
                    ELSE 'not_paid'
                END,
                amount_residual = (
                    SELECT COALESCE(SUM(ABS(aml.amount_residual)), 0)
                    FROM account_move_line aml
                    JOIN account_account aa ON aa.id = aml.account_id
                    WHERE aml.move_id = am.id
                    AND aa.account_type IN ('asset_receivable','liability_payable')
                )
            WHERE am.id IN ({ids_str})
        """)
        # Count results
        paid_count = sql_val("taya19_db",
            f"SELECT COUNT(*) FROM account_move WHERE id IN ({ids_str}) AND payment_state = 'paid'")
        not_paid_count = sql_val("taya19_db",
            f"SELECT COUNT(*) FROM account_move WHERE id IN ({ids_str}) AND payment_state = 'not_paid'")
        print(f"  Payment states updated: paid={paid_count}, not_paid={not_paid_count}")

    # Update sequences
    sql_exec("taya19_db",
        "SELECT setval('account_partial_reconcile_id_seq', "
        "(SELECT COALESCE(MAX(id),1) FROM account_partial_reconcile))")
    sql_exec("taya19_db",
        "SELECT setval('account_full_reconcile_id_seq', "
        "(SELECT COALESCE(MAX(id),1) FROM account_full_reconcile))")
    print("  Sequences updated")

    # =========================================================================
    # VERIFICATION
    # =========================================================================
    print(f"\n{'='*60}")
    print("VERIFICATION")
    print(f"{'='*60}")

    # Payment state comparison
    print("\n--- Payment state distribution ---")
    for label, db in [("V15", "taya_db"), ("V19", "taya19_db")]:
        rows = sql(db,
            "SELECT payment_state, COUNT(*) FROM account_move "
            "WHERE move_type IN ('out_invoice','out_refund','in_invoice','in_refund') "
            "AND state = 'posted' GROUP BY payment_state ORDER BY payment_state")
        print(f"  {label}: {', '.join(rows)}")

    # Reconciliation counts
    print("\n--- Reconciliation record counts ---")
    for label, db in [("V15", "taya_db"), ("V19", "taya19_db")]:
        apr = sql_val(db, "SELECT COUNT(*) FROM account_partial_reconcile")
        afr = sql_val(db, "SELECT COUNT(*) FROM account_full_reconcile")
        rec = sql_val(db, "SELECT COUNT(*) FROM account_move_line WHERE reconciled = true")
        print(f"  {label}: partial={apr}, full={afr}, reconciled_lines={rec}")

    # Open receivable/payable balance
    print("\n--- Open receivable/payable balance ---")
    v15_bal = sql("taya_db", """
        SELECT aa.code, SUM(aml.amount_residual)
        FROM account_move_line aml
        JOIN account_account aa ON aa.id = aml.account_id
        WHERE aa.internal_type IN ('receivable','payable')
        GROUP BY aa.code HAVING SUM(aml.amount_residual) != 0 ORDER BY aa.code
    """)
    v19_bal = sql("taya19_db", """
        SELECT aa.code_store, SUM(aml.amount_residual)
        FROM account_move_line aml
        JOIN account_account aa ON aa.id = aml.account_id
        WHERE aa.account_type IN ('asset_receivable','liability_payable')
        GROUP BY aa.code_store HAVING SUM(aml.amount_residual) != 0 ORDER BY aa.code_store
    """)
    for row in v15_bal:
        print(f"  V15: {row}")
    for row in v19_bal:
        print(f"  V19: {row}")

    # Spot check
    print("\n--- Spot check ---")
    for name in ["HD/2022/00003", "HD/2024/00125", "HD/2025/00019"]:
        for label, db in [("V15", "taya_db"), ("V19", "taya19_db")]:
            row = sql(db, f"SELECT name, amount_total, amount_residual, payment_state "
                         f"FROM account_move WHERE name = '{name}'")
            if row:
                print(f"  {label} {row[0]}")


if __name__ == "__main__":
    main()
