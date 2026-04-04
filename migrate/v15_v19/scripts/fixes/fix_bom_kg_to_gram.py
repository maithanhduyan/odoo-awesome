"""
Convert BOM lines from kg to gram on Odoo 19.
- Read original qty from V15 (has 3-4 decimal places in kg)
- Multiply by 1000 to get grams
- Update V19: product_uom_id = g (15), product_qty = qty_in_grams
- Only converts lines that use kg UoM
"""
import sys, json, subprocess
sys.path.insert(0, '/home/odoo-migration')

from migrate.config import *
from migrate.migrator import OdooConnection

V19_KG_UOM_ID = 16
V19_G_UOM_ID = 15

def run_sql(sql):
    r = subprocess.run(
        ["docker", "exec", "postgres-18", "psql", "-U", "odoo", "-d", "taya19_db", "-c", sql],
        capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        print(f"  SQL ERROR: {r.stderr[:300]}")
    return r.stdout

# Connect
src = OdooConnection(V15_URL, V15_DB, V15_USER, V15_PASSWORD, 'v15')
dst = OdooConnection(V19_URL, V19_DB, V19_USER, V19_PASSWORD, 'v19')
src.connect()
dst.connect()

id_map = json.load(open('migrate/id_map.json'))
bom_line_map = {int(k): v for k, v in id_map.get('mrp.bom.line', {}).items()}

# Read V15 BOM lines that use kg
v15_bom_lines = src.search_read('mrp.bom.line',
    [['product_uom_id.name', '=', 'kg']],
    ['product_id', 'product_qty', 'product_uom_id', 'bom_id'],
    limit=0)

print(f"V15 BOM lines with kg: {len(v15_bom_lines)}")

# Build updates: V15 qty (kg) * 1000 = grams
updates = []  # (v19_id, qty_in_grams)
skipped = 0

for bl in v15_bom_lines:
    v19_id = bom_line_map.get(bl['id'])
    if not v19_id:
        skipped += 1
        continue

    qty_kg = bl['product_qty']
    qty_g = round(qty_kg * 1000, 2)  # gram, 2dp is more than enough

    updates.append((v19_id, qty_g))

print(f"Updates to apply: {len(updates)}")
print(f"Skipped (no V19 mapping): {skipped}")

# Preview first 10
print(f"\n{'V19 ID':>8s} {'V15 kg':>12s} {'V19 gram':>12s} {'Product':50s}")
print("-" * 85)
for v19_id, qty_g in updates[:10]:
    bl = next(b for b in v15_bom_lines if bom_line_map.get(b['id']) == v19_id)
    pname = bl['product_id'][1] if bl['product_id'] else '?'
    print(f"{v19_id:8d} {bl['product_qty']:12.4f} {qty_g:12.2f} {pname[:50]:50s}")
print(f"  ... {len(updates) - 10} more")

# Apply via SQL (fast batch update)
print(f"\nApplying updates...")

BATCH = 500
total_ok = 0
for i in range(0, len(updates), BATCH):
    batch = updates[i:i+BATCH]
    # UPDATE product_qty and product_uom_id in one statement
    ids = ','.join(str(u[0]) for u in batch)
    qty_cases = " ".join(f"WHEN {u[0]} THEN {u[1]}" for u in batch)

    sql = f"""
UPDATE mrp_bom_line
SET product_qty = CASE id {qty_cases} ELSE product_qty END,
    product_uom_id = {V19_G_UOM_ID}
WHERE id IN ({ids});
"""
    out = run_sql(sql)
    if 'UPDATE' in out:
        n = int(out.strip().split()[-1])
        total_ok += n

print(f"Updated: {total_ok} BOM lines (kg → g)")

# Verify
print(f"\n=== Verification ===")
v19_bom = dst.search_read('mrp.bom.line', [], ['product_uom_id'], limit=0)
uom_dist = {}
for bl in v19_bom:
    uom = bl['product_uom_id'][1] if bl['product_uom_id'] else '?'
    uom_dist[uom] = uom_dist.get(uom, 0) + 1

for uom, count in sorted(uom_dist.items(), key=lambda x: -x[1]):
    print(f"  {uom:25s}: {count} lines")

# Spot check: compare a few
print(f"\nSpot check (5 random):")
import random
samples = random.sample(updates, min(5, len(updates)))
for v19_id, expected_g in samples:
    v19_bl = dst.read('mrp.bom.line', [v19_id], ['product_id', 'product_qty', 'product_uom_id'])
    if v19_bl:
        bl = v19_bl[0]
        pname = bl['product_id'][1] if bl['product_id'] else '?'
        uom = bl['product_uom_id'][1] if bl['product_uom_id'] else '?'
        match = '✓' if abs(bl['product_qty'] - expected_g) < 0.01 else '✗'
        print(f"  {match} id={v19_id} {pname[:40]:40s} qty={bl['product_qty']:.2f} {uom} (expected {expected_g:.2f} g)")

print(f"\nDone!")
