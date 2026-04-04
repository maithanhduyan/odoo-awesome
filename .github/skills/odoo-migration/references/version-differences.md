# Odoo Version Field Differences (V15 → V19)

## Removed Fields

### uom.uom
- `category_id` — Removed in V19. Was used to group UoMs (Weight, Volume, Unit, etc.)
- `uom_type` — Removed in V19. Was `reference`, `bigger`, `smaller`
- `factor` / `factor_inv` — May behave differently, verify on target

### product.template
- `uom_po_id` — Removed in V19. Purchase UoM no longer separate field

## Changed Field Formats

### String → JSON Dict
In V19, translatable fields are stored as JSON dicts:

```python
# V15
product.name = "Gạo tấm"

# V19
product.name = {"en_US": "Gạo tấm", "vi_VN": "Gạo tấm"}

# When reading via XML-RPC with context={'lang': 'en_US'}, returns plain string
# When reading via SQL, returns JSON
```

### mail.message subtype_id
Subtype IDs differ between versions. Common subtypes:

| Subtype | V15 typical ID | V19 typical ID |
|---------|---------------|---------------|
| Discussions | 1 | 1 |
| Note | 2 | 2 |
| Activities | varies | varies |

Always look up by `xml_id` or `(name, res_model)` instead of hardcoding IDs.

### ir.model.fields IDs
Field IDs are completely different between V15 and V19. For mail.tracking.value migration:

```sql
-- Build mapping on both systems:
SELECT id, model, name FROM ir_model_fields
WHERE model IN ('sale.order', 'purchase.order', 'account.move', 'stock.picking', 'mrp.bom')
ORDER BY model, name;

-- Create dict: (model, field_name) → field_id for each system
-- Then map: v15_field_id → (model, name) → v19_field_id
```

## UoM Rounding Differences

| UoM | V15 rounding | V19 rounding |
|-----|-------------|-------------|
| Túi (Bag) | 1.0 | 0.01 |
| Hộp (Box) | 1.0 | 0.01 |
| Chai (Bottle) | 1.0 | 0.01 |
| Lon (Can) | 1.0 | 0.01 |
| Thùng (Carton) | 1.0 | 0.01 |
| Gói (Package) | 1.0 | 0.01 |
| Bịch (Pouch) | 1.0 | 0.01 |

## Decimal Precision

| Name | V15 digits | V19 digits |
|------|-----------|-----------|
| Product Unit of Measure | 4 | 2 (called "Product Unit") |

### Impact
- V15: 0.735 kg (3dp) → V19: 0.74 kg (2dp) = precision loss
- Solution: Convert to gram (735g) instead of changing decimal precision
- Or: UPDATE ir_decimal_precision SET digits=4 WHERE name='Product Unit'

## Model Rename/Restructure Notes

- `uom.uom` and `uom.category` exist in both versions but with different field sets
- `account.move` replaces `account.invoice` (already happened in V14)
- `stock.production.lot` → `stock.lot` (may vary by version)
- `mail.followers` → structure similar but verify field names
