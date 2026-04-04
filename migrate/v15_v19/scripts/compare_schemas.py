"""Compare Odoo 15 vs 19 database schemas in detail."""
import psycopg2

conn15 = psycopg2.connect(dbname='odoo', user='odoo', password='odoo', host='localhost')
conn19 = psycopg2.connect(dbname='odoo19', user='odoo', password='odoo', host='localhost')

def get_schema(conn):
    cur = conn.cursor()
    cur.execute("""
        SELECT table_name, column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema='public'
        ORDER BY table_name, ordinal_position
    """)
    schema = {}
    for tbl, col, dtype, nullable in cur.fetchall():
        schema.setdefault(tbl, {})[col] = (dtype, nullable)
    return schema

v15 = get_schema(conn15)
v19 = get_schema(conn19)

only_v15 = sorted(set(v15) - set(v19))
only_v19 = sorted(set(v19) - set(v15))
common = sorted(set(v15) & set(v19))

print(f"=== SUMMARY: v15={len(v15)} tables, v19={len(v19)} tables, common={len(common)} ===\n")

print(f"--- Only in v15 ({len(only_v15)}) ---")
for t in only_v15:
    print(f"  {t} ({len(v15[t])} cols)")

print(f"\n--- Only in v19 ({len(only_v19)}) ---")
for t in only_v19:
    print(f"  {t} ({len(v19[t])} cols)")

print(f"\n--- Column diffs in {len(common)} shared tables ---")
total_added = total_removed = total_changed = 0
for t in common:
    added = sorted(set(v19[t]) - set(v15[t]))
    removed = sorted(set(v15[t]) - set(v19[t]))
    changed = sorted(c for c in set(v15[t]) & set(v19[t]) if v15[t][c][0] != v19[t][c][0])
    total_added += len(added)
    total_removed += len(removed)
    total_changed += len(changed)
    if added or removed or changed:
        print(f"\n  [{t}]")
        for c in removed:
            print(f"    - {c} ({v15[t][c][0]})")
        for c in added:
            print(f"    + {c} ({v19[t][c][0]})")
        for c in changed:
            print(f"    ~ {c}: {v15[t][c][0]} -> {v19[t][c][0]}")

print(f"\n=== TOTALS: +{total_added} cols, -{total_removed} cols, ~{total_changed} type changes ===")

# Check critical ORM metadata
print("\n--- ir_module_module state comparison ---")
cur15 = conn15.cursor()
cur15.execute("SELECT state, count(*) FROM ir_module_module GROUP BY state ORDER BY state")
print("  v15:", dict(cur15.fetchall()))
cur19 = conn19.cursor()
cur19.execute("SELECT state, count(*) FROM ir_module_module GROUP BY state ORDER BY state")
print("  v19:", dict(cur19.fetchall()))

# Check sequences
print("\n--- Key sequence values ---")
for db, conn, label in [('odoo', conn15, 'v15'), ('odoo19', conn19, 'v19')]:
    cur = conn.cursor()
    cur.execute("SELECT sequencename, last_value FROM pg_sequences WHERE schemaname='public' AND sequencename LIKE 'res_partner%' OR sequencename LIKE 'res_users%' OR sequencename LIKE 'ir_module%' ORDER BY sequencename")
    print(f"  {label}:", {r[0]: r[1] for r in cur.fetchall()})

conn15.close()
conn19.close()
