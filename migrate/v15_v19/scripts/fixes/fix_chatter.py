"""
Migrate mail.message, mail.tracking.value, and mail.followers from V15 to V19.
"""
import sys, json, subprocess, html
sys.path.insert(0, '/home/odoo-migration')

from migrate.config import *
from migrate.migrator import OdooConnection

def run_sql_v19(sql):
    r = subprocess.run(
        ["docker","exec","postgres-18","psql","-U","odoo","-d","taya19_db","-c",sql],
        capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        print(f"SQL ERROR: {r.stderr[:500]}")
    return r.stdout

def run_sql_v19_csv(sql):
    r = subprocess.run(
        ["docker","exec","postgres-18","psql","-U","odoo","-d","taya19_db","-t","-A","-F,","-c",sql],
        capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        print(f"SQL ERROR: {r.stderr[:500]}")
        return []
    return [l for l in r.stdout.strip().split("\n") if l]

def sql_str(val):
    """Escape a string for SQL."""
    if val is None:
        return "NULL"
    s = str(val).replace("'", "''").replace("\\", "\\\\")
    return f"E'{s}'"

def sql_val(val):
    if val is None or val is False:
        return "NULL"
    return str(val)

# Connect
src = OdooConnection(V15_URL, V15_DB, V15_USER, V15_PASSWORD, 'v15')
dst = OdooConnection(V19_URL, V19_DB, V19_USER, V19_PASSWORD, 'v19')
src.connect(); dst.connect()

id_map = json.load(open('migrate/id_map.json'))
partner_map = {int(k): v for k, v in id_map.get('res.partner', {}).items()}
user_map = {int(k): v for k, v in id_map.get('res.users', {}).items()}

# Subtype mapping
v15_subs = src.search_read('mail.message.subtype', [], ['name'], limit=0)
v19_subs = dst.search_read('mail.message.subtype', [], ['name'], limit=0)
v19_sub_by_name = {}
for s in v19_subs:
    name = s['name']
    if isinstance(name, dict):
        name = name.get('en_US', str(name))
    v19_sub_by_name[name] = s['id']
subtype_map = {}
for s in v15_subs:
    v19_id = v19_sub_by_name.get(s['name'])
    if v19_id:
        subtype_map[s['id']] = v19_id

# Model mappings
MODELS = ['sale.order', 'purchase.order', 'account.move', 'account.payment',
          'stock.picking', 'mrp.production']
model_maps = {}
for model in MODELS:
    model_maps[model] = {int(k): v for k, v in id_map.get(model, {}).items()}

# ir.model.fields mapping (V15 field_id -> V19 field_id by model+name)
print("Building ir.model.fields mapping...")
v15_fields = {}
for row in subprocess.run(
    ["docker","exec","postgresql","psql","-U","odoo","-d","taya_db","-t","-A","-F,","-c",
     "SELECT id, model, name FROM ir_model_fields WHERE model IN ('sale.order','purchase.order','account.move','account.payment','stock.picking','mrp.production');"],
    capture_output=True, text=True).stdout.strip().split("\n"):
    if row and ',' in row:
        parts = row.split(',', 2)
        if len(parts) == 3:
            v15_fields[int(parts[0])] = (parts[1], parts[2])

v19_fields_by_key = {}
for row in subprocess.run(
    ["docker","exec","postgres-18","psql","-U","odoo","-d","taya19_db","-t","-A","-F,","-c",
     "SELECT id, model, name FROM ir_model_fields WHERE model IN ('sale.order','purchase.order','account.move','account.payment','stock.picking','mrp.production');"],
    capture_output=True, text=True).stdout.strip().split("\n"):
    if row and ',' in row:
        parts = row.split(',', 2)
        if len(parts) == 3:
            v19_fields_by_key[(parts[1], parts[2])] = int(parts[0])

field_map = {}
for v15_id, (model, name) in v15_fields.items():
    v19_id = v19_fields_by_key.get((model, name))
    if v19_id:
        field_map[v15_id] = v19_id

print(f"  Mapped {len(field_map)}/{len(v15_fields)} fields")

# ============================================================
# STEP 1: Migrate mail.message
# ============================================================
print("\n=== Migrating mail.message ===")
msg_id_map = {}  # v15_msg_id -> v19_msg_id

# Get next V19 mail_message id
next_id_row = run_sql_v19_csv("SELECT COALESCE(MAX(id),0)+1 FROM mail_message;")
next_msg_id = int(next_id_row[0]) if next_id_row else 100000

FIELDS = ['model', 'res_id', 'body', 'subject', 'date', 'message_type',
           'subtype_id', 'author_id', 'email_from', 'is_internal',
           'create_uid', 'create_date', 'write_uid', 'write_date']

total_ok = 0
total_skip = 0

for model in MODELS:
    mmap = model_maps[model]
    if not mmap:
        continue

    # Get all V15 messages for this model
    v15_msgs = src.search_read('mail.message',
        [['model', '=', model]],
        FIELDS, order='id asc', limit=0)

    batch_values = []
    for msg in v15_msgs:
        v15_res_id = msg.get('res_id', 0)
        v19_res_id = mmap.get(v15_res_id)
        if not v19_res_id:
            total_skip += 1
            continue

        v19_msg_id = next_msg_id
        next_msg_id += 1
        msg_id_map[msg['id']] = v19_msg_id

        # Map author_id
        v15_author = msg['author_id'][0] if msg['author_id'] else None
        v19_author = partner_map.get(v15_author, v15_author) if v15_author else None

        # Map subtype
        v15_sub = msg['subtype_id'][0] if msg['subtype_id'] else None
        v19_sub = subtype_map.get(v15_sub, 2) if v15_sub else None  # default to Note

        # Map create_uid, write_uid
        v15_cu = msg.get('create_uid')
        v15_cu = v15_cu[0] if v15_cu else 1
        v19_cu = user_map.get(v15_cu, v15_cu)

        v15_wu = msg.get('write_uid')
        v15_wu = v15_wu[0] if v15_wu else 1
        v19_wu = user_map.get(v15_wu, v15_wu)

        body = msg.get('body') or ''
        subject = msg.get('subject') or None
        date = msg.get('date') or None
        msg_type = msg.get('message_type', 'notification')
        email_from = msg.get('email_from') or None
        is_internal = 'true' if msg.get('is_internal') else 'false'
        create_date = msg.get('create_date') or date
        write_date = msg.get('write_date') or date

        vals = (
            f"({v19_msg_id}, {sql_str(model)}, {v19_res_id}, "
            f"{sql_str(body)}, {sql_str(subject)}, "
            f"{sql_str(date) if date else 'NULL'}::timestamp, "
            f"{sql_str(msg_type)}, {sql_val(v19_sub)}, {sql_val(v19_author)}, "
            f"{sql_str(email_from) if email_from else 'NULL'}, {is_internal}, "
            f"{v19_cu}, {sql_str(create_date) if create_date else 'NULL'}::timestamp, "
            f"{v19_wu}, {sql_str(write_date) if write_date else 'NULL'}::timestamp)"
        )
        batch_values.append(vals)

        if len(batch_values) >= 200:
            sql = (
                "INSERT INTO mail_message (id, model, res_id, body, subject, date, "
                "message_type, subtype_id, author_id, email_from, is_internal, "
                "create_uid, create_date, write_uid, write_date) VALUES\n"
                + ",\n".join(batch_values) + ";"
            )
            out = run_sql_v19(sql)
            if 'INSERT' in out:
                total_ok += len(batch_values)
            else:
                print(f"  ERROR inserting batch for {model}: {out[:200]}")
            batch_values = []

    # Flush remaining
    if batch_values:
        sql = (
            "INSERT INTO mail_message (id, model, res_id, body, subject, date, "
            "message_type, subtype_id, author_id, email_from, is_internal, "
            "create_uid, create_date, write_uid, write_date) VALUES\n"
            + ",\n".join(batch_values) + ";"
        )
        out = run_sql_v19(sql)
        if 'INSERT' in out:
            total_ok += len(batch_values)
        else:
            print(f"  ERROR inserting last batch for {model}: {out[:200]}")

    print(f"  {model}: {len(v15_msgs)} V15 messages processed")

print(f"\nMessages: inserted={total_ok}, skipped={total_skip}")
print(f"Message ID map: {len(msg_id_map)} entries")

# Update sequence
run_sql_v19(f"SELECT setval('mail_message_id_seq', {next_msg_id});")

# ============================================================
# STEP 2: Migrate mail.tracking.value
# ============================================================
print("\n=== Migrating mail.tracking.value ===")

# Get next V19 tracking value id
next_tv_id_row = run_sql_v19_csv("SELECT COALESCE(MAX(id),0)+1 FROM mail_tracking_value;")
next_tv_id = int(next_tv_id_row[0]) if next_tv_id_row else 100000

# Get V15 tracking values linked to mapped messages
v15_msg_ids = list(msg_id_map.keys())
tv_ok = 0

for i in range(0, len(v15_msg_ids), 500):
    batch_msg_ids = v15_msg_ids[i:i+500]

    # Read V15 tracking values via SQL (faster)
    ids_str = ','.join(str(x) for x in batch_msg_ids)
    v15_tvs = src.search_read('mail.tracking.value',
        [['mail_message_id', 'in', batch_msg_ids]],
        ['mail_message_id', 'field', 'field_desc', 'field_type',
         'old_value_integer', 'new_value_integer', 'old_value_float', 'new_value_float',
         'old_value_char', 'new_value_char', 'old_value_text', 'new_value_text',
         'old_value_datetime', 'new_value_datetime', 'currency_id',
         'create_uid', 'create_date', 'write_uid', 'write_date'],
        limit=0)

    batch_values = []
    for tv in v15_tvs:
        v15_msg_id = tv['mail_message_id'][0] if tv['mail_message_id'] else None
        if not v15_msg_id or v15_msg_id not in msg_id_map:
            continue

        v19_msg_id = msg_id_map[v15_msg_id]

        # Map field
        v15_field_id = tv['field'][0] if tv['field'] else None
        v19_field_id = field_map.get(v15_field_id) if v15_field_id else None
        if not v19_field_id:
            continue

        tv_id = next_tv_id
        next_tv_id += 1

        v15_cu = tv.get('create_uid')
        v15_cu = v15_cu[0] if v15_cu else 1
        v19_cu = user_map.get(v15_cu, v15_cu)
        v15_wu = tv.get('write_uid')
        v15_wu = v15_wu[0] if v15_wu else 1
        v19_wu = user_map.get(v15_wu, v15_wu)

        vals = (
            f"({tv_id}, {v19_field_id}, {v19_msg_id}, "
            f"{sql_val(tv.get('old_value_integer'))}, {sql_val(tv.get('new_value_integer'))}, "
            f"{sql_val(tv.get('old_value_float'))}, {sql_val(tv.get('new_value_float'))}, "
            f"{sql_str(tv.get('old_value_char'))}, {sql_str(tv.get('new_value_char'))}, "
            f"{sql_str(tv.get('old_value_text'))}, {sql_str(tv.get('new_value_text'))}, "
            f"{sql_str(tv.get('old_value_datetime')) + '::timestamp' if tv.get('old_value_datetime') else 'NULL'}, "
            f"{sql_str(tv.get('new_value_datetime')) + '::timestamp' if tv.get('new_value_datetime') else 'NULL'}, "
            f"{sql_val(tv.get('currency_id')[0] if tv.get('currency_id') else None)}, "
            f"{v19_cu}, {sql_str(tv.get('create_date')) + '::timestamp' if tv.get('create_date') else 'NULL'}, "
            f"{v19_wu}, {sql_str(tv.get('write_date')) + '::timestamp' if tv.get('write_date') else 'NULL'})"
        )
        batch_values.append(vals)

        if len(batch_values) >= 200:
            sql = (
                "INSERT INTO mail_tracking_value (id, field_id, mail_message_id, "
                "old_value_integer, new_value_integer, old_value_float, new_value_float, "
                "old_value_char, new_value_char, old_value_text, new_value_text, "
                "old_value_datetime, new_value_datetime, currency_id, "
                "create_uid, create_date, write_uid, write_date) VALUES\n"
                + ",\n".join(batch_values) + ";"
            )
            out = run_sql_v19(sql)
            if 'INSERT' in out:
                tv_ok += len(batch_values)
            else:
                print(f"  TV ERROR: {out[:300]}")
            batch_values = []

    if batch_values:
        sql = (
            "INSERT INTO mail_tracking_value (id, field_id, mail_message_id, "
            "old_value_integer, new_value_integer, old_value_float, new_value_float, "
            "old_value_char, new_value_char, old_value_text, new_value_text, "
            "old_value_datetime, new_value_datetime, currency_id, "
            "create_uid, create_date, write_uid, write_date) VALUES\n"
            + ",\n".join(batch_values) + ";"
        )
        out = run_sql_v19(sql)
        if 'INSERT' in out:
            tv_ok += len(batch_values)
        else:
            print(f"  TV ERROR: {out[:300]}")

run_sql_v19(f"SELECT setval('mail_tracking_value_id_seq', {next_tv_id});")
print(f"Tracking values inserted: {tv_ok}")

# ============================================================
# STEP 3: Migrate mail.followers
# ============================================================
print("\n=== Migrating mail.followers ===")

# Delete existing V19 followers for business models
for model in MODELS:
    run_sql_v19(f"DELETE FROM mail_followers WHERE res_model = '{model}';")

next_fol_id_row = run_sql_v19_csv("SELECT COALESCE(MAX(id),0)+1 FROM mail_followers;")
next_fol_id = int(next_fol_id_row[0]) if next_fol_id_row else 100000

fol_ok = 0
for model in MODELS:
    mmap = model_maps[model]
    if not mmap:
        continue

    v15_fols = src.search_read('mail.followers',
        [['res_model', '=', model]],
        ['res_id', 'partner_id'],
        limit=0)

    batch_values = []
    seen = set()  # avoid duplicates
    for fol in v15_fols:
        v15_res_id = fol['res_id']
        v19_res_id = mmap.get(v15_res_id)
        if not v19_res_id:
            continue

        v15_partner = fol['partner_id'][0] if fol['partner_id'] else None
        if not v15_partner:
            continue
        v19_partner = partner_map.get(v15_partner, v15_partner)

        key = (model, v19_res_id, v19_partner)
        if key in seen:
            continue
        seen.add(key)

        fol_id = next_fol_id
        next_fol_id += 1

        batch_values.append(f"({fol_id}, {sql_str(model)}, {v19_res_id}, {v19_partner})")

        if len(batch_values) >= 500:
            sql = (
                "INSERT INTO mail_followers (id, res_model, res_id, partner_id) VALUES\n"
                + ",\n".join(batch_values) + " ON CONFLICT DO NOTHING;"
            )
            out = run_sql_v19(sql)
            if 'INSERT' in out:
                fol_ok += len(batch_values)
            batch_values = []

    if batch_values:
        sql = (
            "INSERT INTO mail_followers (id, res_model, res_id, partner_id) VALUES\n"
            + ",\n".join(batch_values) + " ON CONFLICT DO NOTHING;"
        )
        out = run_sql_v19(sql)
        if 'INSERT' in out:
            fol_ok += len(batch_values)

    print(f"  {model}: {len(v15_fols)} V15 followers")

run_sql_v19(f"SELECT setval('mail_followers_id_seq', {next_fol_id});")
print(f"Followers inserted: {fol_ok}")

print("\n=== DONE ===")
