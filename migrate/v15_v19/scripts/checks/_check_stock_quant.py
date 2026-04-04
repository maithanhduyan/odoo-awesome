"""Explore stock.quant and stock.valuation.layer for Phase 19 planning."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from migrate.config import *
from migrate.migrator import OdooConnection, IDMap

src = OdooConnection(V15_URL, V15_DB, V15_USER, V15_PASSWORD, "v15")
src.connect()
dst = OdooConnection(V19_URL, V19_DB, V19_USER, V19_PASSWORD, "v19")
dst.connect()
id_map = IDMap()

# ── stock.quant ──────────────────────────────────────────────────────
print("=== V15 stock.quant samples (first 10) ===")
quants = src.search_read("stock.quant", [],
    ["product_id", "location_id", "quantity", "reserved_quantity",
     "in_date", "lot_id", "owner_id", "package_id", "company_id"],
    limit=10)
for q in quants:
    print(f"  id={q['id']} prod={q['product_id']} loc={q['location_id']} "
          f"qty={q['quantity']} res={q['reserved_quantity']} "
          f"in_date={q.get('in_date')} lot={q.get('lot_id')}")

# Location distribution
print("\n=== V15 stock.quant location distribution ===")
all_quants = src.search_read("stock.quant", [],
    ["location_id", "quantity", "reserved_quantity"], limit=0)
loc_dist: dict = {}
for q in all_quants:
    loc_name = q["location_id"][1] if q.get("location_id") else "None"
    loc_id = q["location_id"][0] if q.get("location_id") else 0
    key = f"{loc_id}:{loc_name}"
    if key not in loc_dist:
        loc_dist[key] = {"count": 0, "qty": 0, "loc_id": loc_id}
    loc_dist[key]["count"] += 1
    loc_dist[key]["qty"] += q.get("quantity", 0)
for loc, d in sorted(loc_dist.items(), key=lambda x: -x[1]["count"]):
    mapped = id_map.get("stock.location", d["loc_id"])
    print(f"  {loc}: {d['count']} quants, qty={d['qty']:.0f}, v19_loc={mapped}")

# Check lot usage
lots_used = sum(1 for q in all_quants if q.get("lot_id"))
print(f"\n  Quants with lot_id: {lots_used}")
packages_used = sum(1 for q in all_quants if q.get("package_id"))
print(f"  Quants with package_id: {packages_used}")

# V19 existing
print(f"\n=== V19 stock.quant: {dst.search_count('stock.quant')} ===")
v19_quants = dst.search_read("stock.quant", [],
    ["product_id", "location_id", "quantity"], limit=5)
for q in v19_quants:
    print(f"  id={q['id']} prod={q['product_id']} loc={q['location_id']} qty={q['quantity']}")

# ── stock.valuation.layer ────────────────────────────────────────────
print("\n=== V15 stock.valuation.layer fields ===")
fields15 = src.fields_get("stock.valuation.layer")
for fn, meta in sorted(fields15.items()):
    t = meta.get("type", "")
    if t in ("many2one", "float", "integer", "char", "boolean", "date", "datetime", "selection", "monetary"):
        r = meta.get("relation", "")
        ro = " [RO]" if meta.get("readonly") else ""
        rel = " -> " + r if r else ""
        print(f"  {fn}: {t}{rel}{ro}")

print("\n=== V19 stock.valuation.layer fields ===")
fields19 = dst.fields_get("stock.valuation.layer")
for fn, meta in sorted(fields19.items()):
    t = meta.get("type", "")
    if t in ("many2one", "float", "integer", "char", "boolean", "date", "datetime", "selection", "monetary"):
        r = meta.get("relation", "")
        ro = " [RO]" if meta.get("readonly") else ""
        rel = " -> " + r if r else ""
        print(f"  {fn}: {t}{rel}{ro}")

# SVL samples
print("\n=== V15 stock.valuation.layer samples (first 10) ===")
svls = src.search_read("stock.valuation.layer", [],
    ["product_id", "stock_move_id", "quantity", "unit_cost", "value",
     "remaining_qty", "remaining_value", "description", "company_id",
     "account_move_id", "create_date"],
    limit=10)
for s in svls:
    print(f"  id={s['id']} prod={s['product_id']} move={s.get('stock_move_id')} "
          f"qty={s['quantity']} cost={s['unit_cost']} val={s['value']} "
          f"rem_qty={s['remaining_qty']} rem_val={s['remaining_value']}")

# SVL totals
print(f"\n=== V15 SVL with account_move_id ===")
all_svls = src.search_read("stock.valuation.layer", [],
    ["account_move_id", "stock_move_id"], limit=0)
with_acct = sum(1 for s in all_svls if s.get("account_move_id"))
with_move = sum(1 for s in all_svls if s.get("stock_move_id"))
print(f"  Total SVLs: {len(all_svls)}")
print(f"  With account_move_id: {with_acct}")
print(f"  With stock_move_id: {with_move}")

# V19 existing SVLs
v19_svl_count = dst.search_count("stock.valuation.layer")
print(f"\n=== V19 stock.valuation.layer: {v19_svl_count} ===")

# ── stock.move.line ──────────────────────────────────────────────────
print("\n=== V15 stock.move.line count: ", src.search_count("stock.move.line"), " ===")
print("=== V19 stock.move.line count: ", dst.search_count("stock.move.line"), " ===")

# Check V15 fields
print("\n=== V15 stock.move.line fields ===")
sml_f15 = src.fields_get("stock.move.line")
for fn, meta in sorted(sml_f15.items()):
    t = meta.get("type", "")
    if t in ("many2one", "float", "integer", "char", "boolean", "date", "datetime", "selection"):
        r = meta.get("relation", "")
        ro = " [RO]" if meta.get("readonly") else ""
        rel = " -> " + r if r else ""
        print(f"  {fn}: {t}{rel}{ro}")

print("\n=== V19 stock.move.line fields ===")
sml_f19 = dst.fields_get("stock.move.line")
for fn, meta in sorted(sml_f19.items()):
    t = meta.get("type", "")
    if t in ("many2one", "float", "integer", "char", "boolean", "date", "datetime", "selection"):
        r = meta.get("relation", "")
        ro = " [RO]" if meta.get("readonly") else ""
        rel = " -> " + r if r else ""
        print(f"  {fn}: {t}{rel}{ro}")
