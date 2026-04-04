"""
Fix missing invoice numbers (name) in V19.
During migration, the `name` field was not copied from V15 to V19.
This script reads V15 names and batch-updates V19 via SQL.
"""
import json
import subprocess
import sys
from pathlib import Path

MAP_FILE = Path(__file__).parent / "migrate" / "id_map.json"


def run_sql(db: str, sql: str) -> list[str]:
    """Run SQL via docker exec and return output lines."""
    cmd = ["docker", "exec", "postgres", "psql", "-U", "odoo", "-d", db, "-t", "-A", "-c", sql]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"SQL ERROR: {r.stderr.strip()}")
        return []
    return [line for line in r.stdout.strip().split("\n") if line.strip()]


def main():
    # Load id_map
    with open(MAP_FILE) as f:
        id_map = json.load(f)

    am_map = id_map.get("account.move", {})
    if not am_map:
        print("ERROR: No account.move mappings found in id_map.json")
        sys.exit(1)

    print(f"account.move mappings: {len(am_map)}")

    # Read V15 invoice names
    v15_rows = run_sql("taya_db",
        "SELECT id, name FROM account_move "
        "WHERE move_type IN ('out_invoice','out_refund','in_invoice','in_refund') "
        "AND name IS NOT NULL AND name != '/' "
        "ORDER BY id"
    )

    v15_names = {}
    for row in v15_rows:
        parts = row.split("|", 1)
        if len(parts) == 2:
            v15_id = parts[0].strip()
            name = parts[1].strip()
            v15_names[v15_id] = name

    print(f"V15 invoices with names: {len(v15_names)}")

    # Build update list: (v19_id, name)
    updates = []
    skipped = 0
    for v15_id_str, name in v15_names.items():
        v19_id = am_map.get(v15_id_str)
        if v19_id:
            updates.append((v19_id, name))
        else:
            skipped += 1

    print(f"Updates to apply: {len(updates)}, skipped (unmapped): {skipped}")

    if not updates:
        print("Nothing to update.")
        return

    # Batch UPDATE using CASE statements (200 per batch)
    BATCH = 200
    total_updated = 0

    for i in range(0, len(updates), BATCH):
        batch = updates[i:i + BATCH]
        cases = []
        ids = []
        for v19_id, name in batch:
            safe_name = name.replace("'", "''")
            cases.append(f"WHEN {v19_id} THEN '{safe_name}'")
            ids.append(str(v19_id))

        sql = (
            f"UPDATE account_move SET name = CASE id "
            f"{' '.join(cases)} END "
            f"WHERE id IN ({','.join(ids)})"
        )

        result = run_sql("taya19_db", sql)
        total_updated += len(batch)
        print(f"  Batch {i // BATCH + 1}: updated {len(batch)} records (total: {total_updated})")

    # Verify
    print("\n--- Verification ---")
    verify = run_sql("taya19_db",
        "SELECT move_type, COUNT(*), "
        "COUNT(CASE WHEN name IS NOT NULL AND name != '' AND name != '/' THEN 1 END) as with_name "
        "FROM account_move "
        "WHERE move_type IN ('out_invoice','out_refund','in_invoice','in_refund') "
        "GROUP BY move_type ORDER BY move_type"
    )
    for row in verify:
        print(f"  {row}")

    # Show samples
    print("\n--- Sample invoice numbers ---")
    samples = run_sql("taya19_db",
        "SELECT id, name, move_type FROM account_move "
        "WHERE move_type IN ('out_invoice','in_invoice') "
        "AND name IS NOT NULL AND name != '' "
        "ORDER BY id LIMIT 10"
    )
    for row in samples:
        print(f"  {row}")

    print(f"\nDone! Updated {total_updated} invoice names.")


if __name__ == "__main__":
    main()
