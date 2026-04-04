"""
Fix audit fields (create_uid, write_uid, create_date, write_date) in V19
to match the original values from V15.

During migration via XML-RPC, all records got create_uid=2 (Administrator).
This script restores the original creator/writer from V15 using id_map.json.
"""
import json
import subprocess
import sys
from pathlib import Path

MAP_FILE = Path(__file__).parent / "migrate" / "id_map.json"

# V15 login -> V19 uid mapping (by login match)
USER_MAP_V15_TO_V19 = {
    1: 1,    # __system__ (V15 OdooBot uid=1 -> V19 __system__)
    2: 2,    # tayafood@gmail.com
    3: 3,    # default -> public (closest)
    4: 3,    # public -> public
    5: 4,    # portaltemplate
    7: 36,   # anmtt@tayafood.com (Mai An)
    8: 37,   # yann@tayafood.com
    10: 38,  # nijimise@gmail.com
    17: 39,  # anmtd@tayafood.com
    20: 40,  # admin@tayafood.com
    21: 41,  # sale@tayafood.com
    22: 42,  # ninguyenthihien@tayafood.com
    23: 43,  # trangntt@tayafood.com
    25: 44,  # root@example.com
    26: 45,  # ketoan@tayafood.com
    38: 46,  # chanhnt@tayafood.com
}

# Models to fix: (v15_table, v19_table, id_map_model_key)
# These are models that have id_map entries (V15 id -> V19 id)
MODELS = [
    ("res_partner", "res_partner", "res.partner"),
    ("product_template", "product_template", "product.template"),
    ("product_product", "product_product", "product.product"),
    ("sale_order", "sale_order", "sale.order"),
    ("sale_order_line", "sale_order_line", "sale.order.line"),
    ("purchase_order", "purchase_order", "purchase.order"),
    ("purchase_order_line", "purchase_order_line", "purchase.order.line"),
    ("account_move", "account_move", "account.move"),
    ("account_move_line", "account_move_line", "account.move.line"),
    ("account_payment", "account_payment", "account.payment"),
    ("stock_picking", "stock_picking", "stock.picking"),
    ("stock_move", "stock_move", "stock.move"),
    ("stock_move_line", "stock_move_line", "stock.move.line"),
    ("mrp_production", "mrp_production", "mrp.production"),
    ("mrp_bom", "mrp_bom", "mrp.bom"),
    ("hr_employee", "hr_employee", "hr.employee"),
    ("crm_lead", "crm_lead", "crm.lead"),
    ("project_project", "project_project", "project.project"),
    ("project_task", "project_task", "project.task"),
    ("ir_attachment", "ir_attachment", "ir.attachment"),
]


def run_sql(db, sql):
    cmd = ["docker", "exec", "postgres", "psql", "-U", "odoo", "-d", db, "-t", "-A", "-c", sql]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  SQL ERROR: {r.stderr.strip()[:200]}")
        return []
    return [l for l in r.stdout.strip().split("\n") if l.strip()]


def run_sql_no_output(db, sql):
    cmd = ["docker", "exec", "postgres", "psql", "-U", "odoo", "-d", db, "-t", "-A", "-c", sql]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  SQL ERROR: {r.stderr.strip()[:200]}")
        return False
    return True


