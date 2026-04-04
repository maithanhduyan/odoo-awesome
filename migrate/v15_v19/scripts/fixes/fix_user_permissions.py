"""
Migrate user permissions (group memberships) from Odoo 15 to Odoo 19.
Maps groups by xml_id, handles renamed/moved groups between versions.
"""
import subprocess
import sys


def run_sql(db, sql):
    cmd = ["docker", "exec", "postgres", "psql", "-U", "odoo", "-d", db, "-t", "-A", "-c", sql]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"SQL ERROR: {r.stderr.strip()}")
        return []
    return [l for l in r.stdout.strip().split("\n") if l.strip()]


# Groups renamed/moved between V15 and V19
XMLID_REMAP = {
    "sale.group_delivery_invoice_address": "account.group_delivery_invoice_address",
    "product.group_discount_per_so_line": "sale.group_discount_per_so_line",
}

# Groups removed in V19 (no equivalent) - skip these
SKIP_XMLIDS = {
    "account.group_show_line_subtotals_tax_included",
    "base.group_private_addresses",
    "hr_attendance.group_hr_attendance",
    "hr_attendance.group_hr_attendance_kiosk",
    "hr_attendance.group_hr_attendance_use_pin",
    "hr_contract.group_hr_contract_manager",
    "product.group_stock_packaging",
    "website.group_website_publisher",
}


def main():
    # Step 1: Get V19 xml_id -> group_id mapping
    rows = run_sql("taya19_db",
        "SELECT imd.module || '.' || imd.name, g.id "
        "FROM ir_model_data imd "
        "JOIN res_groups g ON g.id = imd.res_id "
        "WHERE imd.model = 'res.groups'"
    )
    v19_xmlid_to_gid = {}
    for row in rows:
        parts = row.split("|", 1)
        v19_xmlid_to_gid[parts[0]] = int(parts[1])
    print(f"V19 groups: {len(v19_xmlid_to_gid)}")

    # Step 2: Get V19 user login -> uid mapping
    rows = run_sql("taya19_db",
        "SELECT id, login FROM res_users WHERE active = true AND id > 1"
    )
    v19_login_to_uid = {}
    for row in rows:
        parts = row.split("|", 1)
        v19_login_to_uid[parts[1]] = int(parts[0])
    print(f"V19 users: {len(v19_login_to_uid)}")

    # Step 3: Get V15 user-group mappings (login, xml_id)
    rows = run_sql("taya_db",
        "SELECT u.login, imd.module || '.' || imd.name "
        "FROM res_users u "
        "JOIN res_groups_users_rel rel ON rel.uid = u.id "
        "JOIN res_groups g ON g.id = rel.gid "
        "JOIN ir_model_data imd ON imd.model = 'res.groups' AND imd.res_id = g.id "
        "WHERE u.active = true AND u.id > 1 "
        "ORDER BY u.login, imd.module || '.' || imd.name"
    )

    # Parse into dict: login -> set of xml_ids
    v15_user_groups = {}
    for row in rows:
        parts = row.split("|", 1)
        login, xmlid = parts[0], parts[1]
        v15_user_groups.setdefault(login, set()).add(xmlid)
    print(f"V15 users with groups: {len(v15_user_groups)}")

    # Step 4: Get existing V19 user-group memberships to avoid duplicates
    rows = run_sql("taya19_db",
        "SELECT uid, gid FROM res_groups_users_rel"
    )
    existing = set()
    for row in rows:
        parts = row.split("|")
        existing.add((int(parts[0]), int(parts[1])))
    print(f"V19 existing memberships: {len(existing)}")

    # Step 5: Build INSERT list
    inserts = []  # (uid, gid)
    skipped_no_user = 0
    skipped_no_group = 0
    skipped_existing = 0
    skipped_removed = 0
    remapped = 0

    for login, xmlids in v15_user_groups.items():
        # Skip admin - already has full permissions
        if login == "tayafood@gmail.com":
            continue

        v19_uid = v19_login_to_uid.get(login)
        if not v19_uid:
            skipped_no_user += 1
            continue

        for xmlid in xmlids:
            # Skip removed groups
            if xmlid in SKIP_XMLIDS:
                skipped_removed += 1
                continue

            # Remap if needed
            target_xmlid = XMLID_REMAP.get(xmlid, xmlid)
            if target_xmlid != xmlid:
                remapped += 1

            v19_gid = v19_xmlid_to_gid.get(target_xmlid)
            if not v19_gid:
                skipped_no_group += 1
                if xmlid not in SKIP_XMLIDS:
                    print(f"  WARNING: No V19 group for {xmlid} (user: {login})")
                continue

            if (v19_uid, v19_gid) in existing:
                skipped_existing += 1
                continue

            inserts.append((v19_uid, v19_gid))
            existing.add((v19_uid, v19_gid))  # prevent duplicates in same run

    print(f"\nTo insert: {len(inserts)}")
    print(f"Skipped: no_user={skipped_no_user}, no_group={skipped_no_group}, "
          f"existing={skipped_existing}, removed={skipped_removed}, remapped={remapped}")

    if not inserts:
        print("Nothing to insert.")
        return

    # Step 6: Batch INSERT
    BATCH = 500
    total = 0
    for i in range(0, len(inserts), BATCH):
        batch = inserts[i:i + BATCH]
        values = ", ".join(f"({uid}, {gid})" for uid, gid in batch)
        sql = f"INSERT INTO res_groups_users_rel (uid, gid) VALUES {values} ON CONFLICT DO NOTHING"
        run_sql("taya19_db", sql)
        total += len(batch)
        print(f"  Batch {i // BATCH + 1}: inserted {len(batch)} (total: {total})")

    # Step 7: Verify
    print("\n--- Verification ---")
    for login in sorted(v15_user_groups.keys()):
        if login == "tayafood@gmail.com":
            continue
        v19_uid = v19_login_to_uid.get(login)
        if not v19_uid:
            continue

        v15_count = len(v15_user_groups[login])
        rows = run_sql("taya19_db",
            f"SELECT COUNT(*) FROM res_groups_users_rel WHERE uid = {v19_uid}"
        )
        v19_count = int(rows[0]) if rows else 0
        print(f"  {login}: V15={v15_count} groups, V19={v19_count} groups")

    print(f"\nDone! Inserted {total} group memberships.")


if __name__ == "__main__":
    main()
