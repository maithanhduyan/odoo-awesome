#!/usr/bin/env python3
"""Phase 17 Payments Research: V15 → V19 account.payment exploration."""

import json
import logging
import sys
from pprint import pprint
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from migrate.migrator import OdooConnection, IDMap
from migrate.config import V15_URL, V15_DB, V15_USER, V15_PASSWORD, V19_URL, V19_DB, V19_USER, V19_PASSWORD

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("check_payments")

v15 = OdooConnection(V15_URL, V15_DB, V15_USER, V15_PASSWORD, label="V15")
v19 = OdooConnection(V19_URL, V19_DB, V19_USER, V19_PASSWORD, label="V19")

print("\n" + "=" * 80)
print("PHASE 17: Payments V15 → V19 EXPLORATION")
print("=" * 80)

v15.connect()
v19.connect()
id_map = IDMap()

# 1. FIELD COMPARISON
print("\n" + "=" * 80)
print("1. FIELD COMPARISON: account.payment")
print("=" * 80)

v15_fields = v15.fields_get("account.payment")
v19_fields = v19.fields_get("account.payment")
v15_fn = set(v15_fields.keys())
v19_fn = set(v19_fields.keys())

print(f"\nV15 fields: {len(v15_fn)}, V19 fields: {len(v19_fn)}")

only_v15 = sorted(v15_fn - v19_fn)
if only_v15:
    print(f"\nREMOVED in V19 ({len(only_v15)}):")
    for f in only_v15:
        print(f"  - {f:<40} ({v15_fields[f].get('type')})")

only_v19 = sorted(v19_fn - v15_fn)
if only_v19:
    print(f"\nNEW in V19 ({len(only_v19)}):")
    for f in only_v19[:30]:
        print(f"  + {f:<40} ({v19_fields[f].get('type')})")
    if len(only_v19) > 30:
        print(f"  ... and {len(only_v19)-30} more")

type_changes = []
for f in sorted(v15_fn & v19_fn):
    t15, t19 = v15_fields[f].get("type"), v19_fields[f].get("type")
    if t15 != t19:
        type_changes.append((f, t15, t19))
if type_changes:
    print(f"\nTYPE CHANGES ({len(type_changes)}):")
    for f, t15, t19 in type_changes:
        print(f"  {f:<40} {t15} → {t19}")

# Key fields
KEY = ["name", "partner_id", "journal_id", "payment_method_id", "payment_method_line_id",
       "state", "payment_type", "amount", "currency_id", "date", "ref", "move_id",
       "is_internal_transfer", "partner_type", "destination_journal_id"]
print("\nKey fields check:")
for f in KEY:
    if f in v15_fn and f in v19_fn:
        print(f"  OK  {f}")
    elif f in v15_fn:
        print(f"  DEL {f} (V15 only)")
    elif f in v19_fn:
        print(f"  NEW {f} (V19 only)")

# 2. V15 STATISTICS
print("\n" + "=" * 80)
print("2. V15 PAYMENT STATISTICS")
print("=" * 80)

total = v15.search_count("account.payment", [])
print(f"\nTotal: {total}")

print("\nBy state:")
for st in ["draft", "posted", "sent", "reconciled", "cancelled"]:
    c = v15.search_count("account.payment", [("state", "=", st)])
    if c: print(f"  {st:<15} {c:>5}")

print("\nBy payment_type:")
for pt in ["inbound", "outbound", "transfer"]:
    c = v15.search_count("account.payment", [("payment_type", "=", pt)])
    if c: print(f"  {pt:<15} {c:>5}")

print("\nBy partner_type:")
for pt in ["customer", "supplier"]:
    c = v15.search_count("account.payment", [("partner_type", "=", pt)])
    if c: print(f"  {pt:<15} {c:>5}")

print("\nBy journal:")
journals = v15.search_read("account.journal", [], ["id", "name", "code", "type"])
for j in sorted(journals, key=lambda x: x["id"]):
    c = v15.search_count("account.payment", [("journal_id", "=", j["id"])])
    if c: print(f"  {j['name']:<30} ({j['code']:<8}) {c:>3}")

# 3. SAMPLE PAYMENT
print("\n" + "=" * 80)
print("3. SAMPLE PAYMENT (V15)")
print("=" * 80)

sample = v15.search_read("account.payment", [], [
    "id", "name", "partner_id", "journal_id", "payment_method_id",
    "payment_type", "partner_type", "state", "amount", "currency_id",
    "date", "ref", "move_id", "is_internal_transfer", "company_id",
    "destination_account_id", "destination_journal_id"
], limit=3, order="id asc")
for s in sample:
    print(f"\n  Payment v15#{s['id']}: {s['name']}")
    for k, v in s.items():
        if k != "id":
            print(f"    {k:<35} = {str(v)[:80]}")

# 4. ENTRY MOVES (the 1 manual entry)
print("\n" + "=" * 80)
print("4. MANUAL ENTRY MOVES (no payment_id)")
print("=" * 80)

