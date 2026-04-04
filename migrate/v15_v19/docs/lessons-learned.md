# Lessons Learned: Odoo v15 → v19 Migration

## Kinh nghiệm tích lũy từ migration production TAYA Việt Nam

50 models, 77,284 records, 14 post-migration fixes. Đây là những bài học quan trọng nhất.

---

## 1. ORM là con dao hai lưỡi

### Ưu điểm
- Validation tự động: constraints, required fields, compute dependencies
- Version-agnostic: không phụ thuộc schema
- Idempotent: id_map tracking, chạy lại an toàn

### Nhược điểm phát hiện

| ORM behavior | Hậu quả | Giải pháp |
|---|---|---|
| Auto-generate sequence cho `name` | Invoice numbers bị mất | Direct SQL update |
| Auto-apply default tax | 794 SO/PO + 793 AML lines sai tax | Remove tax + restore amounts |
| Auto-create chatter messages | 19,633 messages sai author/date | SQL update author_id + date |
| Set create_uid = current user | 67,227 records mất audit trail | SQL restore từ V15 |
| Auto-create partner khi tạo user | Phải map ngược partner ID | Đọc lại sau create, update data |
| Stricter VAT validation | 4 partners reject | Create without VAT, SQL bypass |

**Kết luận**: Dùng ORM cho migration (integrity), nhưng luôn cần SQL fix scripts cho phần ORM tự ý thay đổi.

---

## 2. Default Tax là bẫy lớn nhất

**Ảnh hưởng**: Đây là vấn đề tốn công nhất — cần 4 fix scripts riêng biệt.

**Cơ chế**: Odoo v19 auto-apply tax mặc định (10% GTGT) lên mọi line KHÔNG có tax assignment. V15 cho phép lines không có tax, v19 tự gán.

**Chuỗi hậu quả**:
```
Auto-tax on SO/PO lines → fix_taxes.py (794 lines)
    ↓
Auto-tax on AML lines → fix_invoice_taxes.py (793 AML + restore amounts)
    ↓ (side effect: overwrite amount_residual)
Reconciliation state lost → fix_reconciliation.py (4,081 AML + 2,063 AM)
    ↓ (222 invoices have extra unmapped AML lines)
222 invoices still wrong → fix_unmapped_invoices.py (222 inv + 200 APR/AFR)
```

**Phòng ngừa**: Trước khi migration, disable default tax trên v19:
```python
# Disable auto-apply tax
tax_ids = env['account.tax'].search([('type_tax_use', '!=', False)])
tax_ids.write({'active': False})
# ... migrate ...
# Re-enable after
tax_ids.write({'active': True})
```

Hoặc tốt hơn: sau migration, so sánh tax totals giữa V15/V19 per invoice TRƯỚC khi chạy bất kỳ fix nào khác.

---

## 3. Fix scripts có side effects — thứ tự rất quan trọng

**Bài học đắt giá**: `fix_invoice_taxes.py` restore V15 debit/credit/balance trên AML lines → vô tình ghi đè `amount_residual` và phá vỡ reconciliation state → cần `fix_reconciliation.py` để khôi phục.

**Nguyên tắc**:
1. **Fix amounts trước reconciliation**: Thuế → totals → residuals → reconciliation → payment_state
2. **Đừng bao giờ UPDATE column mà không hiểu side effects**: `amount_residual` ảnh hưởng `reconciled`, `payment_state`, outstanding credits display
3. **Luôn verify sau mỗi fix**: So sánh V15 vs V19 ngay sau mỗi script, không đợi chạy hết

---

## 4. Schema changes v15 → v19 cần biết

### Fields removed/renamed

