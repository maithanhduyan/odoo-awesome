"""Phase 18 Reconciliation Research: V15 → V19 exploration."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from migrate.config import *
from migrate.migrator import OdooConnection, IDMap

v15 = OdooConnection(V15_URL, V15_DB, V15_USER, V15_PASSWORD, label="V15")
v19 = OdooConnection(V19_URL, V19_DB, V19_USER, V19_PASSWORD, label="V19")
v15.connect()
v19.connect()
id_map = IDMap()

# 1. FIELD COMPARISON: account.partial.reconcile
print("=" * 80)
print("1. account.partial.reconcile FIELDS")
print("=" * 80)

v15_f = v15.fields_get("account.partial.reconcile")
v19_f = v19.fields_get("account.partial.reconcile")
v15_fn = set(v15_f.keys())
v19_fn = set(v19_f.keys())

print(f"\nV15: {len(v15_fn)} fields, V19: {len(v19_fn)} fields")

only15 = sorted(v15_fn - v19_fn)
if only15:
    print(f"\nREMOVED in V19 ({len(only15)}):")
    for f in only15:
        print(f"  - {f:<40} ({v15_f[f].get('type')})")

only19 = sorted(v19_fn - v15_fn)
if only19:
    print(f"\nNEW in V19 ({len(only19)}):")
    for f in only19:
        print(f"  + {f:<40} ({v19_f[f].get('type')})")

common = sorted(v15_fn & v19_fn)
for f in common:
    t15, t19 = v15_f[f].get("type"), v19_f[f].get("type")
    if t15 != t19:
        print(f"  TYPE CHANGE: {f:<35} {t15} → {t19}")

# Key fields
print("\nKey fields:")
for f in ["debit_move_id", "credit_move_id", "amount", "debit_amount_currency",
          "credit_amount_currency", "company_id", "full_reconcile_id",
          "max_date", "company_currency_id", "debit_currency_id", "credit_currency_id"]:
    in15 = f in v15_fn
    in19 = f in v19_fn
    t15 = v15_f[f].get("type") if in15 else "-"
    t19 = v19_f[f].get("type") if in19 else "-"
    status = "BOTH" if in15 and in19 else "V15 only" if in15 else "V19 only"
    print(f"  {f:<40} V15={t15:<12} V19={t19:<12} {status}")

# 2. FIELD COMPARISON: account.full.reconcile
print("\n" + "=" * 80)
print("2. account.full.reconcile FIELDS")
print("=" * 80)

v15_ff = v15.fields_get("account.full.reconcile")
v19_ff = v19.fields_get("account.full.reconcile")
v15_ffn = set(v15_ff.keys())
v19_ffn = set(v19_ff.keys())

print(f"\nV15: {len(v15_ffn)} fields, V19: {len(v19_ffn)} fields")

only15f = sorted(v15_ffn - v19_ffn)
if only15f:
    print(f"\nREMOVED in V19 ({len(only15f)}):")
    for f in only15f:
        print(f"  - {f:<40} ({v15_ff[f].get('type')})")

only19f = sorted(v19_ffn - v15_ffn)
if only19f:
    print(f"\nNEW in V19 ({len(only19f)}):")
    for f in only19f:
        print(f"  + {f:<40} ({v19_ff[f].get('type')})")

# Key fields
print("\nKey fields:")
for f in ["name", "partial_reconcile_ids", "reconciled_line_ids", "exchange_move_id", "company_id"]:
    in15 = f in v15_ffn
    in19 = f in v19_ffn
    t15 = v15_ff[f].get("type") if in15 else "-"
    t19 = v19_ff[f].get("type") if in19 else "-"
    status = "BOTH" if in15 and in19 else "V15 only" if in15 else "V19 only"
    print(f"  {f:<40} V15={t15:<12} V19={t19:<12} {status}")

# 3. SAMPLE DATA
print("\n" + "=" * 80)
print("3. SAMPLE V15 account.partial.reconcile")
print("=" * 80)

samples = v15.search_read("account.partial.reconcile", [],
    ["id", "debit_move_id", "credit_move_id", "amount",
     "debit_amount_currency", "credit_amount_currency",
     "full_reconcile_id", "company_id", "max_date",
     "company_currency_id", "debit_currency_id", "credit_currency_id"],
    limit=5, order="id asc")
for s in samples:
    print(f"\n  Partial #{s['id']}:")
    for k, v in s.items():
        if k != "id":
            print(f"    {k:<35} = {v}")

# 4. SAMPLE full reconcile
print("\n" + "=" * 80)
print("4. SAMPLE V15 account.full.reconcile")
print("=" * 80)

fsamples = v15.search_read("account.full.reconcile", [],
    ["id", "name", "partial_reconcile_ids", "reconciled_line_ids", "exchange_move_id"],
    limit=5, order="id asc")
for s in fsamples:
    print(f"\n  Full #{s['id']}:")
    for k, v in s.items():
        if k != "id":
            print(f"    {k:<35} = {v}")

# 5. Check if move lines have full_reconcile_id
print("\n" + "=" * 80)
print("5. V15 account.move.line reconcile fields")
print("=" * 80)

ml_fields = v15.fields_get("account.move.line")
for f in ["full_reconcile_id", "reconciled", "matched_debit_ids", "matched_credit_ids",
          "amount_residual", "amount_residual_currency"]:
    if f in ml_fields:
        print(f"  V15 {f:<35} ({ml_fields[f].get('type')})")

ml19_fields = v19.fields_get("account.move.line")
for f in ["full_reconcile_id", "reconciled", "matched_debit_ids", "matched_credit_ids",
          "amount_residual", "amount_residual_currency"]:
    if f in ml19_fields:
        print(f"  V19 {f:<35} ({ml19_fields[f].get('type')})")

# 6. Check move line mapping coverage
print("\n" + "=" * 80)
print("6. MOVE LINE MAPPING COVERAGE")
print("=" * 80)

# How many partial reconcile move lines are mapped?
partials = v15.search_read("account.partial.reconcile", [],
    ["debit_move_id", "credit_move_id"], order="id asc")
debit_ids = set()
credit_ids = set()
for p in partials:
    if p.get("debit_move_id"):
        debit_ids.add(p["debit_move_id"][0])
    if p.get("credit_move_id"):
        credit_ids.add(p["credit_move_id"][0])

all_line_ids = debit_ids | credit_ids
mapped_count = sum(1 for lid in all_line_ids if id_map.get("account.move.line", lid))
unmapped_count = len(all_line_ids) - mapped_count

print(f"  Unique move lines referenced: {len(all_line_ids)}")
print(f"  Mapped in id_map:             {mapped_count}")
print(f"  NOT mapped:                   {unmapped_count}")

# Check what moves those unmapped lines belong to
if unmapped_count > 0:
    unmapped_ids = [lid for lid in all_line_ids if not id_map.get("account.move.line", lid)]
    # Sample unmapped lines
    sample_unmapped = v15.read("account.move.line", unmapped_ids[:20],
        ["id", "move_id", "account_id", "debit", "credit", "name", "display_type", "exclude_from_invoice_tab"])
    print(f"\n  Sample unmapped lines (first 20):")
    move_ids_seen = set()
    for l in sample_unmapped:
        mid = l["move_id"][0] if l.get("move_id") else 0
        acct = l.get("account_id", [0, ""])[1] if l.get("account_id") else ""
        excl = l.get("exclude_from_invoice_tab", False)
        dt = l.get("display_type", False)
        print(f"    Line #{l['id']}: move={mid} acct={acct:<30} D={l.get('debit',0):>12,.0f} C={l.get('credit',0):>12,.0f} excl={excl} dt={dt}")
        move_ids_seen.add(mid)

    # Check if those moves are mapped
    print(f"\n  Distinct moves of unmapped lines: {len(move_ids_seen)}")
    for mid in sorted(move_ids_seen):
        v19_mid = id_map.get("account.move", mid)
        print(f"    Move v15#{mid} → v19#{v19_mid}")

# 7. V19 current state
print("\n" + "=" * 80)
print("7. V19 CURRENT STATE")
print("=" * 80)

v19_partial = v19.search_count("account.partial.reconcile", [])
v19_full = v19.search_count("account.full.reconcile", [])
print(f"  V19 account.partial.reconcile: {v19_partial}")
print(f"  V19 account.full.reconcile: {v19_full}")

# 8. Check V19 payment_state on invoices
print("\n" + "=" * 80)
print("8. V19 INVOICE payment_state")
print("=" * 80)

import subprocess
sql = "SELECT payment_state, COUNT(*) FROM account_move WHERE move_type != 'entry' GROUP BY payment_state ORDER BY payment_state;"
result = subprocess.run(["docker", "exec", "postgres", "psql", "-U", "odoo", "-d", "taya19_db", "-c", sql],
    capture_output=True, text=True, timeout=30)
print(result.stdout)

print("=" * 80)
print("DONE")
