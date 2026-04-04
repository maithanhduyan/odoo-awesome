---
name: odoo-migration
description: 'Migrate data between Odoo versions (v15→v19+). Use for planning migration phases, writing migration scripts, fixing data quality issues (audit fields, chatter, UoM, invoices), direct SQL bypass for ORM constraints, XML-RPC batch operations, and resolving version-specific field/API differences.'
argument-hint: 'Describe the migration task: source version, target version, and what data to migrate'
---

# Odoo Version Migration

Comprehensive knowledge for migrating Odoo data between major versions using XML-RPC and direct SQL.

## When to Use

- Planning or executing data migration between Odoo versions
- Writing migration scripts for specific models
- Fixing post-migration data quality issues
- Resolving Odoo version API/field differences
- Migrating chatter (messages, tracking values, followers)
- Converting UoM or fixing decimal precision across versions
- Syncing audit fields (create_uid, write_uid, create_date, write_date)

## Architecture

### Dual-Strategy Approach

1. **XML-RPC** (primary): For standard CRUD via Odoo ORM — respects constraints, triggers workflows
2. **Direct SQL** (bypass): For bulk fixes, audit fields, chatter — bypasses ORM constraints that block legitimate data sync

### Infrastructure Pattern

```
Source Odoo (container) ←→ Migration Scripts (host) ←→ Target Odoo (container)
       ↓                                                      ↓
Source PostgreSQL (container)                    Target PostgreSQL (container)
```

- Services run in separate Docker Compose files, connected via shared Docker network
- Use **container names** (not service names) for inter-service communication
- Migration scripts run on host, connecting via XML-RPC (HTTP) and `docker exec` (SQL)

## Migration Pipeline

### Phase Order (22 phases)

Execute in dependency order — parent models before children:

| Phase | Model | Dependencies |
|-------|-------|-------------|
| 1 | res.partner | None |
| 2 | res.users | res.partner |
| 3 | product.category | None |
| 4 | uom.uom | None |
| 5 | product.template | product.category, uom.uom |
| 6 | product.product | product.template |
| 7 | stock.warehouse | None |
| 8 | stock.location | stock.warehouse |
| 9 | account.account | None |
| 10 | account.journal | account.account |
| 11 | account.tax | None |
| 12 | sale.order | res.partner, res.users |
| 13 | sale.order.line | sale.order, product.product |
| 14 | purchase.order | res.partner |
| 15 | purchase.order.line | purchase.order, product.product |
| 16 | account.move | res.partner, account.journal |
| 17 | account.move.line | account.move, product.product, account.account |
| 18 | stock.picking | stock.location, res.partner |
| 19 | stock.move.line, stock.quant | stock.picking, product.product (use pagination!) |
| 20 | mrp.bom | product.template |
| 21 | mrp.bom.line | mrp.bom, product.product |
| 22 | mail.message | All above models |

### Core Engine Components

```python
# config.py — connection settings
V15_URL = "http://<container-or-ip>:8069"
V19_URL = "http://<container-or-ip>:8069"

# migrator.py — OdooConnection, IDMap, Migrator classes
# - OdooConnection: XML-RPC wrapper with search_read, create, write
# - IDMap: Persistent JSON mapping (v15_id → v19_id) per model
# - Migrator: Orchestrates read→transform→write with field mapping
```

### ID Mapping Strategy

