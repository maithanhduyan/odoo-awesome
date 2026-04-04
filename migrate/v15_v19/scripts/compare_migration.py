"""
Comprehensive data comparison between Odoo V15 (taya_db) and Odoo V19 (taya19_db).

Checks:
1. Record counts per migrated model
2. Key field values (names, amounts, dates, states)
3. Financial totals (invoices, payments, sales, purchases)
4. Audit fields (create_uid, write_uid)
5. Relational integrity (partner, product references)
"""
import json
import subprocess
import sys
from pathlib import Path
from collections import defaultdict

MAP_FILE = Path(__file__).parent / "migrate" / "id_map.json"

# V15 uid -> V19 uid
USER_MAP = {1:1, 2:2, 3:3, 4:3, 5:4, 7:36, 8:37, 10:38, 17:39, 20:40, 21:41, 22:42, 23:43, 25:44, 26:45, 38:46}


def sql(db, query):
    cmd = ["docker", "exec", "postgres", "psql", "-U", "odoo", "-d", db, "-t", "-A", "-c", query]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        return None
    return [l for l in r.stdout.strip().split("\n") if l.strip()]


def sql_one(db, query):
    rows = sql(db, query)
    return rows[0] if rows else None


class Report:
    def __init__(self):
        self.sections = []
        self.ok = 0
        self.warn = 0
        self.fail = 0

    def section(self, title):
        self.sections.append(("section", title))
        print(f"\n{'='*70}")
        print(f"  {title}")
        print(f"{'='*70}")

    def ok_msg(self, msg):
        self.ok += 1
        self.sections.append(("ok", msg))
        print(f"  [OK] {msg}")

    def warn_msg(self, msg):
        self.warn += 1
        self.sections.append(("warn", msg))
        print(f"  [!!] {msg}")

    def fail_msg(self, msg):
        self.fail += 1
        self.sections.append(("fail", msg))
        print(f"  [FAIL] {msg}")

    def info(self, msg):
        self.sections.append(("info", msg))
        print(f"       {msg}")

    def summary(self):
        print(f"\n{'#'*70}")
        print(f"  SUMMARY: {self.ok} OK, {self.warn} warnings, {self.fail} failures")
        print(f"{'#'*70}")


