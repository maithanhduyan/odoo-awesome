import json
import urllib.request

def jsonrpc(method, service, args):
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "call",
        "params": {"service": service, "method": method, "args": args}}).encode()
    req = urllib.request.Request("http://localhost:8069/jsonrpc", data=payload,
        headers={"Content-Type": "application/json", "X-Odoo-Database": "taya19_db"})
    resp = urllib.request.urlopen(req, timeout=30)
    return json.loads(resp.read().decode())["result"]

for pwd in ["admin", "TaYa@2022Pwd", "odoo"]:
    uid = jsonrpc("login", "common", ["taya19_db", "tayafood@gmail.com", pwd])
    print(f"tayafood@gmail.com / {pwd} => uid={uid}")
