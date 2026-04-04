"""Fix account_move.invoice_user_id to match V15 salesperson."""
import json
import subprocess
from pathlib import Path

MAP_FILE = Path(__file__).parent / "migrate" / "id_map.json"

with open(MAP_FILE) as f:
    id_map = json.load(f)

am_map = id_map.get("account.move", {})

USER_MAP = {1:1, 2:2, 3:3, 4:3, 5:4, 7:36, 8:37, 10:38, 17:39, 20:40, 21:41, 22:42, 23:43, 25:44, 26:45, 38:46}

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
    return r.returncode == 0

# Get ALL V15 invoice_user_id
rows = run_sql("taya_db", "SELECT id, invoice_user_id FROM account_move WHERE invoice_user_id IS NOT NULL")
v15_data = {}
for row in rows:
    parts = row.split("|")
    if len(parts) >= 2:
        v15_data[parts[0]] = int(parts[1])

# Build updates
updates = []
for v15_id_str, v15_uid in v15_data.items():
    v19_id = am_map.get(v15_id_str)
    if v19_id:
        v19_uid = USER_MAP.get(v15_uid, 2)
        updates.append((v19_id, v19_uid))

print(f"Total updates: {len(updates)}")

BATCH = 200
total = 0
for i in range(0, len(updates), BATCH):
    batch = updates[i:i + BATCH]
    cases = " ".join(f"WHEN {vid} THEN {uid}" for vid, uid in batch)
    ids = ",".join(str(vid) for vid, _ in batch)
    sql = f"UPDATE account_move SET invoice_user_id = CASE id {cases} ELSE invoice_user_id END WHERE id IN ({ids})"
    if run_sql_exec("taya19_db", sql):
        total += len(batch)

print(f"Updated: {total}")

# Verify
print("\n--- Verification: customer invoices salesperson ---")
for row in run_sql("taya19_db",
    "SELECT rp.name, COUNT(*) FROM account_move am "
    "LEFT JOIN res_users ru ON ru.id = am.invoice_user_id "
    "LEFT JOIN res_partner rp ON rp.id = ru.partner_id "
    "WHERE am.move_type IN ('out_invoice','out_refund') "
    "GROUP BY rp.name ORDER BY COUNT(*) DESC"):
    print(f"  {row}")

print("\n--- Verification: vendor bills salesperson ---")
for row in run_sql("taya19_db",
    "SELECT rp.name, COUNT(*) FROM account_move am "
    "LEFT JOIN res_users ru ON ru.id = am.invoice_user_id "
    "LEFT JOIN res_partner rp ON rp.id = ru.partner_id "
    "WHERE am.move_type IN ('in_invoice','in_refund') "
    "GROUP BY rp.name ORDER BY COUNT(*) DESC"):
    print(f"  {row}")