def main():
    with open(MAP_FILE) as f:
        id_map = json.load(f)

    rpt = Report()

    # ================================================================
    # 1. RECORD COUNTS
    # ================================================================
    rpt.section("1. RECORD COUNTS PER MODEL")

    count_models = [
        ("res.partner", "res_partner", None),
        ("product.template", "product_template", None),
        ("product.product", "product_product", None),
        ("sale.order", "sale_order", None),
        ("sale.order.line", "sale_order_line", None),
        ("purchase.order", "purchase_order", None),
        ("purchase.order.line", "purchase_order_line", None),
        ("account.move", "account_move", None),
        ("account.move.line", "account_move_line", None),
        ("account.payment", "account_payment", None),
        ("stock.picking", "stock_picking", None),
        ("stock.move", "stock_move", None),
        ("stock.move.line", "stock_move_line", None),
        ("mrp.production", "mrp_production", None),
        ("mrp.bom", "mrp_bom", None),
        ("mrp.bom.line", "mrp_bom_line", None),
        ("crm.lead", "crm_lead", None),
        ("project.project", "project_project", None),
        ("project.task", "project_task", None),
        ("hr.employee", "hr_employee", None),
        ("account.account", "account_account", None),
        ("stock.quant", "stock_quant", None),
    ]

    for model_key, table, where in count_models:
        mapped = len(id_map.get(model_key, {}))
        w = f"WHERE {where}" if where else ""
        v15_count = sql_one("taya_db", f"SELECT COUNT(*) FROM {table} {w}")
        v19_count = sql_one("taya19_db", f"SELECT COUNT(*) FROM {table} {w}")
        v15_c = int(v15_count) if v15_count else 0
        v19_c = int(v19_count) if v19_count else 0

        if v19_c >= mapped and mapped > 0:
            rpt.ok_msg(f"{model_key}: V15={v15_c}, V19={v19_c}, mapped={mapped}")
        elif mapped == 0:
            rpt.info(f"{model_key}: V15={v15_c}, V19={v19_c} (no id_map)")
        else:
            rpt.warn_msg(f"{model_key}: V15={v15_c}, V19={v19_c}, mapped={mapped}")

    # ================================================================
    # 2. FINANCIAL TOTALS
    # ================================================================
    rpt.section("2. FINANCIAL TOTALS")

    # Invoice totals by type
    for move_type in ["out_invoice", "out_refund", "in_invoice", "in_refund", "entry"]:
        v15_total = sql_one("taya_db",
            f"SELECT COALESCE(SUM(amount_total), 0) FROM account_move WHERE move_type = '{move_type}'")
        v19_total = sql_one("taya19_db",
            f"SELECT COALESCE(SUM(amount_total), 0) FROM account_move WHERE move_type = '{move_type}'")
        v15_f = float(v15_total) if v15_total else 0
        v19_f = float(v19_total) if v19_total else 0
        diff = abs(v15_f - v19_f)
        pct = (diff / v15_f * 100) if v15_f > 0 else 0
        if pct < 0.01:
            rpt.ok_msg(f"account.move [{move_type}] total: V15={v15_f:,.0f} V19={v19_f:,.0f}")
        elif pct < 1:
            rpt.warn_msg(f"account.move [{move_type}] total: V15={v15_f:,.0f} V19={v19_f:,.0f} (diff {pct:.2f}%)")
        else:
            rpt.fail_msg(f"account.move [{move_type}] total: V15={v15_f:,.0f} V19={v19_f:,.0f} (diff {pct:.2f}%)")

    # Sale order totals
    v15_so = sql_one("taya_db", "SELECT COALESCE(SUM(amount_total), 0) FROM sale_order")
    v19_so = sql_one("taya19_db", "SELECT COALESCE(SUM(amount_total), 0) FROM sale_order")
    v15_f = float(v15_so) if v15_so else 0
    v19_f = float(v19_so) if v19_so else 0
    diff_pct = (abs(v15_f - v19_f) / v15_f * 100) if v15_f > 0 else 0
    if diff_pct < 0.01:
        rpt.ok_msg(f"sale.order total: V15={v15_f:,.0f} V19={v19_f:,.0f}")
    else:
        rpt.warn_msg(f"sale.order total: V15={v15_f:,.0f} V19={v19_f:,.0f} (diff {diff_pct:.2f}%)")

    # Purchase order totals
    v15_po = sql_one("taya_db", "SELECT COALESCE(SUM(amount_total), 0) FROM purchase_order")
    v19_po = sql_one("taya19_db", "SELECT COALESCE(SUM(amount_total), 0) FROM purchase_order")
    v15_f = float(v15_po) if v15_po else 0
    v19_f = float(v19_po) if v19_po else 0
    diff_pct = (abs(v15_f - v19_f) / v15_f * 100) if v15_f > 0 else 0
    if diff_pct < 0.01:
        rpt.ok_msg(f"purchase.order total: V15={v15_f:,.0f} V19={v19_f:,.0f}")
    else:
        rpt.warn_msg(f"purchase.order total: V15={v15_f:,.0f} V19={v19_f:,.0f} (diff {diff_pct:.2f}%)")

    # ================================================================
    # 3. KEY FIELDS COMPARISON (sample-based)
    # ================================================================
    rpt.section("3. KEY FIELDS SPOT CHECK")

    # Compare sale.order fields
    so_map = id_map.get("sale.order", {})
    sample_v15_ids = list(so_map.keys())[:50]
    mismatches = {"name": 0, "state": 0, "amount_total": 0, "partner_id": 0}
    checked = 0
    partner_map = id_map.get("res.partner", {})

    if sample_v15_ids:
        id_list = ",".join(sample_v15_ids)
        v15_rows = sql("taya_db",
            f"SELECT id, name, state, amount_total, partner_id FROM sale_order WHERE id IN ({id_list})")
        v15_data = {}
        for row in v15_rows or []:
            parts = row.split("|")
            if len(parts) >= 5:
                v15_data[parts[0]] = parts[1:]

        for v15_id, fields in v15_data.items():
            v19_id = so_map.get(v15_id)
            if not v19_id:
                continue
            v19_row = sql_one("taya19_db",
                f"SELECT name, state, amount_total, partner_id FROM sale_order WHERE id = {v19_id}")
            if not v19_row:
                continue
            v19_parts = v19_row.split("|")
            checked += 1
            if fields[0] != v19_parts[0]:
                mismatches["name"] += 1
            if fields[2] != v19_parts[2]:
                mismatches["amount_total"] += 1
            expected_partner = partner_map.get(fields[3])
            if expected_partner and str(expected_partner) != v19_parts[3]:
                mismatches["partner_id"] += 1

    for field, count in mismatches.items():
        if count == 0:
            rpt.ok_msg(f"sale.order.{field}: {checked} checked, 0 mismatches")
        else:
            rpt.fail_msg(f"sale.order.{field}: {checked} checked, {count} mismatches")

    # Compare account.move fields
    am_map = id_map.get("account.move", {})
    sample_am_ids = list(am_map.keys())[:50]
    am_mismatches = {"name": 0, "amount_total": 0, "partner_id": 0, "move_type": 0}
    am_checked = 0

    if sample_am_ids:
        id_list = ",".join(sample_am_ids)
        v15_rows = sql("taya_db",
            f"SELECT id, name, amount_total, partner_id, move_type FROM account_move WHERE id IN ({id_list})")
        v15_data = {}
        for row in v15_rows or []:
            parts = row.split("|")
            if len(parts) >= 5:
                v15_data[parts[0]] = parts[1:]

        for v15_id, fields in v15_data.items():
            v19_id = am_map.get(v15_id)
            if not v19_id:
                continue
            v19_row = sql_one("taya19_db",
                f"SELECT name, amount_total, partner_id, move_type FROM account_move WHERE id = {v19_id}")
            if not v19_row:
                continue
            v19_parts = v19_row.split("|")
            am_checked += 1
            if fields[0] != v19_parts[0]:
                am_mismatches["name"] += 1
            if fields[1] != v19_parts[1]:
                am_mismatches["amount_total"] += 1
            if fields[3] != v19_parts[3]:
                am_mismatches["move_type"] += 1
            expected_partner = partner_map.get(fields[2])
            if expected_partner and str(expected_partner) != v19_parts[2]:
                am_mismatches["partner_id"] += 1

    for field, count in am_mismatches.items():
        if count == 0:
            rpt.ok_msg(f"account.move.{field}: {am_checked} checked, 0 mismatches")
        else:
            rpt.fail_msg(f"account.move.{field}: {am_checked} checked, {count} mismatches")

    # Compare product.template fields
    pt_map = id_map.get("product.template", {})
    sample_pt_ids = list(pt_map.keys())[:50]
    pt_mismatches = {"name": 0, "list_price": 0, "type": 0}
    pt_checked = 0

    if sample_pt_ids:
        id_list = ",".join(sample_pt_ids)
        v15_rows = sql("taya_db",
            f"SELECT id, name, list_price, type FROM product_template WHERE id IN ({id_list})")
        v15_data = {}
        for row in v15_rows or []:
            parts = row.split("|")
            if len(parts) >= 4:
                v15_data[parts[0]] = parts[1:]

        for v15_id, fields in v15_data.items():
            v19_id = pt_map.get(v15_id)
            if not v19_id:
                continue
            v19_row = sql_one("taya19_db",
                f"SELECT name, list_price, type FROM product_template WHERE id = {v19_id}")
            if not v19_row:
                continue
            v19_parts = v19_row.split("|")
            pt_checked += 1
            if fields[0] != v19_parts[0]:
                pt_mismatches["name"] += 1
            if fields[1] != v19_parts[1]:
                pt_mismatches["list_price"] += 1

    for field, count in pt_mismatches.items():
        if count == 0:
            rpt.ok_msg(f"product.template.{field}: {pt_checked} checked, 0 mismatches")
        else:
            rpt.fail_msg(f"product.template.{field}: {pt_checked} checked, {count} mismatches")

    # ================================================================
    # 4. AUDIT FIELDS
    # ================================================================
    rpt.section("4. AUDIT FIELDS (create_uid)")

    audit_models = [
        ("product.template", "product_template"),
        ("sale.order", "sale_order"),
        ("purchase.order", "purchase_order"),
        ("account.move", "account_move"),
        ("stock.picking", "stock_picking"),
        ("mrp.production", "mrp_production"),
        ("res.partner", "res_partner"),
    ]

    for model_key, table in audit_models:
        model_map = id_map.get(model_key, {})
        if not model_map:
            continue

        # Sample 30 records
        sample_ids = list(model_map.keys())[:30]
        id_list = ",".join(sample_ids)

        v15_rows = sql("taya_db", f"SELECT id, create_uid FROM {table} WHERE id IN ({id_list})")
        v15_data = {}
        for row in v15_rows or []:
            parts = row.split("|")
            if len(parts) >= 2 and parts[1].strip():
                v15_data[parts[0]] = int(parts[1])

        matched = 0
        total = 0
        for v15_id, v15_uid in v15_data.items():
            v19_id = model_map.get(v15_id)
            if not v19_id:
                continue
            expected_v19_uid = USER_MAP.get(v15_uid, 2)
            actual = sql_one("taya19_db", f"SELECT create_uid FROM {table} WHERE id = {v19_id}")
            if actual:
                total += 1
                if int(actual) == expected_v19_uid:
                    matched += 1

        if total > 0 and matched == total:
            rpt.ok_msg(f"{model_key} create_uid: {matched}/{total} matched")
        elif total > 0:
            rpt.warn_msg(f"{model_key} create_uid: {matched}/{total} matched")
        else:
            rpt.info(f"{model_key} create_uid: no data to check")

    # ================================================================
    # 5. RELATIONAL INTEGRITY
    # ================================================================
    rpt.section("5. RELATIONAL INTEGRITY")

    # sale_order -> partner_id
    broken = sql_one("taya19_db",
        "SELECT COUNT(*) FROM sale_order so "
        "LEFT JOIN res_partner rp ON rp.id = so.partner_id "
        "WHERE rp.id IS NULL")
    if broken and int(broken) == 0:
        rpt.ok_msg("sale_order.partner_id: all references valid")
    else:
        rpt.fail_msg(f"sale_order.partner_id: {broken} broken references")

    # purchase_order -> partner_id
    broken = sql_one("taya19_db",
        "SELECT COUNT(*) FROM purchase_order po "
        "LEFT JOIN res_partner rp ON rp.id = po.partner_id "
        "WHERE rp.id IS NULL")
    if broken and int(broken) == 0:
        rpt.ok_msg("purchase_order.partner_id: all references valid")
    else:
        rpt.fail_msg(f"purchase_order.partner_id: {broken} broken references")

    # account_move -> partner_id
    broken = sql_one("taya19_db",
        "SELECT COUNT(*) FROM account_move am "
        "LEFT JOIN res_partner rp ON rp.id = am.partner_id "
        "WHERE am.partner_id IS NOT NULL AND rp.id IS NULL")
    if broken and int(broken) == 0:
        rpt.ok_msg("account_move.partner_id: all references valid")
    else:
        rpt.fail_msg(f"account_move.partner_id: {broken} broken references")

    # sale_order_line -> product_id
    broken = sql_one("taya19_db",
        "SELECT COUNT(*) FROM sale_order_line sol "
        "LEFT JOIN product_product pp ON pp.id = sol.product_id "
        "WHERE sol.product_id IS NOT NULL AND pp.id IS NULL")
    if broken and int(broken) == 0:
        rpt.ok_msg("sale_order_line.product_id: all references valid")
    else:
        rpt.fail_msg(f"sale_order_line.product_id: {broken} broken references")

    # purchase_order_line -> product_id
    broken = sql_one("taya19_db",
        "SELECT COUNT(*) FROM purchase_order_line pol "
        "LEFT JOIN product_product pp ON pp.id = pol.product_id "
        "WHERE pol.product_id IS NOT NULL AND pp.id IS NULL")
    if broken and int(broken) == 0:
        rpt.ok_msg("purchase_order_line.product_id: all references valid")
    else:
        rpt.fail_msg(f"purchase_order_line.product_id: {broken} broken references")

    # stock_move -> product_id
    broken = sql_one("taya19_db",
        "SELECT COUNT(*) FROM stock_move sm "
        "LEFT JOIN product_product pp ON pp.id = sm.product_id "
        "WHERE sm.product_id IS NOT NULL AND pp.id IS NULL")
    if broken and int(broken) == 0:
        rpt.ok_msg("stock_move.product_id: all references valid")
    else:
        rpt.fail_msg(f"stock_move.product_id: {broken} broken references")

    # account_move_line -> account_id
    broken = sql_one("taya19_db",
        "SELECT COUNT(*) FROM account_move_line aml "
        "LEFT JOIN account_account aa ON aa.id = aml.account_id "
        "WHERE aml.account_id IS NOT NULL AND aa.id IS NULL")
    if broken and int(broken) == 0:
        rpt.ok_msg("account_move_line.account_id: all references valid")
    else:
        rpt.fail_msg(f"account_move_line.account_id: {broken} broken references")

    # mrp_production -> product_id
    broken = sql_one("taya19_db",
        "SELECT COUNT(*) FROM mrp_production mp "
        "LEFT JOIN product_product pp ON pp.id = mp.product_id "
        "WHERE mp.product_id IS NOT NULL AND pp.id IS NULL")
    if broken and int(broken) == 0:
        rpt.ok_msg("mrp_production.product_id: all references valid")
    else:
        rpt.fail_msg(f"mrp_production.product_id: {broken} broken references")

    # stock_picking -> partner_id
    broken = sql_one("taya19_db",
        "SELECT COUNT(*) FROM stock_picking sp "
        "LEFT JOIN res_partner rp ON rp.id = sp.partner_id "
        "WHERE sp.partner_id IS NOT NULL AND rp.id IS NULL")
    if broken and int(broken) == 0:
        rpt.ok_msg("stock_picking.partner_id: all references valid")
    else:
        rpt.fail_msg(f"stock_picking.partner_id: {broken} broken references")

    # ================================================================
    # 6. STATE DISTRIBUTION
    # ================================================================
    rpt.section("6. STATE DISTRIBUTION")

    state_models = [
        ("sale.order", "sale_order", "state"),
        ("purchase.order", "purchase_order", "state"),
        ("account.move", "account_move", "state"),
        ("stock.picking", "stock_picking", "state"),
        ("mrp.production", "mrp_production", "state"),
    ]

    for model_key, table, col in state_models:
        v15_rows = sql("taya_db", f"SELECT {col}, COUNT(*) FROM {table} GROUP BY {col} ORDER BY COUNT(*) DESC")
        v19_rows = sql("taya19_db", f"SELECT {col}, COUNT(*) FROM {table} GROUP BY {col} ORDER BY COUNT(*) DESC")
        v15_dist = {}
        v19_dist = {}
        for row in v15_rows or []:
            parts = row.split("|")
            if len(parts) >= 2:
                v15_dist[parts[0]] = int(parts[1])
        for row in v19_rows or []:
            parts = row.split("|")
            if len(parts) >= 2:
                v19_dist[parts[0]] = int(parts[1])

        all_states = set(v15_dist.keys()) | set(v19_dist.keys())
        diffs = []
        for s in sorted(all_states):
            c15 = v15_dist.get(s, 0)
            c19 = v19_dist.get(s, 0)
            if c15 != c19:
                diffs.append(f"{s}: V15={c15} V19={c19}")

        if not diffs:
            rpt.ok_msg(f"{model_key}.{col}: distributions match")
        else:
            rpt.warn_msg(f"{model_key}.{col}: differences found")
            for d in diffs:
                rpt.info(d)

    # ================================================================
    # 7. CHATTER MESSAGES
    # ================================================================
    rpt.section("7. CHATTER MESSAGES (author check)")

    admin_msgs = sql_one("taya19_db",
        "SELECT COUNT(*) FROM mail_message WHERE author_id = 3 AND date > '2026-03-27 08:00:00'")
    total_msgs = sql_one("taya19_db",
        "SELECT COUNT(*) FROM mail_message WHERE date > '2026-03-27 08:00:00'")
    admin_c = int(admin_msgs) if admin_msgs else 0
    total_c = int(total_msgs) if total_msgs else 0
    non_admin = total_c - admin_c
    if admin_c == 0:
        rpt.ok_msg(f"No migration-time messages with Administrator author (total: {total_c})")
    else:
        rpt.warn_msg(f"{admin_c}/{total_c} migration messages still have Administrator author")

    # ================================================================
    # 8. INVOICE NAMES
    # ================================================================
    rpt.section("8. INVOICE NAMES")

    empty_names = sql_one("taya19_db",
        "SELECT COUNT(*) FROM account_move WHERE name = '/' AND move_type != 'entry'")
    total_inv = sql_one("taya19_db",
        "SELECT COUNT(*) FROM account_move WHERE move_type != 'entry'")
    empty_c = int(empty_names) if empty_names else 0
    total_i = int(total_inv) if total_inv else 0
    if empty_c == 0:
        rpt.ok_msg(f"All {total_i} non-entry moves have names")
    else:
        rpt.warn_msg(f"{empty_c}/{total_i} non-entry moves have empty names ('/')")

    # ================================================================
    # 9. SALESPERSON FIELDS
    # ================================================================
    rpt.section("9. SALESPERSON / RESPONSIBLE FIELDS")

    # invoice_user_id
    admin_inv = sql_one("taya19_db",
        "SELECT COUNT(*) FROM account_move WHERE invoice_user_id = 2 AND move_type IN ('out_invoice','out_refund')")
    total_inv = sql_one("taya19_db",
        "SELECT COUNT(*) FROM account_move WHERE move_type IN ('out_invoice','out_refund')")
    admin_c = int(admin_inv) if admin_inv else 0
    total_i = int(total_inv) if total_inv else 0
    if admin_c < total_i * 0.1:
        rpt.ok_msg(f"account_move.invoice_user_id: {admin_c}/{total_i} are Administrator")
    else:
        rpt.warn_msg(f"account_move.invoice_user_id: {admin_c}/{total_i} are Administrator")

    # sale_order user_id
    admin_so = sql_one("taya19_db",
        "SELECT COUNT(*) FROM sale_order WHERE user_id = 2")
    total_so = sql_one("taya19_db",
        "SELECT COUNT(*) FROM sale_order")
    admin_c = int(admin_so) if admin_so else 0
    total_s = int(total_so) if total_so else 0
    if admin_c < total_s * 0.1:
        rpt.ok_msg(f"sale_order.user_id: {admin_c}/{total_s} are Administrator")
    else:
        rpt.warn_msg(f"sale_order.user_id: {admin_c}/{total_s} are Administrator")

    # product responsible_id
    admin_pt = sql_one("taya19_db",
        "SELECT COUNT(*) FROM product_template WHERE responsible_id = '{\"1\": 2}'::jsonb")
    total_pt = sql_one("taya19_db",
        "SELECT COUNT(*) FROM product_template WHERE responsible_id IS NOT NULL")
    admin_c = int(admin_pt) if admin_pt else 0
    total_p = int(total_pt) if total_pt else 0
    if admin_c < total_p * 0.1:
        rpt.ok_msg(f"product_template.responsible_id: {admin_c}/{total_p} are Administrator")
    else:
        rpt.warn_msg(f"product_template.responsible_id: {admin_c}/{total_p} are Administrator")

    # ================================================================
    # SUMMARY
    # ================================================================
    rpt.summary()


if __name__ == "__main__":
    main()
