"""Create 5 missing journals in V19 and update id_map."""
import json
import xmlrpc.client
from pathlib import Path

MAP_FILE = Path(__file__).parent / "migrate" / "id_map.json"

url = "http://localhost:19069"
db = "taya19_db"
pw = "TaYa@2022Pwd"
uid = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common").authenticate(
    db, "tayafood@gmail.com", pw, {}
)
models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")

with open(MAP_FILE) as f:
    idmap = json.load(f)

acc_map = idmap.get("account.account", {})
jrnl_map = idmap.get("account.journal", {})

journals = [
    {"v15_id": 9, "name": "Point of Sale", "code": "POSS", "type": "general", "v15_acc": None},
    {"v15_id": 10, "name": "0331000496415", "code": "BNK2", "type": "bank", "v15_acc": 198},
    {"v15_id": 11, "name": "0331000494299", "code": "BNK3", "type": "bank", "v15_acc": 199},
    {"v15_id": 12, "name": "28186668", "code": "BNK4", "type": "bank", "v15_acc": 200},
    {"v15_id": 13, "name": "86897699", "code": "BNK5", "type": "bank", "v15_acc": 201},
]

for j in journals:
    vals = {"name": j["name"], "code": j["code"], "type": j["type"]}
    if j["v15_acc"]:
        v19_acc = acc_map.get(str(j["v15_acc"]))
        if v19_acc:
            vals["default_account_id"] = v19_acc
    try:
        v19_id = models.execute_kw(db, uid, pw, "account.journal", "create", [vals])
        jrnl_map[str(j["v15_id"])] = v19_id
        print(f"Created: v15#{j['v15_id']} {j['code']} -> v19#{v19_id}")
    except Exception as e:
        print(f"Error: v15#{j['v15_id']} {j['code']}: {e}")

idmap["account.journal"] = jrnl_map
with open(MAP_FILE, "w") as f:
    json.dump(idmap, f, indent=2)
total = sum(len(v) for v in idmap.values())
print(f"Saved. Total mappings: {total}")
