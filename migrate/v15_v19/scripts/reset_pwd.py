"""Reset password for tayafood@gmail.com in taya19_db via JSON-RPC."""
import json
import urllib.request

URL = "http://localhost:8069"
DB = "taya19_db"
USER = "tayafood@gmail.com"
OLD_PWD = "admin"
NEW_PWD = "TaYa@2022Pwd"

def jsonrpc(service, method, args):
    payload = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "call",
        "params": {"service": service, "method": method, "args": args}
    }).encode()
    req = urllib.request.Request(
        f"{URL}/jsonrpc", data=payload,
        headers={"Content-Type": "application/json", "X-Odoo-Database": DB}
    )
    resp = urllib.request.urlopen(req, timeout=30)
    data = json.loads(resp.read().decode())
    if "error" in data:
        raise RuntimeError(data["error"])
    return data["result"]

# Login
uid = jsonrpc("common", "login", [DB, USER, OLD_PWD])
print(f"Logged in as uid={uid}")

# Change password
jsonrpc("object", "execute_kw",
    [DB, uid, OLD_PWD, "res.users", "write", [[uid], {"password": NEW_PWD}]])
print(f"Password changed to: {NEW_PWD}")

# Verify new password works
uid2 = jsonrpc("common", "login", [DB, USER, NEW_PWD])
print(f"Verify login with new password: uid={uid2}")
