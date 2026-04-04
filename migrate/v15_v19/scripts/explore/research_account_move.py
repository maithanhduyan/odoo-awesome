"""
Research account.move and account.move.line structures in V15 and V19.
Run: python research_account_move.py
"""
import json
import sys
import xmlrpc.client
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from migrate.config import (
    V15_URL, V15_DB, V15_USER, V15_PASSWORD,
    V19_URL, V19_DB, V19_USER, V19_PASSWORD,
)

# ── Connect ──────────────────────────────────────────────────────────────
def connect(url, db, user, pwd):
    common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
    uid = common.authenticate(db, user, pwd, {})
    models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
    return uid, models

v15_uid, v15 = connect(V15_URL, V15_DB, V15_USER, V15_PASSWORD)
v19_uid, v19 = connect(V19_URL, V19_DB, V19_USER, V19_PASSWORD)

def v15_call(model, method, args, kw=None):
    return v15.execute_kw(V15_DB, v15_uid, V15_PASSWORD, model, method, args, kw or {})

def v19_call(model, method, args, kw=None):
    return v19.execute_kw(V19_DB, v19_uid, V19_PASSWORD, model, method, args, kw or {})

SEP = "\n" + "=" * 80

# ── 1. V15 account.move counts ──────────────────────────────────────────
print(SEP)
print("1. V15 account.move counts by move_type and state")
print("=" * 80)

groups_mt = v15_call('account.move', 'read_group', [[], ['move_type'], ['move_type']])
print("\n--- By move_type ---")
total = 0
for g in groups_mt:
    print(f"  {g['move_type']}: {g['move_type_count']}")
    total += g['move_type_count']
print(f"  TOTAL: {total}")

groups_st = v15_call('account.move', 'read_group', [[], ['state'], ['state']])
print("\n--- By state ---")
for g in groups_st:
    print(f"  {g['state']}: {g['state_count']}")

groups_ms = v15_call('account.move', 'read_group', [[], ['move_type', 'state'], ['move_type', 'state']], {'lazy': False})
print("\n--- By move_type + state ---")
for g in groups_ms:
    print(f"  {g['move_type']} / {g['state']}: {g['__count']}")

# ── 2. V15 account.move fields ──────────────────────────────────────────
print(SEP)
print("2. V15 account.move fields (key fields)")
print("=" * 80)

KEY_MOVE_FIELDS = [
    'move_type', 'state', 'name', 'ref', 'narration', 'date', 'invoice_date',
    'invoice_date_due', 'partner_id', 'journal_id', 'currency_id', 'company_id',
    'amount_total', 'amount_residual', 'amount_untaxed', 'amount_tax',
    'payment_reference', 'fiscal_position_id', 'invoice_origin',
    'reversed_entry_id', 'invoice_line_ids', 'line_ids',
    'invoice_payment_term_id', 'auto_post', 'posted_before',
]

v15_move_fields = v15_call('account.move', 'fields_get', [[]], {'attributes': ['type', 'string', 'relation', 'required', 'readonly', 'store']})
print("\nV15 account.move key fields:")
for f in KEY_MOVE_FIELDS:
    info = v15_move_fields.get(f)
    if info:
        print(f"  {f}: type={info['type']}, string='{info.get('string','')}', "
              f"relation={info.get('relation','')}, required={info.get('required',False)}, "
              f"store={info.get('store',True)}")
    else:
        print(f"  {f}: *** NOT FOUND ***")

# ── 3. V15 account.move.line fields ─────────────────────────────────────
print(SEP)
print("3. V15 account.move.line fields (key fields)")
print("=" * 80)

KEY_LINE_FIELDS = [
    'move_id', 'account_id', 'partner_id', 'product_id', 'product_uom_id',
    'quantity', 'price_unit', 'discount', 'debit', 'credit', 'balance',
    'tax_ids', 'tax_line_id', 'name', 'date', 'journal_id', 'currency_id',
    'amount_currency', 'analytic_account_id', 'display_type', 'sequence',
    'exclude_from_invoice_tab', 'price_subtotal', 'price_total',
    'tax_tag_ids', 'tax_repartition_line_id', 'move_name',
]

