"""Fix 4 partners that failed due to VAT validation.
Creates them without VAT, then prints SQL to set VAT directly."""

import json
import sys
import xmlrpc.client
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from migrate.config import (
    V15_URL, V15_DB, V15_USER, V15_PASSWORD,
    V19_URL, V19_DB, V19_USER, V19_PASSWORD,
)

# Connect V15
common15 = xmlrpc.client.ServerProxy(f"{V15_URL}/xmlrpc/2/common")
uid15 = common15.authenticate(V15_DB, V15_USER, V15_PASSWORD, {})
m15 = xmlrpc.client.ServerProxy(f"{V15_URL}/xmlrpc/2/object")

# Connect V19
common19 = xmlrpc.client.ServerProxy(f"{V19_URL}/xmlrpc/2/common")
uid19 = common19.authenticate(V19_DB, V19_USER, V19_PASSWORD, {})
m19 = xmlrpc.client.ServerProxy(f"{V19_URL}/xmlrpc/2/object")

print(f"[v15] uid={uid15}, [v19] uid={uid19}")


def v15_read(model, domain, fields):
    return m15.execute_kw(V15_DB, uid15, V15_PASSWORD, model, "search_read",
                          [domain], {"fields": fields, "order": "id asc"})


def v19_create(model, vals):
    return m19.execute_kw(V19_DB, uid19, V19_PASSWORD, model, "create", [vals])


# Load id_map
map_file = Path(__file__).parent / "migrate" / "id_map.json"
id_map = json.loads(map_file.read_text(encoding="utf-8"))

FIELDS = [
    "name", "city", "color", "comment", "company_name", "email",
    "employee", "function", "lang", "partner_latitude", "partner_longitude",
    "phone", "ref", "street", "street2", "type", "tz", "vat",
    "website", "zip", "active", "is_company", "image_1920",
    "country_id", "state_id", "parent_id", "company_id", "industry_id",
]

M2O_MODELS = {
    "country_id": "res.country",
    "state_id": "res.country.state",
    "parent_id": "res.partner",
    "company_id": "res.company",
    "industry_id": "res.partner.industry",
}

TZ_MAP = {"Asia/Saigon": "Asia/Ho_Chi_Minh"}
TYPE_MAP = {"private": "contact"}

FAILED_IDS = [55, 56, 163, 168]

# Read from V15
records = v15_read("res.partner", [("id", "in", FAILED_IDS)], ["id"] + FIELDS)
print(f"Read {len(records)} records from V15")

created = []
for rec in records:
    v15_id = rec["id"]
    vals = {}
    for field in FIELDS:
        value = rec[field]
        if field == "vat":
            continue  # Skip VAT — will set via SQL
        if field == "tz" and value:
            value = TZ_MAP.get(value, value)
        if field == "type" and value:
            value = TYPE_MAP.get(value, value)
        if field in M2O_MODELS and value:
            old_id = value[0] if isinstance(value, (list, tuple)) else value
            related_model = M2O_MODELS[field]
            new_id = id_map.get(related_model, {}).get(str(old_id))
            if new_id is None:
                print(f"  #{v15_id}: no mapping for {field}.{related_model}={old_id}, skip field")
                continue
            vals[field] = new_id
        elif isinstance(value, (list, tuple)) and len(value) == 2 and isinstance(value[0], int):
            vals[field] = value[0]
        else:
            if value is not False or field == "active":
                vals[field] = value

    try:
        v19_id = v19_create("res.partner", vals)
        id_map.setdefault("res.partner", {})[str(v15_id)] = v19_id
        created.append((v15_id, v19_id, rec["name"], rec["vat"]))
        print(f"  Created: v15#{v15_id} -> v19#{v19_id} ({rec['name']})")
    except Exception as e:
        print(f"  FAILED v15#{v15_id}: {e}")

# Save id_map
map_file.write_text(json.dumps(id_map, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\nID map saved. Created {len(created)}/{len(FAILED_IDS)} partners.")

# Generate and print SQL
if created:
    print("\n--- SQL to set VAT (run via psql) ---")
    sql_parts = []
    for v15_id, v19_id, name, vat in created:
        if vat:
            # Sanitize: only allow alphanumeric, dash, space
            safe_vat = "".join(c for c in vat if c.isalnum() or c in "- ")
            sql_parts.append(f"UPDATE res_partner SET vat='{safe_vat}' WHERE id={v19_id};")
            print(f"  {sql_parts[-1]}  -- {name}")

    # Execute SQL via docker
    if sql_parts:
        sql_cmd = " ".join(sql_parts)
        print(f"\nFull SQL:\n{sql_cmd}")