def main():
    with open(MAP_FILE) as f:
        id_map = json.load(f)

    total_updated = 0
    total_skipped = 0

    for v15_table, v19_table, model_key in MODELS:
        model_map = id_map.get(model_key, {})
        if not model_map:
            print(f"SKIP {model_key}: no mappings")
            continue

        # Get V15 audit data for mapped records
        v15_ids = list(model_map.keys())

        # Process in chunks to avoid SQL too long
        CHUNK = 500
        all_v15_audit = {}

        for i in range(0, len(v15_ids), CHUNK):
            chunk_ids = v15_ids[i:i + CHUNK]
            id_list = ",".join(chunk_ids)
            rows = run_sql("taya_db",
                f"SELECT id, create_uid, write_uid, "
                f"to_char(create_date, 'YYYY-MM-DD HH24:MI:SS'), "
                f"to_char(write_date, 'YYYY-MM-DD HH24:MI:SS') "
                f"FROM {v15_table} WHERE id IN ({id_list})"
            )
            for row in rows:
                parts = row.split("|")
                if len(parts) >= 5:
                    v15_id = parts[0]
                    all_v15_audit[v15_id] = {
                        "create_uid": int(parts[1]) if parts[1] else None,
                        "write_uid": int(parts[2]) if parts[2] else None,
                        "create_date": parts[3] if parts[3] else None,
                        "write_date": parts[4] if parts[4] else None,
                    }

        if not all_v15_audit:
            print(f"SKIP {model_key}: no V15 audit data found")
            continue

        # Build batch UPDATE using CASE statements
        # Group by (create_uid, write_uid) to minimize SQL complexity
        updates = []  # (v19_id, v19_create_uid, v19_write_uid, create_date, write_date)
        skipped = 0

        for v15_id_str, audit in all_v15_audit.items():
            v19_id = model_map.get(v15_id_str)
            if not v19_id:
                skipped += 1
                continue

            v19_create_uid = USER_MAP_V15_TO_V19.get(audit["create_uid"], 2) if audit["create_uid"] else 2
            v19_write_uid = USER_MAP_V15_TO_V19.get(audit["write_uid"], 2) if audit["write_uid"] else 2

            updates.append((
                v19_id,
                v19_create_uid,
                v19_write_uid,
                audit["create_date"],
                audit["write_date"],
            ))

        if not updates:
            print(f"SKIP {model_key}: no updates needed")
            continue

        # Execute batch UPDATEs in chunks of 200
        BATCH = 200
        model_updated = 0

        for i in range(0, len(updates), BATCH):
            batch = updates[i:i + BATCH]

            create_uid_cases = []
            write_uid_cases = []
            create_date_cases = []
            write_date_cases = []
            ids = []

            for v19_id, cu, wu, cd, wd in batch:
                ids.append(str(v19_id))
                create_uid_cases.append(f"WHEN {v19_id} THEN {cu}")
                write_uid_cases.append(f"WHEN {v19_id} THEN {wu}")
                if cd:
                    create_date_cases.append(f"WHEN {v19_id} THEN '{cd}'::timestamp")
                if wd:
                    write_date_cases.append(f"WHEN {v19_id} THEN '{wd}'::timestamp")

            id_list = ",".join(ids)

            set_clauses = [
                f"create_uid = CASE id {' '.join(create_uid_cases)} ELSE create_uid END",
                f"write_uid = CASE id {' '.join(write_uid_cases)} ELSE write_uid END",
            ]
            if create_date_cases:
                set_clauses.append(
                    f"create_date = CASE id {' '.join(create_date_cases)} ELSE create_date END"
                )
            if write_date_cases:
                set_clauses.append(
                    f"write_date = CASE id {' '.join(write_date_cases)} ELSE write_date END"
                )

            sql = f"UPDATE {v19_table} SET {', '.join(set_clauses)} WHERE id IN ({id_list})"

            if run_sql_no_output("taya19_db", sql):
                model_updated += len(batch)

        total_updated += model_updated
        total_skipped += skipped
        print(f"  {model_key}: updated {model_updated}/{len(updates)} records" +
              (f" (skipped {skipped})" if skipped else ""))

    # Verification
    print(f"\n{'='*60}")
    print(f"TOTAL: updated {total_updated} records, skipped {total_skipped}")
    print(f"{'='*60}")

    print("\n--- Verification: product_template create_uid distribution ---")
    rows = run_sql("taya19_db",
        "SELECT u.login, COUNT(*) FROM product_template pt "
        "JOIN res_users u ON u.id = pt.create_uid "
        "GROUP BY u.login ORDER BY COUNT(*) DESC"
    )
    for row in rows:
        print(f"  {row}")

    print("\n--- Verification: account_move create_uid distribution ---")
    rows = run_sql("taya19_db",
        "SELECT u.login, am.move_type, COUNT(*) FROM account_move am "
        "JOIN res_users u ON u.id = am.create_uid "
        "GROUP BY u.login, am.move_type ORDER BY am.move_type, COUNT(*) DESC"
    )
    for row in rows:
        print(f"  {row}")

    print("\n--- Verification: sale_order create_uid distribution ---")
    rows = run_sql("taya19_db",
        "SELECT u.login, COUNT(*) FROM sale_order so "
        "JOIN res_users u ON u.id = so.create_uid "
        "GROUP BY u.login ORDER BY COUNT(*) DESC"
    )
    for row in rows:
        print(f"  {row}")


if __name__ == "__main__":
    main()