v15_line_fields = v15_call('account.move.line', 'fields_get', [[]], {'attributes': ['type', 'string', 'relation', 'required', 'readonly', 'store']})
print("\nV15 account.move.line key fields:")
for f in KEY_LINE_FIELDS:
    info = v15_line_fields.get(f)
    if info:
        print(f"  {f}: type={info['type']}, string='{info.get('string','')}', "
              f"relation={info.get('relation','')}, required={info.get('required',False)}, "
              f"store={info.get('store',True)}")
    else:
        print(f"  {f}: *** NOT FOUND ***")

# ── 4. V19 account.move fields ──────────────────────────────────────────
print(SEP)
print("4. V19 account.move fields — compare with V15")
print("=" * 80)

v19_move_fields = v19_call('account.move', 'fields_get', [[]], {'attributes': ['type', 'string', 'relation', 'required', 'readonly', 'store']})

EXTRA_V19_CHECK = KEY_MOVE_FIELDS + ['payment_state', 'sequence_prefix', 'sequence_number', 'move_type']
print("\nV19 account.move key fields check:")
for f in sorted(set(EXTRA_V19_CHECK)):
    info = v19_move_fields.get(f)
    if info:
        print(f"  {f}: type={info['type']}, string='{info.get('string','')}', "
              f"relation={info.get('relation','')}, required={info.get('required',False)}, "
              f"store={info.get('store',True)}")
    else:
        print(f"  {f}: *** NOT IN V19 ***")

v15_only = set(v15_move_fields.keys()) - set(v19_move_fields.keys())
v19_only = set(v19_move_fields.keys()) - set(v15_move_fields.keys())
print(f"\nFields in V15 account.move but NOT in V19 ({len(v15_only)}):")
for f in sorted(v15_only):
    print(f"  - {f}")
print(f"\nFields in V19 account.move but NOT in V15 ({len(v19_only)}):")
for f in sorted(v19_only):
    info = v19_move_fields[f]
    print(f"  + {f}: type={info['type']}, string='{info.get('string','')}'")

# ── 5. V19 account.move.line fields ─────────────────────────────────────
print(SEP)
print("5. V19 account.move.line fields — compare with V15")
print("=" * 80)

v19_line_fields = v19_call('account.move.line', 'fields_get', [[]], {'attributes': ['type', 'string', 'relation', 'required', 'readonly', 'store']})

EXTRA_LINE_CHECK = KEY_LINE_FIELDS + ['analytic_distribution', 'tax_line_id', 'exclude_from_invoice_tab']
print("\nV19 account.move.line key fields check:")
for f in sorted(set(EXTRA_LINE_CHECK)):
    info = v19_line_fields.get(f)
    if info:
        print(f"  {f}: type={info['type']}, string='{info.get('string','')}', "
              f"relation={info.get('relation','')}, required={info.get('required',False)}, "
              f"store={info.get('store',True)}")
    else:
        print(f"  {f}: *** NOT IN V19 ***")

v15_line_only = set(v15_line_fields.keys()) - set(v19_line_fields.keys())
v19_line_only = set(v19_line_fields.keys()) - set(v15_line_fields.keys())
print(f"\nFields in V15 account.move.line but NOT in V19 ({len(v15_line_only)}):")
for f in sorted(v15_line_only):
    print(f"  - {f}")
print(f"\nFields in V19 account.move.line but NOT in V15 ({len(v19_line_only)}):")
for f in sorted(v19_line_only):
    info = v19_line_fields[f]
    print(f"  + {f}: type={info['type']}, string='{info.get('string','')}'")

# ── 6. Journal mapping ──────────────────────────────────────────────────
print(SEP)
print("6. Journal mapping V15 -> V19")
print("=" * 80)

v15_journals = v15_call('account.journal', 'search_read', [[]],
                        {'fields': ['id', 'name', 'type', 'code', 'company_id'], 'limit': 100})
