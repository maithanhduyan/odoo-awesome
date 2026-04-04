# User ID Mapping (V15 → V19)

## Mapping Table

Build this mapping early — it's needed for audit fields, chatter authors, and salesperson fields.

| V15 user ID | V19 user ID | Notes |
|-------------|-------------|-------|
| 2 | 2 | Admin (usually same) |
| 7 | 36 | |
| 8 | 37 | |
| 10 | 38 | |
| 17 | 39 | |
| 20 | 40 | |
| 21 | 41 | |
| 22 | 42 | |
| 23 | 43 | |
| 25 | 44 | |
| 26 | 45 | |
| 38 | 46 | |

## How to Build User Map

```python
# 1. Migrate res.users first (Phase 2)
# 2. Extract mapping from id_map.json
import json
with open('id_map.json') as f:
    id_map = json.load(f)

user_map = {int(k): v for k, v in id_map.get('res.users', {}).items()}
```

## Usage Pattern

```python
# For audit fields — CRITICAL: default to original uid, not admin(2)
mapped_uid = user_map.get(original_uid, original_uid)

# For partner_id mapping (chatter followers, message authors)
partner_map = {int(k): v for k, v in id_map.get('res.partner', {}).items()}
mapped_partner = partner_map.get(v15_partner_id, v15_partner_id)
```

## Common Mistakes

1. **`user_map.get(uid, 2)`** — Wrong! Defaults unmapped users to admin, corrupts audit trail
2. **`user_map.get(uid, uid)`** — Correct! Preserves original uid when no mapping exists
3. **Forgetting OdooBot** — uid=1 is OdooBot in V19, don't map real users to it
