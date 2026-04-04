"""
Fix remaining 200 invoice names that failed due to unique constraint.
Handles conflicts by appending -R suffix for refunds or -2 for duplicates.
"""
import json
import subprocess
from pathlib import Path

MAP_FILE = Path(__file__).parent / "migrate" / "id_map.json"


def run_sql(db, sql):
    cmd = ["docker", "exec", "postgres", "psql", "-U", "odoo", "-d", db, "-t", "-A", "-c", sql]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        return None, r.stderr.strip()
    return [l for l in r.stdout.strip().split("\n") if l.strip()], None


def main():
    with open(MAP_FILE) as f:
        id_map = json.load(f)

    am_map = id_map["account.move"]
    rev_map = {str(v): k for k, v in am_map.items()}

    # Get V19 IDs still missing names
    rows, _ = run_sql("taya19_db",
        "SELECT id, move_type, journal_id FROM account_move "
        "WHERE move_type IN ('out_invoice','out_refund','in_invoice','in_refund') "
        "AND (name IS NULL OR name = '' OR name = '/') ORDER BY id"
    )

    missing = []
    for row in rows:
        parts = row.split("|")
        missing.append({"v19_id": int(parts[0]), "move_type": parts[1], "journal_id": int(parts[2])})

    print(f"Missing names: {len(missing)}")

    # Get V15 names for these
    updates = []
    for rec in missing:
        v15_id = rev_map.get(str(rec["v19_id"]))
        if not v15_id:
            print(f"  WARNING: No reverse mapping for V19 {rec['v19_id']}")
            continue
        v15_rows, _ = run_sql("taya_db", f"SELECT name FROM account_move WHERE id = {v15_id}")
        if v15_rows:
            rec["v15_name"] = v15_rows[0]
            rec["v15_id"] = v15_id
            updates.append(rec)

    print(f"Updates to process: {len(updates)}")

    # Process one by one, handling conflicts
    success = 0
    conflicts = 0
    for rec in updates:
        name = rec["v15_name"]
        safe_name = name.replace("'", "''")
        v19_id = rec["v19_id"]
        journal_id = rec["journal_id"]

        # Check if name+journal_id already exists
        existing, _ = run_sql("taya19_db",
            f"SELECT id FROM account_move WHERE name = '{safe_name}' AND journal_id = {journal_id}"
        )

        if existing:
            # Conflict - add suffix based on move_type
            if rec["move_type"] in ("out_refund", "in_refund"):
                name = f"{name}-R"
            else:
                suffix = 2
                while True:
                    test_name = f"{name}-{suffix}"
                    test_safe = test_name.replace("'", "''")
                    ex2, _ = run_sql("taya19_db",
                        f"SELECT id FROM account_move WHERE name = '{test_safe}' AND journal_id = {journal_id}"
                    )
                    if not ex2:
                        name = test_name
                        break
                    suffix += 1
            conflicts += 1
            print(f"  Conflict: V15={rec['v15_id']} '{rec['v15_name']}' -> '{name}'")

        safe_name = name.replace("'", "''")
        _, err = run_sql("taya19_db",
            f"UPDATE account_move SET name = '{safe_name}' WHERE id = {v19_id}"
        )
        if err:
            print(f"  ERROR updating V19 {v19_id}: {err}")
        else:
            success += 1

    print(f"\nDone! Success: {success}, Conflicts resolved: {conflicts}")

    # Final verify
    rows, _ = run_sql("taya19_db",
        "SELECT move_type, COUNT(*), "
        "COUNT(CASE WHEN name IS NOT NULL AND name != '' THEN 1 END) as with_name "
        "FROM account_move "
        "WHERE move_type IN ('out_invoice','out_refund','in_invoice','in_refund') "
        "GROUP BY move_type ORDER BY move_type"
    )
    print("\n--- Final Verification ---")
    for row in rows:
        print(f"  {row}")


if __name__ == "__main__":
    main()