v19_journals = v19_call('account.journal', 'search_read', [[]],
                        {'fields': ['id', 'name', 'type', 'code', 'company_id'], 'limit': 100})

print(f"\nV15 journals ({len(v15_journals)}):")
for j in v15_journals:
    print(f"  id={j['id']}, code={j['code']}, name={j['name']}, type={j['type']}")

print(f"\nV19 journals ({len(v19_journals)}):")
for j in v19_journals:
    print(f"  id={j['id']}, code={j['code']}, name={j['name']}, type={j['type']}")

with open(Path(__file__).parent / 'migrate' / 'id_map.json', 'r') as f:
    id_map = json.load(f)

journal_map = id_map.get('account.journal', {})
print(f"\nJournal id_map entries: {len(journal_map)}")
for v15id, v19id in sorted(journal_map.items(), key=lambda x: int(x[0])):
    v15j = next((j for j in v15_journals if j['id'] == int(v15id)), None)
    v19j = next((j for j in v19_journals if j['id'] == v19id), None)
    print(f"  V15 {v15id} ({v15j['name'] if v15j else '?'}) -> V19 {v19id} ({v19j['name'] if v19j else '?'})")

# ── 7. Account mapping ──────────────────────────────────────────────────
print(SEP)
print("7. Account mapping V15 -> V19")
print("=" * 80)

v15_accounts = v15_call('account.account', 'search_read', [[]],
                        {'fields': ['id', 'name', 'code', 'user_type_id', 'company_id'],
                         'limit': 500, 'context': {'active_test': False}})
v19_accounts = v19_call('account.account', 'search_read', [[]],
                        {'fields': ['id', 'name', 'code', 'account_type'],
                         'limit': 500, 'context': {'active_test': False}})

print(f"V15 accounts: {len(v15_accounts)}")
print(f"V19 accounts: {len(v19_accounts)}")

account_map = id_map.get('account.account', {})
print(f"Account id_map entries: {len(account_map)}")

print("\nV15 sample accounts (first 10):")
for a in v15_accounts[:10]:
    ut = a.get('user_type_id', [False, ''])
    print(f"  id={a['id']}, code={a['code']}, name={a['name']}, user_type_id={ut}")

print("\nV19 sample accounts (first 10):")
for a in v19_accounts[:10]:
    print(f"  id={a['id']}, code={a['code']}, name={a['name']}, account_type={a.get('account_type','')}")

# ── 8. Sample invoices ──────────────────────────────────────────────────
print(SEP)
print("8. V15 Sample invoices")
print("=" * 80)

MOVE_READ_FIELDS = [
    'name', 'move_type', 'state', 'ref', 'narration', 'date', 'invoice_date',
    'invoice_date_due', 'partner_id', 'journal_id', 'currency_id', 'company_id',
    'amount_total', 'amount_residual', 'amount_untaxed', 'amount_tax',
    'payment_reference', 'fiscal_position_id', 'invoice_origin',
    'reversed_entry_id', 'invoice_line_ids', 'line_ids',
    'invoice_payment_term_id',
]

LINE_READ_FIELDS = [
    'move_id', 'account_id', 'partner_id', 'product_id', 'product_uom_id',
    'quantity', 'price_unit', 'discount', 'debit', 'credit', 'balance',
    'tax_ids', 'tax_line_id', 'name', 'display_type', 'sequence',
    'exclude_from_invoice_tab', 'price_subtotal', 'price_total',
    'amount_currency',
]

samples = [
    ('out_invoice posted', [['move_type', '=', 'out_invoice'], ['state', '=', 'posted']]),
    ('in_invoice posted', [['move_type', '=', 'in_invoice'], ['state', '=', 'posted']]),
    ('entry posted', [['move_type', '=', 'entry'], ['state', '=', 'posted']]),
]