entry_moves = v15.search_read("account.move", [("move_type", "=", "entry")],
    ["id", "name", "state", "payment_id", "date", "journal_id", "partner_id", "amount_total", "line_ids"],
    order="id asc")
manual = [m for m in entry_moves if not m.get("payment_id")]
print(f"\nTotal entry moves: {len(entry_moves)}, with payment_id: {len(entry_moves)-len(manual)}, manual: {len(manual)}")

for m in manual:
    print(f"\n  Move v15#{m['id']}: {m['name']}")
    print(f"    state={m['state']}, date={m['date']}")
    print(f"    journal={m.get('journal_id')}")
    print(f"    partner={m.get('partner_id')}")
    print(f"    amount_total={m.get('amount_total')}")
    print(f"    lines: {len(m.get('line_ids', []))}")
    # Read lines
    if m.get("line_ids"):
        lines = v15.read("account.move.line", m["line_ids"],
            ["id", "name", "account_id", "debit", "credit", "partner_id"])
        for l in lines:
            acct = l.get("account_id", [0, ""])[1] if l.get("account_id") else ""
            print(f"      Line #{l['id']}: {l.get('name', '')[:40]:<40} acct={acct:<30} D={l.get('debit',0):>12,.0f} C={l.get('credit',0):>12,.0f}")

# 5. PAYMENT METHODS
print("\n" + "=" * 80)
print("5. PAYMENT METHODS")
print("=" * 80)

v15_pm = v15.search_read("account.payment.method", [], ["id", "name", "code", "payment_type"])
v19_pm = v19.search_read("account.payment.method", [], ["id", "name", "code", "payment_type"])

print(f"\nV15 ({len(v15_pm)}):")
for pm in v15_pm: print(f"  #{pm['id']} {pm['name']:<30} code={pm.get('code',''):<15} type={pm.get('payment_type','')}")
print(f"\nV19 ({len(v19_pm)}):")
for pm in v19_pm: print(f"  #{pm['id']} {pm['name']:<30} code={pm.get('code',''):<15} type={pm.get('payment_type','')}")

# Map by code+type
v19_pm_by_code = {(pm["code"], pm["payment_type"]): pm["id"] for pm in v19_pm}
print("\nMapping by code+type:")
for pm in v15_pm:
    key = (pm["code"], pm["payment_type"])
    v19_id = v19_pm_by_code.get(key)
    print(f"  v15#{pm['id']} ({pm['code']},{pm['payment_type']}) → v19#{v19_id}" if v19_id else f"  v15#{pm['id']} ({pm['code']},{pm['payment_type']}) → NOT FOUND")

# 6. V19 payment.method.line
print("\n" + "=" * 80)
print("6. V19 account.payment.method.line")
print("=" * 80)

try:
    pml_count = v19.search_count("account.payment.method.line", [])
    print(f"\nV19 records: {pml_count}")
    if pml_count > 0:
        pmls = v19.search_read("account.payment.method.line", [], [
            "id", "name", "payment_method_id", "journal_id", "payment_type"
        ], limit=30)
        for pml in pmls:
            pm = pml.get("payment_method_id", [0, ""])[1] if pml.get("payment_method_id") else ""
            j = pml.get("journal_id", [0, ""])[1] if pml.get("journal_id") else ""
            print(f"  #{pml['id']:<4} {pml.get('name',''):<30} method={pm:<20} journal={j:<20} type={pml.get('payment_type','')}")
except Exception as e:
    print(f"  Error: {e}")

# 7. V19 PAYMENT STATE OPTIONS
print("\n" + "=" * 80)
print("7. V19 account.payment STATE field")
print("=" * 80)

v19_state = v19_fields.get("state", {})
print(f"  type: {v19_state.get('type')}")
print(f"  selection: {v19_state.get('selection')}")
print(f"  required: {v19_state.get('required')}")

v15_state = v15_fields.get("state", {})
print(f"\nV15 state selection: {v15_state.get('selection')}")

# 8. ID_MAP CHECK
print("\n" + "=" * 80)
print("8. ID_MAP STATUS")
print("=" * 80)

for model in ["account.payment", "account.payment.method", "account.journal", "account.payment.term", "account.move"]:
    c = id_map.count(model)
    print(f"  {model:<35} {'mapped' if c else 'NOT MAPPED':<12} {c} entries")

# 9. V15 check: is_reconciled or reconciled_invoice_ids
print("\n" + "=" * 80)
print("9. RECONCILIATION FIELDS")
print("=" * 80)

for f in ["reconciled_invoice_ids", "reconciled_bill_ids", "reconciled_invoices_count",
          "reconciled_bills_count", "is_reconciled", "is_matched"]:
    in15 = f in v15_fn
    in19 = f in v19_fn
    t15 = v15_fields[f].get("type") if in15 else "-"
    t19 = v19_fields[f].get("type") if in19 else "-"
    print(f"  {f:<35} V15={t15:<15} V19={t19:<15} {'BOTH' if in15 and in19 else 'V15 only' if in15 else 'V19 only' if in19 else 'NONE'}")

print("\n" + "=" * 80)
print("DONE")
print("=" * 80)
