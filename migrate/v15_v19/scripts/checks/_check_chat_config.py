"""Check ai_chat.config on production for API key / security settings."""
import psycopg2

DB_URL = "postgresql://odoo:lYxWmr4RwXUUReMtNr12IXvgvsqvOShs@interchange.proxy.rlwy.net:10858/taya19_db"

conn = psycopg2.connect(DB_URL)
cur = conn.cursor()

# Check what ai_chat tables exist
cur.execute("""
    SELECT tablename FROM pg_tables
    WHERE schemaname = 'public' AND tablename LIKE 'ai_chat%%'
    ORDER BY tablename
""")
tables = [r[0] for r in cur.fetchall()]
print("ai_chat tables:", tables)

# Check if module is installed
cur.execute("""
    SELECT name, state, latest_version
    FROM ir_module_module
    WHERE name = 'ai_chat'
""")
mod = cur.fetchone()
if mod:
    print(f"Module: name={mod[0]}, state={mod[1]}, version={mod[2]}")
else:
    print("Module ai_chat NOT found in ir_module_module")

# If ai_chat_config exists, show security columns
if 'ai_chat_config' in tables:
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'ai_chat_config' ORDER BY ordinal_position")
    cols = [r[0] for r in cur.fetchall()]
    print("Config columns:", cols)

    cur.execute("SELECT * FROM ai_chat_config WHERE active = true LIMIT 1")
    colnames = [d[0] for d in cur.description]
    row = cur.fetchone()
    if row:
        print("\n--- Active config ---")
        for n, v in zip(colnames, row):
            if any(k in n for k in ['key', 'origin', 'rate', 'secret', 'api', 'allow']):
                print(f"  {n}: {v!r}")
    else:
        print("No active config found!")

conn.close()