for label, domain in samples:
    print(f"\n--- Sample: {label} ---")
    ids = v15_call('account.move', 'search', [domain], {'limit': 1, 'order': 'id asc'})
    if not ids:
        print("  No records found!")
        continue
    recs = v15_call('account.move', 'read', [ids], {'fields': MOVE_READ_FIELDS})
    rec = recs[0]
    for k, v in rec.items():
        print(f"  {k}: {v}")

    line_ids = rec.get('line_ids', [])
    if line_ids:
        lines = v15_call('account.move.line', 'read', [line_ids], {'fields': LINE_READ_FIELDS})
        print(f"\n  Lines ({len(lines)}):")
        for ln in lines:
            print(f"    ---")
            for k2, v2 in ln.items():
                print(f"    {k2}: {v2}")

# ── 9. V19 existing account.move ────────────────────────────────────────
print(SEP)
print("9. V19 existing account.move count")
print("=" * 80)

v19_move_count = v19_call('account.move', 'search_count', [[]])
print(f"V19 account.move total count: {v19_move_count}")

if v19_move_count > 0:
    v19_groups = v19_call('account.move', 'read_group', [[], ['move_type'], ['move_type']])
    for g in v19_groups:
        print(f"  {g['move_type']}: {g['move_type_count']}")

# ── 10. States ───────────────────────────────────────────────────────────
print(SEP)
print("10. V15 vs V19 account.move state values")
print("=" * 80)

v15_state_full = v15_call('account.move', 'fields_get', [['state']], {'attributes': ['selection']})
v19_state_full = v19_call('account.move', 'fields_get', [['state']], {'attributes': ['selection']})
print(f"V15 state selections: {v15_state_full.get('state', {}).get('selection', [])}")
print(f"V19 state selections: {v19_state_full.get('state', {}).get('selection', [])}")

v15_mt_full = v15_call('account.move', 'fields_get', [['move_type']], {'attributes': ['selection']})
v19_mt_full = v19_call('account.move', 'fields_get', [['move_type']], {'attributes': ['selection']})
print(f"\nV15 move_type selections: {v15_mt_full.get('move_type', {}).get('selection', [])}")
print(f"V19 move_type selections: {v19_mt_full.get('move_type', {}).get('selection', [])}")

# ── 11. reversed_entry_id ────────────────────────────────────────────────
print(SEP)
print("11. V15 reversed_entry_id usage")
print("=" * 80)

reversed_count = v15_call('account.move', 'search_count', [[['reversed_entry_id', '!=', False]]])
print(f"V15 moves with reversed_entry_id set: {reversed_count}")

if reversed_count > 0:
    reversal_ids = v15_call('account.move', 'search', [[['reversed_entry_id', '!=', False]]], {'limit': 5})
    reversals = v15_call('account.move', 'read', [reversal_ids],
                         {'fields': ['name', 'move_type', 'state', 'reversed_entry_id']})
    print("Sample reversals:")
    for r in reversals:
        print(f"  {r['name']} ({r['move_type']}/{r['state']}) -> reversed_entry_id={r['reversed_entry_id']}")

if 'reversal_move_id' in v15_move_fields:
    rev_count2 = v15_call('account.move', 'search_count', [[['reversal_move_id', '!=', False]]])
    print(f"V15 has 'reversal_move_id' field, non-empty count: {rev_count2}")

# ── 12. Fiscal positions ────────────────────────────────────────────────
print(SEP)
print("12. Fiscal positions V15 -> V19")
print("=" * 80)

v15_fp = v15_call('account.fiscal.position', 'search_read', [[]],
                   {'fields': ['id', 'name', 'company_id'], 'limit': 100})
print(f"V15 fiscal positions ({len(v15_fp)}):")
for fp in v15_fp:
    print(f"  id={fp['id']}, name={fp['name']}")

v19_fp = v19_call('account.fiscal.position', 'search_read', [[]],
                   {'fields': ['id', 'name', 'company_id'], 'limit': 100})
print(f"V19 fiscal positions ({len(v19_fp)}):")
for fp in v19_fp:
    print(f"  id={fp['id']}, name={fp['name']}")

fp_map = id_map.get('account.fiscal.position', {})
print(f"Fiscal position id_map entries: {len(fp_map)}")

# ── 13. Payment terms ───────────────────────────────────────────────────
print(SEP)
print("13. Payment terms V15 -> V19")
print("=" * 80)

