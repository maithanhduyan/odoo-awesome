"""
Fix mail.message author_id and date for auto-generated chatter messages
created during migration. These messages show 'Administrator' instead of
the original creator from V15.

Strategy:
- For each model in id_map, find mail.message records authored by
  Administrator (partner_id=3) during migration window
- Map res_id -> V15 record -> V15 create_uid -> V19 partner_id
- Update author_id and date to match V15 originals
"""
import json
import subprocess
from pathlib import Path

MAP_FILE = Path(__file__).parent / "migrate" / "id_map.json"

# V15 user_id -> V19 partner_id (via login matching)
V15_UID_TO_V19_PARTNER = {
    1: 2,     # system -> OdooBot
    2: 3,     # tayafood -> Administrator
    3: 4,     # default -> Public
    4: 4,     # public -> Public user
    5: 5,     # portaltemplate -> Portal User Template
    7: 330,   # anmtt -> Mai An
    8: 331,   # yann -> Nguyễn Y Ẩn
    10: 332,  # nijimise -> Nijimise Shop
    17: 333,  # anmtd -> Mai Thành Duy An
    20: 334,  # admin -> Admin
    21: 335,  # sale -> Sale (Chatbot)
    22: 336,  # ninguyenthihien -> Nguyễn Thị Hiền Ni
    23: 337,  # trangntt -> Nguyễn Thị Thùy Trang
    25: 338,  # root -> OdooBot (sao chép)
    26: 339,  # ketoan -> Kế Toán
    38: 340,  # chanhnt -> Nguyễn Thị Chánh
}

# Models with id_map entries that have mail.message tracking
MODELS = [
    ("sale_order", "sale.order"),
    ("purchase_order", "purchase.order"),
    ("account_move", "account.move"),
    ("account_payment", "account.payment"),
    ("stock_picking", "stock.picking"),
    ("mrp_production", "mrp.production"),
    ("mrp_bom", "mrp.bom"),
    ("product_template", "product.template"),
    ("product_product", "product.product"),
    ("res_partner", "res.partner"),
    ("crm_lead", "crm.lead"),
    ("project_project", "project.project"),
    ("project_task", "project.task"),
    ("hr_employee", "hr.employee"),
]


def run_sql(db, sql):
    cmd = ["docker", "exec", "postgres", "psql", "-U", "odoo", "-d", db, "-t", "-A", "-c", sql]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  SQL ERROR: {r.stderr.strip()[:200]}")
        return []
    return [l for l in r.stdout.strip().split("\n") if l.strip()]


def run_sql_exec(db, sql):
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

    for v15_table, model_key in MODELS:
        model_map = id_map.get(model_key, {})
        if not model_map:
            continue

        # Build reverse map: V19 id -> V15 id
        v19_to_v15 = {int(v): int(k) for k, v in model_map.items()}
        v19_ids = list(v19_to_v15.keys())

        # Get V15 create_uid and create_date for all mapped records
        v15_ids = [str(v15_to_v15) for v15_to_v15 in v19_to_v15.values()]
        v15_audit = {}  # v15_id -> (create_uid, create_date)

        CHUNK = 500
        for i in range(0, len(v15_ids), CHUNK):
            chunk = v15_ids[i:i + CHUNK]
            id_list = ",".join(chunk)
            rows = run_sql("taya_db",
                f"SELECT id, create_uid, to_char(create_date, 'YYYY-MM-DD HH24:MI:SS') "
                f"FROM {v15_table} WHERE id IN ({id_list})"
            )
            for row in rows:
                parts = row.split("|")
                if len(parts) >= 3:
                    v15_audit[int(parts[0])] = (
                        int(parts[1]) if parts[1] else None,
                        parts[2] if parts[2] else None,
                    )

        # Get V19 mail.message records for this model authored by Administrator (3)
        # during migration window
        v19_id_list = ",".join(str(x) for x in v19_ids)

        # Process in chunks to avoid SQL too long
        all_messages = []  # (msg_id, res_id)
        for i in range(0, len(v19_ids), CHUNK):
            chunk_ids = v19_ids[i:i + CHUNK]
            id_list = ",".join(str(x) for x in chunk_ids)
            rows = run_sql("taya19_db",
                f"SELECT id, res_id FROM mail_message "
                f"WHERE model = '{model_key}' "
                f"AND res_id IN ({id_list}) "
                f"AND author_id = 3 "
                f"AND date > '2026-03-27 08:00:00'"
            )
            for row in rows:
                parts = row.split("|")
                if len(parts) >= 2:
                    all_messages.append((int(parts[0]), int(parts[1])))

        if not all_messages:
            print(f"  {model_key}: no messages to fix")
            continue

        # Build updates: (msg_id, new_author_partner_id, new_date)
        updates = []
        for msg_id, v19_res_id in all_messages:
            v15_id = v19_to_v15.get(v19_res_id)
            if not v15_id:
                continue
            audit = v15_audit.get(v15_id)
            if not audit:
                continue
            v15_create_uid, v15_create_date = audit
            if v15_create_uid is None:
                continue
            new_partner = V15_UID_TO_V19_PARTNER.get(v15_create_uid, 3)
            updates.append((msg_id, new_partner, v15_create_date))

        if not updates:
            print(f"  {model_key}: no updates needed")
            continue

        # Batch UPDATE
        BATCH = 200
        model_updated = 0
        for i in range(0, len(updates), BATCH):
            batch = updates[i:i + BATCH]
            author_cases = []
            date_cases = []
            ids = []
            for msg_id, partner_id, create_date in batch:
                ids.append(str(msg_id))
                author_cases.append(f"WHEN {msg_id} THEN {partner_id}")
                if create_date:
                    date_cases.append(f"WHEN {msg_id} THEN '{create_date}'::timestamp")

            id_list = ",".join(ids)
            set_clauses = [
                f"author_id = CASE id {' '.join(author_cases)} ELSE author_id END"
            ]
            if date_cases:
                set_clauses.append(
                    f"date = CASE id {' '.join(date_cases)} ELSE date END"
                )

            sql = f"UPDATE mail_message SET {', '.join(set_clauses)} WHERE id IN ({id_list})"
            if run_sql_exec("taya19_db", sql):
                model_updated += len(batch)

        total_updated += model_updated
        print(f"  {model_key}: fixed {model_updated}/{len(all_messages)} messages")

    print(f"\n{'='*60}")
    print(f"TOTAL: fixed {total_updated} mail.message records")
    print(f"{'='*60}")

    # Verify sale_order 992
    print("\n--- Verification: sale_order 992 chatter ---")
    rows = run_sql("taya19_db",
        "SELECT mm.id, rp.name, mm.date, left(mm.body, 80) "
        "FROM mail_message mm "
        "JOIN res_partner rp ON rp.id = mm.author_id "
        "WHERE mm.model = 'sale.order' AND mm.res_id = 992 "
        "ORDER BY mm.date"
    )
    for row in rows:
        print(f"  {row}")


if __name__ == "__main__":
    main()
