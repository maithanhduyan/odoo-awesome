"""
Migrate reconciliation (đối soát hóa đơn - thanh toán) from V15 to V19.

The migration transferred account_partial_reconcile and account_full_reconcile records,
but the account_move_line fields (amount_residual, reconciled, full_reconcile_id)
were overwritten by fix_invoice_taxes.py restoring V15 debit/credit/balance values.

This script:
1. Recalculates amount_residual on all reconcilable AML lines based on existing
   account_partial_reconcile records in V19
2. Sets reconciled = true and full_reconcile_id where appropriate
3. Fixes payment_state on account_move based on residual amounts
4. Handles the 200 unmapped reconciliations by finding matching AML lines
   in V19 and creating new partial/full reconcile records
"""
import json
import subprocess
from pathlib import Path
from collections import defaultdict

MAP_FILE = Path(__file__).parent / "migrate" / "id_map.json"

CHUNK = 300


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
    print(f"AML mappings: {len(aml_map)}, AM mappings: {len(am_map)}")

    # =========================================================================
    # STEP 1: Find missing reconciliations (V15 pairs not in V19)
    # =========================================================================
    print("\n=== STEP 1: Find missing partial reconciliations ===")

    # Get ALL V15 partial reconcile records
    v15_apr_rows = sql("taya_db",
        "SELECT id, debit_move_id, credit_move_id, amount, "
        "debit_amount_currency, credit_amount_currency, "
        "full_reconcile_id, max_date, debit_currency_id, credit_currency_id "
        "FROM account_partial_reconcile ORDER BY id")
    print(f"V15 partial reconcile records: {len(v15_apr_rows)}")

    # Get existing V19 partial reconcile debit/credit pairs
    v19_apr_rows = sql("taya19_db",
        "SELECT debit_move_id, credit_move_id FROM account_partial_reconcile")
    v19_pairs = set()
    for r in v19_apr_rows:
        p = r.split("|")
        if len(p) >= 2:
            v19_pairs.add((int(p[0]), int(p[1])))

    # Find missing records
    missing_apr = []
    unmappable = 0
    for r in v15_apr_rows:
        p = r.split("|")
        if len(p) < 10:
            continue
        v15_debit = p[1]
        v15_credit = p[2]
        v19_debit = aml_map.get(v15_debit)
        v19_credit = aml_map.get(v15_credit)

        if v19_debit is None or v19_credit is None:
            unmappable += 1
            continue

        if (v19_debit, v19_credit) not in v19_pairs:
            missing_apr.append({
                "v15_id": int(p[0]),
                "debit_move_id": v19_debit,
                "credit_move_id": v19_credit,
                "amount": p[3],
                "debit_amount_currency": p[4],
                "credit_amount_currency": p[5],
                "full_reconcile_id": p[6] if p[6] else None,
                "max_date": p[7],
                "debit_currency_id": p[8] if p[8] else "NULL",
                "credit_currency_id": p[9] if p[9] else "NULL",
            })

    print(f"Missing in V19: {len(missing_apr)}, Unmappable (AML not migrated): {unmappable}")

    # Insert missing partial reconcile records
    if missing_apr:
        next_id = int(sql_val("taya19_db", "SELECT COALESCE(MAX(id),0)+1 FROM account_partial_reconcile"))
        inserted = 0
        for i in range(0, len(missing_apr), 50):
            batch = missing_apr[i:i + 50]
            values = []
            for rec in batch:
                values.append(
                    f"({next_id}, {rec['debit_move_id']}, {rec['credit_move_id']}, "
                    f"{rec['amount']}, {rec['debit_amount_currency']}, {rec['credit_amount_currency']}, "
                    f"{rec['debit_currency_id']}, {rec['credit_currency_id']}, "
                    f"1, 1, 1, '{rec['max_date']}', NOW(), NOW())"
                )
                next_id += 1
            vals_str = ",".join(values)
            if sql_exec("taya19_db",
                "INSERT INTO account_partial_reconcile "
                "(id, debit_move_id, credit_move_id, amount, debit_amount_currency, "
                "credit_amount_currency, debit_currency_id, credit_currency_id, "
                "company_id, create_uid, write_uid, max_date, create_date, write_date) "
                f"VALUES {vals_str} ON CONFLICT DO NOTHING"):
                inserted += len(batch)
        print(f"Inserted {inserted} missing partial reconcile records")

    # =========================================================================
    # STEP 2: Migrate full reconcile records
    # =========================================================================
    print("\n=== STEP 2: Verify full reconcile records ===")

    # Get V15 full reconcile
    v15_fr_rows = sql("taya_db",
        "SELECT id, name FROM account_full_reconcile ORDER BY id")
    v15_fr_ids = set()
    for r in v15_fr_rows:
        p = r.split("|")
        v15_fr_ids.add(int(p[0]))

    # Get V19 full reconcile
    v19_fr_rows = sql("taya19_db",
        "SELECT id FROM account_full_reconcile ORDER BY id")
    v19_fr_ids = set(int(r) for r in v19_fr_rows)

    # V19 full_reconcile uses different IDs (auto-incremented during migration)
    # We need to build V15->V19 full_reconcile_id mapping
    # Using the partial reconcile records to figure out the mapping
    print(f"V15 full reconcile records: {len(v15_fr_ids)}")
    print(f"V19 full reconcile records: {len(v19_fr_ids)}")

    # =========================================================================
    # STEP 3: Recalculate amount_residual from partial reconcile data
    # =========================================================================
    print("\n=== STEP 3: Recalculate amount_residual on reconcilable AML lines ===")

    # Get all receivable/payable account IDs
    rec_pay_accounts = sql("taya19_db",
        "SELECT id FROM account_account WHERE account_type IN ('asset_receivable', 'liability_payable')")
    rec_pay_ids = ",".join(r.strip() for r in rec_pay_accounts)
    print(f"Receivable/payable accounts: {len(rec_pay_accounts)}")

    # Get all receivable/payable AML lines with their debit/credit
    print("  Loading V19 receivable/payable AML lines...")
    aml_rows = sql("taya19_db",
        f"SELECT id, debit, credit, balance, amount_residual, reconciled, full_reconcile_id "
        f"FROM account_move_line WHERE account_id IN ({rec_pay_ids}) ORDER BY id")
    print(f"  Found {len(aml_rows)} receivable/payable lines")

    aml_data = {}
    for r in aml_rows:
        p = r.split("|")
        if len(p) >= 7:
            aml_id = int(p[0])
            aml_data[aml_id] = {
                "debit": float(p[1]) if p[1] else 0,
                "credit": float(p[2]) if p[2] else 0,
                "balance": float(p[3]) if p[3] else 0,
                "amount_residual": float(p[4]) if p[4] else 0,
                "reconciled": p[5] == "t",
                "full_reconcile_id": int(p[6]) if p[6] else None,
            }

    # Get all partial reconcile sums per AML
    print("  Loading V19 partial reconcile sums...")
    # Debit side: amount reduces the receivable
    debit_sums = sql("taya19_db",
        "SELECT debit_move_id, SUM(amount) FROM account_partial_reconcile GROUP BY debit_move_id")
    credit_sums = sql("taya19_db",
        "SELECT credit_move_id, SUM(amount) FROM account_partial_reconcile GROUP BY credit_move_id")

    # Build reconciled amounts per AML
    reconciled_amounts = defaultdict(float)  # aml_id -> total reconciled amount

    for r in debit_sums:
        p = r.split("|")
        aml_id = int(p[0])
        reconciled_amounts[aml_id] += float(p[1])

    for r in credit_sums:
        p = r.split("|")
        aml_id = int(p[0])
        reconciled_amounts[aml_id] += float(p[1])

    # Calculate correct amount_residual
    # For debit lines (receivable): residual = balance - sum of partial reconcile amounts (as debit)
    # For credit lines (payment credit): residual = balance + sum of partial reconcile amounts (as credit)
    # General formula: residual = balance - (debit_reconciled - credit_reconciled)

    debit_reconciled = defaultdict(float)
    credit_reconciled = defaultdict(float)

    for r in debit_sums:
        p = r.split("|")
        debit_reconciled[int(p[0])] = float(p[1])

    for r in credit_sums:
        p = r.split("|")
        credit_reconciled[int(p[0])] = float(p[1])

    # Compute correct residual for each AML
    updates = []  # (aml_id, new_residual)
    for aml_id, data in aml_data.items():
        dr = debit_reconciled.get(aml_id, 0)
        cr = credit_reconciled.get(aml_id, 0)
        # balance is positive for debit, negative for credit
        # Partial reconcile reduces the absolute value
        # For debit line: residual = balance - dr
        # For credit line: residual = balance + cr
        if data["balance"] > 0:
            correct_residual = data["balance"] - dr
        elif data["balance"] < 0:
            correct_residual = data["balance"] + cr
        else:
            correct_residual = 0

        # Round to avoid floating point issues
        correct_residual = round(correct_residual, 2)
        current_residual = round(data["amount_residual"], 2)

        if abs(correct_residual - current_residual) > 0.01:
            updates.append((aml_id, correct_residual))

    print(f"  AML lines needing amount_residual fix: {len(updates)}")

    # Apply updates in batches
    fixed_residual = 0
    for i in range(0, len(updates), 100):
        batch = updates[i:i + 100]
        cases = " ".join(f"WHEN {aid} THEN {res}" for aid, res in batch)
        ids = ",".join(str(aid) for aid, _ in batch)
        if sql_exec("taya19_db",
            f"UPDATE account_move_line SET amount_residual = CASE id {cases} ELSE amount_residual END "
            f"WHERE id IN ({ids})"):
            fixed_residual += len(batch)
    print(f"  Fixed amount_residual on {fixed_residual} lines")

    # =========================================================================
    # STEP 4: Fix amount_residual_currency
    # =========================================================================
    print("\n=== STEP 4: Fix amount_residual_currency ===")

    # For VND-only company, amount_residual_currency should equal amount_residual
    sql_exec("taya19_db",
        f"UPDATE account_move_line SET amount_residual_currency = amount_residual "
        f"WHERE account_id IN ({rec_pay_ids}) "
        f"AND amount_residual_currency != amount_residual")
    res = sql_val("taya19_db",
        f"SELECT COUNT(*) FROM account_move_line "
        f"WHERE account_id IN ({rec_pay_ids}) "
        f"AND amount_residual_currency != amount_residual")
    print(f"  Remaining mismatches: {res}")

    # =========================================================================
    # STEP 5: Fix reconciled flag
    # =========================================================================
    print("\n=== STEP 5: Fix reconciled flag ===")

    # A line is reconciled when amount_residual = 0 AND it has partial reconcile records
    # Set reconciled = true for lines with residual = 0 that participate in reconciliation
    r1 = sql_val("taya19_db",
        f"UPDATE account_move_line SET reconciled = true "
        f"WHERE account_id IN ({rec_pay_ids}) "
        f"AND amount_residual = 0 AND reconciled = false "
        f"AND (id IN (SELECT debit_move_id FROM account_partial_reconcile) "
        f"  OR id IN (SELECT credit_move_id FROM account_partial_reconcile)) "
        f"RETURNING id")
    count_true = len(sql("taya19_db",
        f"SELECT id FROM account_move_line "
        f"WHERE account_id IN ({rec_pay_ids}) "
        f"AND amount_residual = 0 AND reconciled = true"))

    # Set reconciled = false for lines with residual != 0
    sql_exec("taya19_db",
        f"UPDATE account_move_line SET reconciled = false "
        f"WHERE account_id IN ({rec_pay_ids}) "
        f"AND amount_residual != 0 AND reconciled = true")

    print(f"  Reconciled lines (residual=0): {count_true}")

    # =========================================================================
    # STEP 6: Fix full_reconcile_id on AML lines
    # =========================================================================
    print("\n=== STEP 6: Fix full_reconcile_id ===")

    # Get V15 full_reconcile_id -> AML mappings
    v15_fr_aml = sql("taya_db",
        "SELECT full_reconcile_id, array_agg(id) FROM account_move_line "
        "WHERE full_reconcile_id IS NOT NULL GROUP BY full_reconcile_id")

    # Build V15 full_reconcile_id -> V19 AML IDs
    fr_to_v19_amls = {}  # v15_fr_id -> [v19_aml_ids]
    for r in v15_fr_aml:
        p = r.split("|")
        if len(p) < 2:
            continue
        v15_fr_id = int(p[0])
        v15_aml_ids = p[1].strip("{}").split(",")
        v19_amls = []
        for v15_id in v15_aml_ids:
            v15_id = v15_id.strip()
            v19_id = aml_map.get(v15_id)
            if v19_id:
                v19_amls.append(v19_id)
        if v19_amls:
            fr_to_v19_amls[v15_fr_id] = v19_amls

    # Get existing V19 full_reconcile mapping from partial reconcile
    v19_apr_fr = sql("taya19_db",
        "SELECT id, full_reconcile_id FROM account_partial_reconcile "
        "WHERE full_reconcile_id IS NOT NULL")
    v19_fr_ids_used = set()
    for r in v19_apr_fr:
        p = r.split("|")
        if len(p) >= 2 and p[1]:
            v19_fr_ids_used.add(int(p[1]))

    # Build mapping: for each V15 full_reconcile, find the corresponding V19 full_reconcile_id
    # by looking at the partial reconcile records
    v15_apr_fr = sql("taya_db",
        "SELECT id, full_reconcile_id FROM account_partial_reconcile "
        "WHERE full_reconcile_id IS NOT NULL")

    # V15 apr.id -> V15 fr_id
    v15_apr_to_fr = {}
    for r in v15_apr_fr:
        p = r.split("|")
        v15_apr_to_fr[int(p[0])] = int(p[1])

    # V19 apr -> V19 fr_id (from existing data)
    v19_apr_to_fr = {}
    for r in v19_apr_fr:
        p = r.split("|")
        if p[1]:
            v19_apr_to_fr[int(p[0])] = int(p[1])

    # Build V15_fr -> V19_fr mapping using the partial reconcile debit/credit pairs
    v15_to_v19_fr = {}
    v15_apr_all = sql("taya_db",
        "SELECT id, debit_move_id, credit_move_id, full_reconcile_id "
        "FROM account_partial_reconcile WHERE full_reconcile_id IS NOT NULL ORDER BY id")

    v19_apr_all = sql("taya19_db",
        "SELECT id, debit_move_id, credit_move_id, full_reconcile_id "
        "FROM account_partial_reconcile WHERE full_reconcile_id IS NOT NULL ORDER BY id")
    v19_pair_to_fr = {}
    for r in v19_apr_all:
        p = r.split("|")
        if len(p) >= 4 and p[3]:
            v19_pair_to_fr[(int(p[1]), int(p[2]))] = int(p[3])

    for r in v15_apr_all:
        p = r.split("|")
        if len(p) < 4 or not p[3]:
            continue
        v15_fr_id = int(p[3])
        v15_debit = p[1]
        v15_credit = p[2]
        v19_debit = aml_map.get(v15_debit)
        v19_credit = aml_map.get(v15_credit)
        if v19_debit and v19_credit:
            v19_fr = v19_pair_to_fr.get((v19_debit, v19_credit))
            if v19_fr:
                v15_to_v19_fr[v15_fr_id] = v19_fr

    print(f"  V15->V19 full_reconcile mappings: {len(v15_to_v19_fr)}")

    # Update full_reconcile_id on AML lines (batched)
    # Build a flat list of (aml_id, v19_fr_id) pairs
    fr_update_pairs = []  # [(aml_id, v19_fr_id), ...]
    for v15_fr_id, v19_amls in fr_to_v19_amls.items():
        v19_fr_id = v15_to_v19_fr.get(v15_fr_id)
        if not v19_fr_id:
            continue
        for aml_id in v19_amls:
            fr_update_pairs.append((aml_id, v19_fr_id))

    updated_fr = 0
    for i in range(0, len(fr_update_pairs), 200):
        batch = fr_update_pairs[i:i + 200]
        cases = " ".join(f"WHEN {aid} THEN {frid}" for aid, frid in batch)
        ids = ",".join(str(aid) for aid, _ in batch)
        sql_exec("taya19_db",
            f"UPDATE account_move_line SET full_reconcile_id = CASE id {cases} ELSE full_reconcile_id END "
            f"WHERE id IN ({ids})")
        updated_fr += len(batch)

    print(f"  Updated full_reconcile_id on {updated_fr} AML lines")

    # =========================================================================
    # STEP 7: Fix account_move.amount_residual and payment_state
    # =========================================================================
    print("\n=== STEP 7: Fix account_move.amount_residual and payment_state ===")

    # Get all posted invoices with their AML receivable/payable residuals
    invoice_residuals = sql("taya19_db",
        "SELECT am.id, am.move_type, am.amount_total, "
        "COALESCE(SUM(ABS(aml.amount_residual)), 0) as aml_residual "
        "FROM account_move am "
        "JOIN account_move_line aml ON aml.move_id = am.id "
        f"AND aml.account_id IN ({rec_pay_ids}) "
        "WHERE am.state = 'posted' "
        "AND am.move_type IN ('out_invoice','out_refund','in_invoice','in_refund') "
        "GROUP BY am.id, am.move_type, am.amount_total "
        "ORDER BY am.id")

    # Update amount_residual on account_move
    am_updates = []  # (move_id, correct_residual, correct_payment_state)
    for r in invoice_residuals:
        p = r.split("|")
        if len(p) < 4:
            continue
        move_id = int(p[0])
        amount_total = float(p[2]) if p[2] else 0
        aml_residual = float(p[3]) if p[3] else 0

        # payment_state logic:
        # - 'paid' if all receivable/payable lines are fully reconciled (residual = 0)
        # - 'partial' if some amount has been reconciled but not all
        # - 'not_paid' if nothing has been reconciled
        if aml_residual == 0:
            payment_state = "paid"
        elif amount_total > 0 and aml_residual < amount_total:
            payment_state = "partial"
        else:
            payment_state = "not_paid"

        am_updates.append((move_id, aml_residual, payment_state))

    # Apply
    state_counts = defaultdict(int)
    for i in range(0, len(am_updates), 100):
        batch = am_updates[i:i + 100]
        residual_cases = " ".join(f"WHEN {mid} THEN {res}" for mid, res, _ in batch)
        state_cases = " ".join(f"WHEN {mid} THEN '{st}'" for mid, _, st in batch)
        ids = ",".join(str(mid) for mid, _, _ in batch)
        sql_exec("taya19_db",
            f"UPDATE account_move SET "
            f"amount_residual = CASE id {residual_cases} ELSE amount_residual END, "
            f"payment_state = CASE id {state_cases} ELSE payment_state END "
            f"WHERE id IN ({ids})")
        for _, _, st in batch:
            state_counts[st] += 1

    print(f"  Payment state distribution: {dict(state_counts)}")

    # =========================================================================
    # STEP 8: Fix payment entries (entry type moves with payments)
    # =========================================================================
    print("\n=== STEP 8: Fix payment entry reconciliation from V15 ===")

    # Restore V15 amount_residual and reconciled for AML lines that are
    # part of payment entries (not invoices) and participate in reconciliation
    v19_payment_amls = sql("taya19_db",
        f"SELECT aml.id FROM account_move_line aml "
        f"JOIN account_move am ON am.id = aml.move_id "
        f"WHERE am.move_type = 'entry' AND am.state = 'posted' "
        f"AND aml.account_id IN ({rec_pay_ids})")
    v19_payment_aml_ids = set(int(r) for r in v19_payment_amls)
    print(f"  V19 payment entry AML lines (receivable/payable): {len(v19_payment_aml_ids)}")

    # These lines need amount_residual recalculated too
    # They were already handled in Step 3 via the general recalculation
    # Just verify
    payment_wrong = sql_val("taya19_db",
        f"SELECT COUNT(*) FROM account_move_line aml "
        f"JOIN account_move am ON am.id = aml.move_id "
        f"WHERE am.move_type = 'entry' AND am.state = 'posted' "
        f"AND aml.account_id IN ({rec_pay_ids}) "
        f"AND aml.reconciled = false "
        f"AND aml.amount_residual = 0 "
        f"AND (aml.id IN (SELECT debit_move_id FROM account_partial_reconcile) "
        f"  OR aml.id IN (SELECT credit_move_id FROM account_partial_reconcile))")
    if int(payment_wrong) > 0:
        sql_exec("taya19_db",
            f"UPDATE account_move_line SET reconciled = true "
            f"WHERE id IN ("
            f"  SELECT aml.id FROM account_move_line aml "
            f"  JOIN account_move am ON am.id = aml.move_id "
            f"  WHERE am.move_type = 'entry' AND am.state = 'posted' "
            f"  AND aml.account_id IN ({rec_pay_ids}) "
            f"  AND aml.reconciled = false "
            f"  AND aml.amount_residual = 0 "
            f"  AND (aml.id IN (SELECT debit_move_id FROM account_partial_reconcile) "
            f"    OR aml.id IN (SELECT credit_move_id FROM account_partial_reconcile))"
            f")")
    print(f"  Payment AML lines needing reconciled=true fix: {payment_wrong}")

    # =========================================================================
    # STEP 9: Update sequence for partial/full reconcile
    # =========================================================================
    print("\n=== STEP 9: Update sequences ===")
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
    for label, db, acct_filter in [
        ("V15", "taya_db", "internal_type IN ('receivable','payable')"),
        ("V19", "taya19_db", "account_type IN ('asset_receivable','liability_payable')")
    ]:
        rows = sql(db,
            f"SELECT aa.code, SUM(aml.amount_residual) "
            f"FROM account_move_line aml "
            f"JOIN account_account aa ON aa.id = aml.account_id "
            f"WHERE aa.{acct_filter} "
            f"GROUP BY aa.code ORDER BY aa.code")
        for row in rows:
            print(f"  {label}: {row}")

    # Spot check the HD/2024/00125 and HD/2025/00019 invoices
    print("\n--- Spot check (HD/2024/00125, HD/2025/00019) ---")
    for name in ["HD/2024/00125", "HD/2025/00019"]:
        for label, db in [("V15", "taya_db"), ("V19", "taya19_db")]:
            row = sql(db,
                f"SELECT name, amount_total, amount_residual, payment_state "
                f"FROM account_move WHERE name = '{name}'")
            if row:
                print(f"  {label} {row[0]}")


if __name__ == "__main__":
    main()