v15_pt = v15_call('account.payment.term', 'search_read', [[]],
                   {'fields': ['id', 'name'], 'limit': 100})
print(f"V15 payment terms ({len(v15_pt)}):")
for pt in v15_pt:
    print(f"  id={pt['id']}, name={pt['name']}")

v19_pt = v19_call('account.payment.term', 'search_read', [[]],
                   {'fields': ['id', 'name'], 'limit': 100})
print(f"V19 payment terms ({len(v19_pt)}):")
for pt in v19_pt:
    print(f"  id={pt['id']}, name={pt['name']}")

pt_map = id_map.get('account.payment.term', {})
print(f"Payment term id_map entries: {len(pt_map)}")

# ── 14. Tax check ────────────────────────────────────────────────────────
print(SEP)
print("14. Tax mapping check")
print("=" * 80)

tax_map = id_map.get('account.tax', {})
print(f"account.tax id_map entries: {len(tax_map)}")

v15_taxes = v15_call('account.tax', 'search_read', [[]],
                      {'fields': ['id', 'name', 'type_tax_use', 'amount', 'amount_type'], 'limit': 100})
v19_taxes = v19_call('account.tax', 'search_read', [[]],
                      {'fields': ['id', 'name', 'type_tax_use', 'amount', 'amount_type'], 'limit': 100})

print(f"V15 taxes ({len(v15_taxes)}):")
for t in v15_taxes:
    mapped = tax_map.get(str(t['id']), 'NOT MAPPED')
    print(f"  id={t['id']}, name={t['name']}, use={t['type_tax_use']}, "
          f"amount={t['amount']}%, type={t['amount_type']} -> V19 id={mapped}")

print(f"\nV19 taxes ({len(v19_taxes)}):")
for t in v19_taxes:
    print(f"  id={t['id']}, name={t['name']}, use={t['type_tax_use']}, "
          f"amount={t['amount']}%, type={t['amount_type']}")

# ── 15. V15 account.move.line counts ─────────────────────────────────────
print(SEP)
print("15. V15 account.move.line total count & display_type breakdown")
print("=" * 80)

v15_aml_count = v15_call('account.move.line', 'search_count', [[]])
print(f"V15 account.move.line total: {v15_aml_count}")

try:
    dt_groups = v15_call('account.move.line', 'read_group',
                         [[], ['display_type'], ['display_type']])
    print("\n--- By display_type ---")
    for g in dt_groups:
        print(f"  {g['display_type'] or '(False/product)'}: {g['display_type_count']}")
except Exception as e:
    print(f"  display_type groupby error: {e}")

try:
    ex_groups = v15_call('account.move.line', 'read_group',
                         [[], ['exclude_from_invoice_tab'], ['exclude_from_invoice_tab']])
    print("\n--- By exclude_from_invoice_tab ---")
    for g in ex_groups:
        print(f"  {g['exclude_from_invoice_tab']}: {g['exclude_from_invoice_tab_count']}")
except Exception as e:
    print(f"  exclude_from_invoice_tab groupby error: {e}")

# ── 16. id_map coverage summary ──────────────────────────────────────────
print(SEP)
print("16. id_map coverage summary for accounting models")
print("=" * 80)

acct_models = ['account.account', 'account.tax', 'account.journal',
               'account.fiscal.position', 'account.payment.term',
               'account.move', 'account.move.line',
               'account.analytic.account']
for m in acct_models:
    entries = id_map.get(m, {})
    print(f"  {m}: {len(entries)} mapped")

print("\nV19 analytic check:")
try:
    v19_aa_count = v19_call('account.analytic.account', 'search_count', [[]])
    print(f"  V19 account.analytic.account count: {v19_aa_count}")
except Exception as e:
    print(f"  V19 account.analytic.account: {e}")

try:
    v15_aa_count = v15_call('account.analytic.account', 'search_count', [[]])
    print(f"  V15 account.analytic.account count: {v15_aa_count}")
except Exception as e:
    print(f"  V15 account.analytic.account: {e}")

print("\n\nRESEARCH COMPLETE.")