- Maintain persistent `id_map.json` with structure: `{model: {v15_id: v19_id}}`
- Always look up mapped IDs for relational fields (Many2one, Many2many)
- For unmapped references, log warnings but continue (don't abort batch)

## Critical Version Differences (V15 → V19)

### Removed Fields

| Model | Field | V15 | V19 |
|-------|-------|-----|-----|
| uom.uom | category_id | Present | **Removed** |
| uom.uom | uom_type | Present | **Removed** |
| product.template | uom_po_id | Present | **Removed** |

### Changed Field Types

| Model | Field | V15 | V19 |
|-------|-------|-----|-----|
| product.template | name | `str` | `dict` (JSON: `{"en_US": "..."}`) |
| res.partner | name | `str` | May be `dict` |

### API Changes

- V19 `search_read` may return different default fields
- V19 has stricter unique constraints on some models
- V19 `mail.message` subtype IDs differ from V15
- Always read target fields first: `fields_get()` to discover available fields

## Post-Migration Fixes

### 1. Audit Fields (create_uid, write_uid, create_date, write_date)

**Problem**: ORM always sets write_uid=current_user, ignoring provided values.

**Solution**: Direct SQL UPDATE after migration.

```python
# CRITICAL: Use user_map.get(uid, uid) — NOT user_map.get(uid, 2)
# Preserving original uid when no mapping exists is safer than defaulting to admin
mapped_uid = user_map.get(original_uid, original_uid)
```

```sql
-- Example: sync audit fields for account.move
UPDATE account_move SET
  create_uid = v.create_uid,
  write_uid = v.write_uid,
  create_date = v.create_date,
  write_date = v.write_date
FROM (VALUES
  (v19_id, mapped_create_uid, mapped_write_uid, 'create_date'::timestamp, 'write_date'::timestamp),
  ...
) AS v(id, create_uid, write_uid, create_date, write_date)
WHERE account_move.id = v.id;
```

**Target models**: res.partner, product.template, product.product, sale.order, purchase.order, account.move, stock.picking, mrp.bom, mrp.bom.line

### 2. Chatter Migration (mail.message, mail.tracking.value, mail.followers)

**Problem**: V19 auto-generates messages during migration (wrong author=Administrator, wrong dates).

**Solution** (3-step):

1. **Delete auto-generated V19 messages**:
```sql
DELETE FROM mail_tracking_value WHERE mail_message_id IN (
  SELECT id FROM mail_message WHERE model IN ('sale.order','purchase.order',...) AND res_id > 0
);
DELETE FROM mail_message WHERE model IN (...) AND res_id > 0;
```

2. **Migrate messages via SQL INSERT** (not XML-RPC — ORM blocks author/date override):
```sql
INSERT INTO mail_message (message_type, subtype_id, model, res_id, body, author_id, date, ...)
VALUES ('comment', mapped_subtype_id, 'sale.order', v19_res_id, body, mapped_author_id, original_date, ...);
```

3. **Migrate tracking values** with field_id mapping (v15 field IDs ≠ v19 field IDs):
```sql
-- Map field_id: lookup ir.model.fields by (model, name) on both systems
-- v15: SELECT id, model, name FROM ir_model_fields WHERE model = '...'
-- v19: SELECT id, model, name FROM ir_model_fields WHERE model = '...'
-- Then map: v15_field_id → (model, name) → v19_field_id
```

4. **Migrate followers** with partner_id mapping.

### 3. UoM and Decimal Precision

**Problem**: V15 may use kg with 3+ decimal places (e.g., 0.735 kg). V19 with 2dp rounding loses precision.

**Strategy**: Convert to smaller unit (kg → gram) instead of changing decimal precision config.

```python
# For BOM lines: multiply qty by 1000, change uom_id from kg to gram
# V19 UoM IDs: kg=16, g=15 (verify with: SELECT id, name FROM uom_uom)
```

**UoM rounding differences**: Check `SELECT id, name, rounding FROM uom_uom` on both systems.

### 4. Invoice Names

**Problem**: Some invoices may lose their `name` field during migration.

**Solution**: Match by V15→V19 ID mapping and UPDATE:
```sql
UPDATE account_move SET name = 'INV/2024/00001', state = 'posted'
WHERE id = v19_id AND (name IS NULL OR name = '/');
```

### 5. Salesperson (invoice_user_id, user_id)

**Problem**: Salesperson fields may not map correctly.

**Solution**: SQL UPDATE with user_map values via VALUES+JOIN pattern.

## Large Dataset Handling

For models with >10,000 records (stock.move.line, stock.quant):

```python
BATCH_SIZE = 2000
offset = 0
while True:
    records = source.search_read(model, domain, fields, limit=BATCH_SIZE, offset=offset)
    if not records:
        break
    # process batch
    offset += BATCH_SIZE
```

## Verification Procedures

After each fix, verify with comparison queries:

```python
# Pattern: fetch from both systems, compare field by field
v15_records = v15_conn.search_read(model, [], fields)
v19_records = v19_conn.search_read(model, [], fields)

for v15_rec in v15_records:
    v19_id = id_map.get(model, {}).get(str(v15_rec['id']))
    v19_rec = v19_map.get(v19_id)
    if v15_rec[field] != v19_rec[field]:
        errors.append(...)

print(f"Errors: {len(errors)}")  # Target: 0
```

## Common Pitfalls

1. **Don't use `depends_on`** for cross-compose dependencies — services in different docker-compose files
2. **Container names** for DB connections — not `localhost` from within containers
3. **ORM bypasses audit fields** — always use direct SQL for create_uid/write_uid/create_date/write_date
4. **V19 auto-generates chatter** — delete auto-generated messages before migrating real ones
5. **user_map default** — use `user_map.get(uid, uid)` not `user_map.get(uid, 2)` (don't default to admin)
6. **Pagination required** for stock.move.line, stock.quant — will crash without batching
7. **Backup before every bulk fix** — `pg_dump` the target database before SQL updates
8. **Test with single record first** — verify mapping on one record before running bulk operations

## Reference Files

- [Version field differences](./references/version-differences.md)
- [User ID mapping table](./references/user-mapping.md)
