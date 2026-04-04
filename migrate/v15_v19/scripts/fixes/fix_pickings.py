"""Fix 65 skipped pickings by creating 12 missing archived products, then retrying."""
import json
import logging
import subprocess
import time
import xmlrpc.client
from pathlib import Path

MAP_FILE = Path(__file__).parent / "migrate" / "id_map.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("fix_pickings")

# Product type mapping V15 → V19
PRODUCT_TYPE_MAP = {
    "product": "consu",  # storable → consu + is_storable=True
    "consu": "consu",
    "service": "service",
}

PICKING_STATE_MAP = {
    "draft": "draft", "waiting": "waiting", "confirmed": "confirmed",
    "assigned": "assigned", "done": "done", "cancel": "cancel",
}
MOVE_STATE_MAP = PICKING_STATE_MAP.copy()
MOVE_STATE_MAP["partially_available"] = "partially_available"


def _run_sql(sql: str) -> str:
    cmd = ["docker", "exec", "postgres", "psql", "-U", "odoo", "-d", "taya19_db", "-c", sql]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        log.error("SQL error: %s", result.stderr)
    return result.stdout


def main():
    # Load id_map
    id_map = json.load(open(MAP_FILE, encoding="utf-8"))
    id_map = {model: {int(k): v for k, v in pairs.items()} for model, pairs in id_map.items()}

    def get_map(model, v15_id):
        return id_map.get(model, {}).get(v15_id)

    def set_map(model, v15_id, v19_id):
        id_map.setdefault(model, {})[v15_id] = v19_id

    def has_map(model, v15_id):
        return v15_id in id_map.get(model, {})

    # Connect V15
    common15 = xmlrpc.client.ServerProxy("http://localhost:8069/xmlrpc/2/common")
    uid15 = common15.authenticate("taya_db", "tayafood@gmail.com", "TaYa@2022Pwd", {})
    m15 = xmlrpc.client.ServerProxy("http://localhost:8069/xmlrpc/2/object")
    log.info("[v15] Connected uid=%d", uid15)

    # Connect V19
    common19 = xmlrpc.client.ServerProxy("http://localhost:19069/xmlrpc/2/common")
    uid19 = common19.authenticate("taya19_db", "tayafood@gmail.com", "TaYa@2022Pwd", {})
    m19 = xmlrpc.client.ServerProxy("http://localhost:19069/xmlrpc/2/object")
    log.info("[v19] Connected uid=%d", uid19)

    def v15_read(model, ids, fields):
        return m15.execute_kw("taya_db", uid15, "TaYa@2022Pwd", model, "read", [ids], {"fields": fields, "context": {"active_test": False}})

    def v19_create(model, vals):
        return m19.execute_kw("taya19_db", uid19, "TaYa@2022Pwd", model, "create", [vals])

    def v19_search_read(model, domain, fields, **kw):
        return m19.execute_kw("taya19_db", uid19, "TaYa@2022Pwd", model, "search_read", [domain], {"fields": fields, **kw})

    def v15_search_read(model, domain, fields, **kw):
        return m15.execute_kw("taya_db", uid15, "TaYa@2022Pwd", model, "search_read", [domain], {"fields": fields, "context": {"active_test": False}, **kw})

    # ── Step 1: Create 12 missing products ───────────────────────────

    pids = [45, 50, 170, 194, 273, 297, 320, 326, 480, 494, 504, 646]
    log.info("=== Step 1: Create %d missing products ===", len(pids))

    # Read V15 template + product data
    prods15 = v15_read("product.product", pids,
        ["id", "name", "default_code", "active", "product_tmpl_id", "standard_price", "barcode"])
    tmpl_ids = list(set(p["product_tmpl_id"][0] for p in prods15))
    tmpls15 = v15_read("product.template", tmpl_ids,
        ["id", "name", "default_code", "detailed_type", "list_price", "sale_ok", "purchase_ok",
         "active", "categ_id", "uom_id", "tracking", "weight", "volume", "image_1920"])
    tmpl_map_v15 = {t["id"]: t for t in tmpls15}

    created_prods = 0
    for p in sorted(prods15, key=lambda x: x["id"]):
        if has_map("product.product", p["id"]):
            log.info("  v15#%d already mapped, skip", p["id"])
            continue

        tmpl = tmpl_map_v15[p["product_tmpl_id"][0]]
        v15_type = tmpl.get("detailed_type", "consu")
        v19_type = PRODUCT_TYPE_MAP.get(v15_type, "consu")
        is_storable = (v15_type == "product")

        # Template vals
        tvals = {
            "name": tmpl["name"],
            "type": v19_type,
            "sale_ok": tmpl.get("sale_ok", True),
            "purchase_ok": tmpl.get("purchase_ok", True),
            "active": False,  # Keep archived
        }
        if is_storable:
            tvals["is_storable"] = True
        if tmpl.get("default_code"):
            tvals["default_code"] = tmpl["default_code"]
        if tmpl.get("list_price"):
            tvals["list_price"] = tmpl["list_price"]
        if tmpl.get("tracking"):
            tvals["tracking"] = tmpl["tracking"]
        if tmpl.get("weight"):
            tvals["weight"] = tmpl["weight"]
        if tmpl.get("volume"):
            tvals["volume"] = tmpl["volume"]

        # Category
        if tmpl.get("categ_id"):
            cat_v15 = tmpl["categ_id"][0]
            cat_v19 = get_map("product.category", cat_v15)
            if cat_v19:
                tvals["categ_id"] = cat_v19

        # UoM
        if tmpl.get("uom_id"):
            uom_v15 = tmpl["uom_id"][0]
            uom_v19 = get_map("uom.uom", uom_v15)
            if uom_v19:
                tvals["uom_id"] = uom_v19

        # Image
        if tmpl.get("image_1920"):
            tvals["image_1920"] = tmpl["image_1920"]

        try:
            v19_tmpl_id = v19_create("product.template", tvals)
            set_map("product.template", tmpl["id"], v19_tmpl_id)

            # Find the auto-created product.product variant
            v19_prods = v19_search_read("product.product",
                [("product_tmpl_id", "=", v19_tmpl_id)],
                ["id"], context={"active_test": False})
            if v19_prods:
                v19_prod_id = v19_prods[0]["id"]
                set_map("product.product", p["id"], v19_prod_id)
                created_prods += 1
                log.info("  Created: v15#%d '%s' → v19 tmpl#%d prod#%d",
                         p["id"], tmpl["name"], v19_tmpl_id, v19_prod_id)
            else:
                log.error("  No variant found for template v19#%d!", v19_tmpl_id)
        except Exception as e:
            log.error("  v15#%d FAILED: %s", p["id"], e)

    log.info("  Products created: %d", created_prods)

    # Save id_map
    raw = {model: {str(k): v for k, v in pairs.items()} for model, pairs in id_map.items()}
    with open(MAP_FILE, "w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2, ensure_ascii=False)
    log.info("  id_map saved")

    # ── Step 2: Retry 65 failed pickings ─────────────────────────────

    log.info("=== Step 2: Retry failed pickings ===")

    all_picks = v15_search_read("stock.picking", [],
        ["id", "name", "state", "picking_type_id", "partner_id",
         "location_id", "location_dest_id", "scheduled_date", "date_done",
         "origin", "move_type", "move_lines"],
        order="id asc")

    unmapped_picks = [p for p in all_picks if not has_map("stock.picking", p["id"])]
    log.info("  Unmapped pickings: %d", len(unmapped_picks))

    # Read their moves
    all_move_ids = []
    for pick in unmapped_picks:
        all_move_ids.extend(pick.get("move_lines", []))

    moves_raw = v15_read("stock.move", list(set(all_move_ids)),
        ["id", "name", "product_id", "product_uom", "product_uom_qty",
         "quantity_done", "picking_id", "location_id", "location_dest_id",
         "state", "date", "origin", "reference", "sale_line_id",
         "purchase_line_id", "picking_type_id", "sequence"])

    moves_by_picking = {}
    for mv in moves_raw:
        pid = mv["picking_id"][0] if isinstance(mv["picking_id"], list) else mv["picking_id"]
        if pid:
            moves_by_picking.setdefault(pid, []).append(mv)

    pick_created = 0
    pick_errors = 0
    pick_states_sql = []

    for pick in unmapped_picks:
        if has_map("stock.picking", pick["id"]):
            continue

        pt_v15 = pick["picking_type_id"][0] if pick["picking_type_id"] else False
        pt_v19 = get_map("stock.picking.type", pt_v15) if pt_v15 else False
        if not pt_v19:
            log.warning("  Picking %s: type v15#%s not mapped", pick["name"], pt_v15)
            pick_errors += 1
            continue

        loc_v15 = pick["location_id"][0] if pick["location_id"] else False
        loc_v19 = get_map("stock.location", loc_v15) if loc_v15 else False
        loc_dest_v15 = pick["location_dest_id"][0] if pick["location_dest_id"] else False
        loc_dest_v19 = get_map("stock.location", loc_dest_v15) if loc_dest_v15 else False

        if not loc_v19 or not loc_dest_v19:
            log.warning("  Picking %s: location not mapped", pick["name"])
            pick_errors += 1
            continue

        v15_moves = moves_by_picking.get(pick["id"], [])
        move_cmds = []
        for mv in v15_moves:
            prod_v15 = mv["product_id"][0] if mv["product_id"] else False
            prod_v19 = get_map("product.product", prod_v15) if prod_v15 else False
            if not prod_v19:
                log.warning("  Move %d: product v15#%s still not mapped", mv["id"], prod_v15)
                continue

            uom_v15 = mv["product_uom"][0] if mv["product_uom"] else False
            uom_v19 = get_map("uom.uom", uom_v15) if uom_v15 else False

            mv_loc_v19 = get_map("stock.location", mv["location_id"][0]) if mv["location_id"] else loc_v19
            mv_locd_v19 = get_map("stock.location", mv["location_dest_id"][0]) if mv["location_dest_id"] else loc_dest_v19

            mvals = {
                "description_picking": mv.get("name") or "/",
                "product_id": prod_v19,
                "product_uom_qty": mv.get("product_uom_qty", 0),
                "location_id": mv_loc_v19,
                "location_dest_id": mv_locd_v19,
                "date": mv.get("date") or pick["scheduled_date"],
            }
            if uom_v19:
                mvals["product_uom"] = uom_v19

            if mv.get("sale_line_id"):
                sol_v19 = get_map("sale.order.line", mv["sale_line_id"][0])
                if sol_v19:
                    mvals["sale_line_id"] = sol_v19
            if mv.get("purchase_line_id"):
                pol_v19 = get_map("purchase.order.line", mv["purchase_line_id"][0])
                if pol_v19:
                    mvals["purchase_line_id"] = pol_v19

            move_cmds.append((0, 0, mvals))

        if not move_cmds:
            pick_errors += 1
            continue

        vals = {
            "picking_type_id": pt_v19,
            "location_id": loc_v19,
            "location_dest_id": loc_dest_v19,
            "scheduled_date": pick["scheduled_date"],
            "origin": pick.get("origin") or False,
            "move_type": pick.get("move_type") or "direct",
            "move_ids": move_cmds,
        }

        partner_v15 = pick["partner_id"][0] if pick["partner_id"] else False
        if partner_v15:
            partner_v19 = get_map("res.partner", partner_v15)
            if partner_v19:
                vals["partner_id"] = partner_v19

        try:
            v19_id = v19_create("stock.picking", vals)
            set_map("stock.picking", pick["id"], v19_id)
            pick_created += 1

            target_state = PICKING_STATE_MAP.get(pick["state"], "draft")
            if target_state != "draft":
                pick_states_sql.append((v19_id, target_state, pick.get("date_done")))

        except Exception as e:
            pick_errors += 1
            log.error("  Picking %s (v15#%d) FAILED: %s", pick["name"], pick["id"], e)

    log.info("  Pickings created: %d (errors: %d)", pick_created, pick_errors)

    # ── Step 3: Map new moves + set states ───────────────────────────

    log.info("=== Step 3: Map moves + set states ===")

    new_move_mapped = 0
    move_updates = []

    for pick in unmapped_picks:
        v19_pick_id = get_map("stock.picking", pick["id"])
        if not v19_pick_id:
            continue

        v15_moves = moves_by_picking.get(pick["id"], [])
        if not v15_moves:
            continue

        v19_moves = v19_search_read("stock.move", [["picking_id", "=", v19_pick_id]], ["id", "product_id"], order="id asc")

        v15_valid = []
        for mv in sorted(v15_moves, key=lambda x: x["id"]):
            prod_v15 = mv["product_id"][0] if mv["product_id"] else False
            if prod_v15 and get_map("product.product", prod_v15):
                v15_valid.append(mv)

        for i, v15_mv in enumerate(v15_valid):
            if i < len(v19_moves):
                set_map("stock.move", v15_mv["id"], v19_moves[i]["id"])
                new_move_mapped += 1

                target_state = MOVE_STATE_MAP.get(v15_mv["state"], "draft")
                qty_done = v15_mv.get("quantity_done", 0)
                date = v15_mv.get("date")
                move_updates.append((v19_moves[i]["id"], target_state, qty_done, date))

    log.info("  New moves mapped: %d", new_move_mapped)

    # Set picking states
    if pick_states_sql:
        by_state = {}
        date_done_updates = []
        for v19_id, state, date_done in pick_states_sql:
            by_state.setdefault(state, []).append(v19_id)
            if date_done and state == "done":
                date_done_updates.append((v19_id, date_done))

        for state, ids in by_state.items():
            ids_str = ",".join(str(i) for i in ids)
            _run_sql("UPDATE stock_picking SET state = '%s' WHERE id IN (%s)" % (state, ids_str))
            log.info("  Set %d pickings to state='%s'", len(ids), state)

        if date_done_updates:
            cases = ["WHEN %d THEN '%s'::timestamp" % (v19_id, dd) for v19_id, dd in date_done_updates]
            done_ids = [str(v19_id) for v19_id, _ in date_done_updates]
            _run_sql("UPDATE stock_picking SET date_done = CASE id %s END WHERE id IN (%s)" % (
                " ".join(cases), ",".join(done_ids)))
            log.info("  Set date_done for %d pickings", len(date_done_updates))

    # Set move states + quantity
    if move_updates:
        by_state = {}
        for v19_id, state, _, _ in move_updates:
            by_state.setdefault(state, []).append(v19_id)

        for state, ids in by_state.items():
            if state == "draft":
                continue
            ids_str = ",".join(str(i) for i in ids)
            _run_sql("UPDATE stock_move SET state = '%s' WHERE id IN (%s)" % (state, ids_str))
            log.info("  Set %d moves to state='%s'", len(ids), state)

        done_updates = [(vid, qty, dt) for vid, st, qty, dt in move_updates if st == "done" and qty > 0]
        if done_updates:
            cases_qty = ["WHEN %d THEN %s" % (v19_id, qty) for v19_id, qty, _ in done_updates]
            cases_date = ["WHEN %d THEN '%s'::timestamp" % (v19_id, dt) for v19_id, _, dt in done_updates if dt]
            ids_str = ",".join(str(v19_id) for v19_id, _, _ in done_updates)
            sql = "UPDATE stock_move SET quantity = CASE id %s END" % " ".join(cases_qty)
            if cases_date:
                sql += ", date = CASE id %s END" % " ".join(cases_date)
            sql += " WHERE id IN (%s)" % ids_str
            _run_sql(sql)
            log.info("  Set quantity for %d done moves", len(done_updates))

        done_move_ids = [vid for vid, st, _, _ in move_updates if st == "done"]
        if done_move_ids:
            ids_str = ",".join(str(i) for i in done_move_ids)
            _run_sql("UPDATE stock_move SET picked = true WHERE id IN (%s)" % ids_str)
            log.info("  Set picked=true for %d moves", len(done_move_ids))

    # Save id_map
    raw = {model: {str(k): v for k, v in pairs.items()} for model, pairs in id_map.items()}
    with open(MAP_FILE, "w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2, ensure_ascii=False)
    log.info("id_map saved: %d models, %d mappings",
             len(id_map), sum(len(v) for v in id_map.values()))

    # Final verification
    total_picks_v19 = int(_run_sql("SELECT count(*) FROM stock_picking;").strip().split("\n")[2].strip())
    total_moves_v19 = int(_run_sql("SELECT count(*) FROM stock_move;").strip().split("\n")[2].strip())
    log.info("=== DONE === V19 pickings: %d, moves: %d", total_picks_v19, total_moves_v19)


if __name__ == "__main__":
    main()