| v15 | v19 | Ảnh hưởng |
|-----|-----|-----------|
| `account_account.code` | `account_account.code_store` (jsonb: `{"1": "1311"}`) | SQL queries phải sửa |
| `account_full_reconcile.name` | Removed | Không dùng name cho matching |
| `account_full_reconcile.exchange_move_id` | Removed | — |
| `account_partial_reconcile` | Thêm `exchange_move_id`, `draft_caba_move_vals` | Columns mới, nullable |
| `res.partner.type = 'private'` | Removed | Transform → `contact` |
| `product.template.type = 'product'` | `type = 'consu'` + `is_storable = True` | Product type restructured |
| `ir_translation` table | Removed → inline jsonb | Translations inline |
| `ir_property` table | Removed → `properties` jsonb | Property fields inline |
| `account_account.internal_type` | `account_account.account_type` | Values khác: `receivable` → `asset_receivable`, `payable` → `liability_payable` |

### Timezone change
- Python 3.9 (v15): `pytz` → chấp nhận `Asia/Saigon`
- Python 3.12 (v19): `zoneinfo` → chỉ chấp nhận `Asia/Ho_Chi_Minh`

---

## 5. Batch SQL > Individual SQL

**Bài học từ fix_reconciliation.py Step 6**:

```python
# ❌ SLOW: 2,039 individual SQL calls → timeout sau 300s
for v15_fr_id, v19_amls in fr_to_v19_amls.items():
    sql_exec(f"UPDATE ... WHERE id IN ({ids})")

# ✅ FAST: Batched CASE WHEN, 200 records/batch → vài giây
for i in range(0, len(pairs), 200):
    batch = pairs[i:i+200]
    cases = " ".join(f"WHEN {aid} THEN {fid}" for aid, fid in batch)
    ids = ",".join(str(aid) for aid, _ in batch)
    sql_exec(f"UPDATE account_move_line SET full_reconcile_id = "
             f"CASE id {cases} ELSE full_reconcile_id END "
             f"WHERE id IN ({ids})")
```

**Nguyên tắc**: Mỗi SQL call qua `docker exec` tốn ~50-100ms overhead (process spawn + network). 2,039 calls × 100ms = 200+ giây. Batch 200/call → chỉ ~10 calls × 100ms = 1 giây.

---

## 6. Reconciliation là phần phức tạp nhất

### Cấu trúc reconciliation trong Odoo

```
account_move (Invoice)
  └── account_move_line (Receivable: debit=5,002,500)
        ├── amount_residual = 0 (fully paid)
        ├── reconciled = true
        └── full_reconcile_id = 761
              ↓
account_partial_reconcile
  ├── debit_move_id = invoice_recv_aml
  ├── credit_move_id = payment_credit_aml
  ├── amount = 5,002,500
  └── full_reconcile_id = 761
              ↓
account_full_reconcile (id=761)
              ↓
account_move_line (Payment credit: credit=5,002,500)
  ├── amount_residual = 0
  ├── reconciled = true
  └── full_reconcile_id = 761
```

### 5 fields phải đồng bộ

| Field | Table | Ý nghĩa |
|-------|-------|---------|
| `amount_residual` | account_move_line | Số tiền còn nợ = balance - SUM(partial_reconcile.amount) |
| `reconciled` | account_move_line | `true` khi amount_residual = 0 VÀ tham gia reconcile |
| `full_reconcile_id` | account_move_line | Link đến full reconcile record |
| `full_reconcile_id` | account_partial_reconcile | Link partial → full |
| `payment_state` | account_move | `paid` / `not_paid` / `partial` — tính từ AML residuals |

Nếu BẤT KỲ field nào sai → invoice hiển thị "Dư có chưa phân bổ" (outstanding credits), payment state sai, báo cáo tài chính sai.

### Bài học
- Đừng update `debit`/`credit`/`balance` trên AML sau khi reconciliation đã tồn tại
- Nếu phải update amounts → PHẢI recalculate toàn bộ reconciliation chain
- 200 unmapped AMLs = 200 invoices cần tạo mới APR/AFR records bằng SQL

---

## 7. ID mapping là nền tảng — thiếu mapping = thiếu data

