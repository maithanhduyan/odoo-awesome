"""Fix bank_id on partner banks and state_id on partners.

1. Create missing banks in V19 from V15, map by name
2. Update bank_id on all res.partner.bank records in V19
3. Map Vietnamese states by name between V15 and V19
4. Update state_id on all res.partner records in V19

Then regenerate CSV reports.
"""

import json
import sys
import xmlrpc.client
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from migrate.config import (
    V15_URL, V15_DB, V15_USER, V15_PASSWORD,
    V19_URL, V19_DB, V19_USER, V19_PASSWORD,
)

MAP_FILE = Path(__file__).parent / "migrate" / "id_map.json"


def connect(url, db, user, pwd, label):
    common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
    uid = common.authenticate(db, user, pwd, {})
    models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
    print(f"[{label}] Connected uid={uid}")
    return uid, models, db, pwd


def rpc(models, uid, db, pwd, model, method, *args, **kwargs):
    return models.execute_kw(db, uid, pwd, model, method, list(args), kwargs)


def main():
    uid15, m15, db15, pwd15 = connect(V15_URL, V15_DB, V15_USER, V15_PASSWORD, "v15")
    uid19, m19, db19, pwd19 = connect(V19_URL, V19_DB, V19_USER, V19_PASSWORD, "v19")

    id_map = json.loads(MAP_FILE.read_text(encoding="utf-8"))

    # ── Part 1: Fix bank_id ──────────────────────────────────────────

    print("\n=== Part 1: Fix bank_id ===")

    # Read all V15 banks
    v15_banks = rpc(m15, uid15, db15, pwd15, "res.bank", "search_read",
                    [], fields=["id", "name", "bic"], order="id asc")
    print(f"V15 banks: {len(v15_banks)}")

    # Read all V19 banks
    v19_banks = rpc(m19, uid19, db19, pwd19, "res.bank", "search_read",
                    [], fields=["id", "name", "bic"], order="id asc")
    v19_bank_by_name = {b["name"]: b["id"] for b in v19_banks}
    print(f"V19 banks: {len(v19_banks)}")

    # Create missing banks in V19 and build mapping
    bank_map = id_map.get("res.bank", {})
    created_banks = 0

    for b in v15_banks:
        v15_id = b["id"]
        if str(v15_id) in bank_map:
            continue  # Already mapped

        # Check if name already exists in V19
        if b["name"] in v19_bank_by_name:
            v19_id = v19_bank_by_name[b["name"]]
        else:
            # Create in V19
            vals = {"name": b["name"]}
            if b.get("bic"):
                vals["bic"] = b["bic"]
            v19_id = rpc(m19, uid19, db19, pwd19, "res.bank", "create", vals)
            v19_bank_by_name[b["name"]] = v19_id
            created_banks += 1

        bank_map[str(v15_id)] = v19_id
        print(f"  Bank mapped: v15#{v15_id} -> v19#{v19_id} ({b['name']})")

    id_map["res.bank"] = bank_map
    print(f"  Created {created_banks} new banks in V19")

    # Now update bank_id on all partner bank accounts
    # Read V15 partner banks to get their bank_id
    v15_pbanks = rpc(m15, uid15, db15, pwd15, "res.partner.bank", "search_read",
                     [], fields=["id", "bank_id"], order="id asc")

    pbank_map = id_map.get("res.partner.bank", {})
    updated_banks = 0
    errors_banks = 0

    for pb in v15_pbanks:
        v15_id = pb["id"]
        v19_pbank_id = pbank_map.get(str(v15_id))
        if not v19_pbank_id:
            continue  # Not migrated

        v15_bank_id = pb["bank_id"][0] if pb.get("bank_id") else None
        if not v15_bank_id:
            continue

        v19_bank_id = bank_map.get(str(v15_bank_id))
        if not v19_bank_id:
            print(f"  WARNING: No bank mapping for v15 bank #{v15_bank_id}")
            continue

        try:
            rpc(m19, uid19, db19, pwd19, "res.partner.bank", "write",
                [v19_pbank_id], {"bank_id": v19_bank_id})
            updated_banks += 1
        except Exception as e:
            print(f"  ERROR updating bank_id on v19 partner.bank #{v19_pbank_id}: {e}")
            errors_banks += 1

    print(f"  Updated bank_id on {updated_banks} partner banks ({errors_banks} errors)")

    # ── Part 2: Fix state_id ─────────────────────────────────────────

    print("\n=== Part 2: Fix state_id ===")

    # Get Vietnam country id in both systems
    v15_vn = rpc(m15, uid15, db15, pwd15, "res.country", "search_read",
                 [("code", "=", "VN")], fields=["id"])
    v19_vn = rpc(m19, uid19, db19, pwd19, "res.country", "search_read",
                 [("code", "=", "VN")], fields=["id"])
    v15_vn_id = v15_vn[0]["id"]
    v19_vn_id = v19_vn[0]["id"]

    # Read all VN states from both
    v15_states = rpc(m15, uid15, db15, pwd15, "res.country.state", "search_read",
                     [("country_id", "=", v15_vn_id)], fields=["id", "name", "code"])
    v19_states = rpc(m19, uid19, db19, pwd19, "res.country.state", "search_read",
                     [("country_id", "=", v19_vn_id)], fields=["id", "name", "code"])

    print(f"V15 VN states: {len(v15_states)}, V19 VN states: {len(v19_states)}")

    # Build V19 lookup by name
    v19_state_by_name = {s["name"]: s["id"] for s in v19_states}
    # Also by code for fallback
    v19_state_by_code = {s["code"]: s["id"] for s in v19_states if s.get("code")}

    state_map = id_map.get("res.country.state", {})
    new_state_maps = 0
    created_states = 0
    unmapped_states = []

    for s in v15_states:
        v15_id = s["id"]
        if str(v15_id) in state_map:
            continue  # Already mapped via xmlid

        # Try name match
        v19_id = v19_state_by_name.get(s["name"])

        # Try code match
        if not v19_id and s.get("code"):
            v19_id = v19_state_by_code.get(s["code"])

        if v19_id:
            state_map[str(v15_id)] = v19_id
            new_state_maps += 1
            print(f"  State mapped by name: v15#{v15_id} -> v19#{v19_id} ({s['name']})")
        else:
            # Create in V19
            vals = {
                "name": s["name"],
                "code": s.get("code", s["name"][:3].upper()),
                "country_id": v19_vn_id,
            }
            try:
                v19_id = rpc(m19, uid19, db19, pwd19, "res.country.state", "create", vals)
                state_map[str(v15_id)] = v19_id
                v19_state_by_name[s["name"]] = v19_id
                created_states += 1
                print(f"  State created: v15#{v15_id} -> v19#{v19_id} ({s['name']})")
            except Exception as e:
                print(f"  ERROR creating state {s['name']}: {e}")
                unmapped_states.append(s)

    id_map["res.country.state"] = state_map
    print(f"  Mapped by name: {new_state_maps}, Created: {created_states}")
    if unmapped_states:
        print(f"  Still unmapped: {[s['name'] for s in unmapped_states]}")

    # Now update state_id on partners that are missing it
    # Find partners that had state_id in V15 but are missing in V19
    v15_partners_with_state = rpc(
        m15, uid15, db15, pwd15, "res.partner", "search_read",
        [("state_id", "!=", False)],
        fields=["id", "state_id"],
    )
    print(f"\n  V15 partners with state_id: {len(v15_partners_with_state)}")

    partner_map = id_map.get("res.partner", {})
    updated_states = 0
    errors_states = 0

    for p in v15_partners_with_state:
        v15_id = p["id"]
        v19_partner_id = partner_map.get(str(v15_id))
        if not v19_partner_id:
            continue

        v15_state_id = p["state_id"][0] if isinstance(p["state_id"], (list, tuple)) else p["state_id"]
        v19_state_id = state_map.get(str(v15_state_id))
        if not v19_state_id:
            continue

        # Check if V19 partner already has state_id
        v19_partner = rpc(m19, uid19, db19, pwd19, "res.partner", "read",
                          [v19_partner_id], fields=["state_id"])
        if v19_partner and v19_partner[0].get("state_id"):
            continue  # Already has state

        try:
            rpc(m19, uid19, db19, pwd19, "res.partner", "write",
                [v19_partner_id], {"state_id": v19_state_id})
            updated_states += 1
        except Exception as e:
            print(f"  ERROR updating state_id on v19 partner #{v19_partner_id}: {e}")
            errors_states += 1

    print(f"  Updated state_id on {updated_states} partners ({errors_states} errors)")

    # ── Save ─────────────────────────────────────────────────────────

    MAP_FILE.write_text(json.dumps(id_map, indent=2, ensure_ascii=False), encoding="utf-8")
    total = sum(len(v) for v in id_map.values())
    print(f"\nID map saved: {len(id_map)} models, {total} mappings")
    print("Done! Run 'python generate_csv_reports.py' to update CSVs.")


if __name__ == "__main__":
    main()
