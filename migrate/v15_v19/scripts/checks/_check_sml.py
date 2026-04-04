"""Deeper exploration of stock.move.line for migration planning."""
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

# ── V15 stock.move.line fields ───────────────────────────────────────
print("=== V15 stock.move.line fields ===")
f15 = src.fields_get("stock.move.line")
for fn, meta in sorted(f15.items()):
    t = meta.get("type", "")
    if t in ("many2one", "float", "integer", "char", "boolean", "date", "datetime", "selection"):
        r = meta.get("relation", "")
        ro = " [RO]" if meta.get("readonly") else ""
        rel = " -> " + r if r else ""
        print(f"  {fn}: {t}{rel}{ro}")

# ── V19 stock.move.line fields ───────────────────────────────────────
print("\n=== V19 stock.move.line fields ===")
f19 = dst.fields_get("stock.move.line")
for fn, meta in sorted(f19.items()):
    t = meta.get("type", "")
    if t in ("many2one", "float", "integer", "char", "boolean", "date", "datetime", "selection"):
        r = meta.get("relation", "")
        ro = " [RO]" if meta.get("readonly") else ""
        rel = " -> " + r if r else ""
        print(f"  {fn}: {t}{rel}{ro}")

# ── V15 sample data ─────────────────────────────────────────────────
print("\n=== V15 stock.move.line samples (first 10) ===")
smls = src.search_read("stock.move.line", [],
    ["move_id", "picking_id", "product_id", "product_uom_id",
     "qty_done", "product_uom_qty", "state", "date",
     "location_id", "location_dest_id", "lot_id", "lot_name",
     "package_id", "result_package_id", "owner_id"],
    limit=10)
for s in smls:
    print(f"  id={s['id']} move={s['move_id']} pick={s.get('picking_id')} "
          f"prod={s['product_id']} qty_done={s.get('qty_done')} "
          f"uom_qty={s.get('product_uom_qty')} state={s['state']} "
          f"loc={s['location_id']} dest={s['location_dest_id']}")

# ── V15 state distribution of move lines ─────────────────────────────
print("\n=== V15 stock.move.line state distribution ===")
states = {}
all_smls = src.search_read("stock.move.line", [], ["state"], limit=0)
for s in all_smls:
    st = s.get("state", "?")
    states[st] = states.get(st, 0) + 1
for st, cnt in sorted(states.items(), key=lambda x: -x[1]):
    print(f"  {st}: {cnt}")

# ── Check relationship between V15 stock.move and stock.move.line ────
print("\n=== V15 stock.move.line → stock.move mapping coverage ===")
move_ids_in_sml = set()
for s in all_smls:
    if s.get("move_id"):
        move_ids_in_sml.add(s["move_id"][0])
mapped_moves = sum(1 for mid in move_ids_in_sml if id_map.has("stock.move", mid))
print(f"  Unique stock.move referenced: {len(move_ids_in_sml)}")
print(f"  Mapped in id_map: {mapped_moves}")
print(f"  Unmapped: {len(move_ids_in_sml) - mapped_moves}")

# ── V15 stock.quant deeper analysis ─────────────────────────────────
print("\n=== V15 stock.quant product mapping ===")
quants = src.search_read("stock.quant", [],
    ["product_id", "location_id", "quantity", "reserved_quantity", "in_date"],
    limit=0)
unmapped_products = 0
unmapped_locations = 0
neg_qty = 0
for q in quants:
    pid = q["product_id"][0] if q.get("product_id") else None
    lid = q["location_id"][0] if q.get("location_id") else None
    if pid and not id_map.has("product.product", pid):
        unmapped_products += 1
    if lid and not id_map.has("stock.location", lid):
        unmapped_locations += 1
    if q.get("quantity", 0) < 0:
        neg_qty += 1
print(f"  Total quants: {len(quants)}")
print(f"  Unmapped products: {unmapped_products}")
print(f"  Unmapped locations: {unmapped_locations}")
print(f"  Negative quantity quants: {neg_qty}")
print(f"  Positive quantity quants: {len(quants) - neg_qty}")