**Vấn đề**: 222 invoices có receivable/payable AML line KHÔNG trong id_map.

**Nguyên nhân**: Khi V19 ORM tạo invoice, auto-tax thêm extra AML lines (tax line). V19 receivable line có amount khác V15 → migration không match được → không map được ID.

**Hậu quả**:
- Reconciliation script không tìm được V19 recv AML → không thể tạo APR
- payment_state vẫn `not_paid`

**Giải pháp**: `fix_unmapped_invoices.py` tìm V19 receivable bằng `move_id` + `account_type`, fix amount về V15, rồi tạo APR/AFR mới.

**Phòng ngừa**: Sau migration, ngay lập tức kiểm tra:
```sql
-- V15 paid invoices whose AML is not in id_map
SELECT COUNT(*) FROM account_move
WHERE payment_state = 'paid'
AND move_type IN ('out_invoice','out_refund','in_invoice','in_refund')
-- Check if receivable AML is mapped
```

---

## 8. Docker exec overhead

Mỗi `docker exec postgres psql -U odoo -d db -c "..."` tốn:
- Process spawn: ~30ms
- Network: ~20ms
- Query execution: variable

Cho 100 queries = ~5 giây overhead. Cho 10,000 queries = ~8 phút overhead.

**Tối ưu**:
1. Batch queries: Gom nhiều records vào 1 query (CASE WHEN, VALUES list)
2. Single connection: Nếu nhiều queries → dùng `psycopg2` connect trực tiếp thay vì `docker exec`
3. Bulk operations: `COPY` command cho insert lớn

---

## 9. Kiểm tra Settings/Features sau migration

**Phát hiện**: Sau migration, module "Đơn vị tính & bao bì" (UoM) không được enable trong Settings → sản phẩm không hiển thị UoM field.

**Thêm vào đó**: 2 users (Nijimise uid=38, OdooBot copy uid=44) có conflict giữa Portal group + User group → không lưa được Settings.

**Giải pháp**:
1. Enable features thủ công trong Settings > Tồn kho > Sản phẩm
2. Fix user group conflicts: remove Role/User group (gid=1), keep Portal (gid=10)

**Checklist sau migration**:
- [ ] Settings > General: Company info correct
- [ ] Settings > Tồn kho: UoM enabled, tracking settings
- [ ] Settings > Kế toán: Tax settings, payment terms
- [ ] Settings > Users: Check for group conflicts
- [ ] Sản phẩm > Form: UoM field visible
- [ ] Hóa đơn > Form: No "Dư có chưa phân bổ" warnings
- [ ] Thanh toán > List: Payment states correct

---

## 10. So sánh V15 vs V19 là indispensable

Script `compare_migration.py` (9 sections) là công cụ quan trọng nhất. Chạy SAU MỖI fix script để detect regression.

**Sections cần compare**:
1. Record counts per model
2. Partner name/email match
3. Product name/price match
4. SO/PO header totals (amount_total, amount_tax)
5. SO/PO line amounts
6. Invoice amounts by type (4 types)
7. Payment totals
8. Stock move quantities
9. **Accounting balances** (receivable/payable — CRITICAL)

**Nguyên tắc vàng**: Nếu V15 total ≠ V19 total → STOP. Tìm root cause trước khi chạy tiếp.

---

## Tổng kết

| Bài học | Áp dụng cho |
|---------|-------------|
| Disable default tax trước migration | Mọi Odoo migration |
| Fix scripts phải có thứ tự | Mọi post-migration workflow |
| Batch SQL thay vì loop | Mọi bulk data operation |
| Compare V15 vs V19 liên tục | Mọi data migration |
| Check Settings/Features sau migration | Mọi Odoo upgrade |
| ID map = single source of truth | Mọi migration with cross-references |
| ORM cho create, SQL cho fix | Hybrid approach works best |
| Reconciliation = 5 fields phải sync | Odoo accounting migration |
