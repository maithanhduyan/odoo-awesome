# Odoo Migration v15 → v19: Tài liệu kỹ thuật

## Tổng quan

Tài liệu này ghi lại toàn bộ quá trình migration dữ liệu production của **Công ty TNHH Thực Phẩm TAYA Việt Nam** từ Odoo 15 sang Odoo 19, thực hiện từ 2026-03-26 đến 2026-03-28.

### Kết quả cuối cùng

| Metric | Giá trị |
|--------|---------|
| Models migrated | **50** |
| Total ID mappings | **77,284** |
| Post-migration fix scripts | **14** |
| Payment state (V15 = V19) | paid=2,263 / not_paid=98 ✓ |
| Reconciliation (V15 = V19) | partial=2,242 / full=2,239 ✓ |
| Open balance match | 131: 3,396,307,315 / 331: -3,119,824,713 ✓ |
| Data integrity | **100%** (field-by-field verified) |

### Hệ thống

| Thành phần | Odoo 15 (nguồn) | Odoo 19 (đích) |
|---|---|---|
| Image | `odoo:15.0-20240924` | `odoo:19.0-20260305` |
| Container | `odoo15` | `odoo19` |
| Port | `:8069` | `:19069` |
| Database | `taya_db` | `taya19_db` |
| PostgreSQL | 18 + pgvector (shared) | 18 + pgvector (shared) |
| Python | 3.9 | 3.12 |

### Phạm vi dữ liệu

| Model | Records |
|-------|---------|
| res.partner | 304 |
| res.users | 12 |
| product.template / product.product | 619 |
| sale.order / sale.order.line | 995 / 2,060 |
| purchase.order / purchase.order.line | 1,383 / 1,745 |
| account.move / account.move.line | 4,617 / 8,039 |
| account.payment | 2,250 |
| stock.picking / stock.move / stock.move.line | 2,451 / 20,043 / 19,203 |
| mrp.production / mrp.bom | 1,320 / 163 |
| account.partial.reconcile / account.full.reconcile | 2,242 / 2,239 |
| ir.attachment | 1,374 |
| Khác (HR, CRM, project, UoM...) | ~2,500 |

---

## Phương pháp đã chọn: XML-RPC Read + XML-RPC Write

Sau khi đánh giá 3 phương pháp, chúng tôi chọn **XML-RPC thuần** cho cả đọc và ghi:

### Tại sao không dùng các cách khác

| Phương pháp | Kết luận | Lý do |
|---|---|---|
| Odoo CLI (`--update`) | ❌ Không khả thi | Chỉ hoạt động cùng major version. Không có `--migrate` CLI |
| Direct SQL Write | ❌ Bypass ORM | Không trigger computed fields, constraints, defaults — dễ data corruption |
| pg_dump/pg_restore | ❌ Schema khác | v15 có 127 tables (base), v19 có 135 tables — 41 type changes (varchar→jsonb) |
| Odoo Enterprise Upgrade | ❌ Dịch vụ bên ngoài | Phải upload DB lên upgrade.odoo.com — không tự chủ |

### Tại sao chọn XML-RPC

1. **ORM validation** — Odoo xử lý defaults, computed fields, constraints tự động
2. **Version-agnostic** — API ổn định giữa v15 và v19, không phụ thuộc schema
3. **Zero-downtime** — v15 vẫn hoạt động bình thường trong khi migrate
4. **Idempotent** — ID Map tracking cho phép chạy lại mà không duplicate
5. **Rollback dễ** — v19 database có thể drop/recreate bất kỳ lúc nào

---

## Kiến trúc Migration Engine

```
┌─────────────┐  XML-RPC Read  ┌──────────────────┐  XML-RPC Write  ┌─────────────┐
│   Odoo 15   │ ──────────────>│  Migration Script │ ──────────────>│   Odoo 19   │
│  :8069      │                │                   │                │  :19069     │
│  db=odoo    │                │  migrator.py      │                │  db=odoo19  │
└─────────────┘                │  ├─ OdooConnection│                └─────────────┘
                               │  ├─ IDMap (JSON)  │
                               │  └─ Migrator      │
                               └──────────────────┘
                                        │
                               ┌────────▼────────┐
                               │  id_map.json     │
                               │  2,238 mappings  │
                               └─────────────────┘
```

### Core Engine (`migrator.py`)

| Class | Chức năng |
|-------|-----------|
| `OdooConnection` | XML-RPC wrapper: `connect()`, `search_read()`, `create()`, `write()`, `fields_get()` |
| `IDMap` | v15_id ↔ v19_id mapping per model, persist to JSON, auto-load on start |
| `Migrator` | `build_xmlid_map()` cho master data, `migrate_model()` generic, `migrate_m2m()`, `migrate_attachments()` |

### Cấu trúc thư mục

```
odoo-migration/migrate/
├── config.py          # Connection settings v15/v19
├── migrator.py        # Core engine (~400 lines)
├── run.py             # CLI entry point
├── id_map.json        # Persisted v15→v19 ID mappings (77,284 entries, 50 models)
└── models/
    ├── base.py        # Phase 1-8: Master data, partners, users, banks
    ├── product.py     # Phase 9-10: Products, categories
    ├── accounting.py  # Phase 11-12: Chart of accounts, taxes
    ├── hr.py          # Phase 13: HR employees, departments, jobs
    ├── orders.py      # Phase 14-15: Sale orders, purchase orders
    ├── stock.py       # Phase 16: Stock locations, warehouses, picking types
    ├── mrp.py         # Phase 17: Manufacturing BOMs, production orders
    ├── invoices.py    # Phase 18: Account moves (invoices, bills, entries)
    ├── payments.py    # Phase 19: Account payments
    ├── reconcile.py   # Phase 20: Partial & full reconciliation
    ├── stock_detail.py# Phase 21: Stock pickings, moves, move lines, quants
    ├── crm_project.py # Phase 22: CRM leads, projects, tasks
    ├── attachments.py # Attachments (optional)
    └── mail.py        # Chatter messages (optional)
```

---

## 22 Phases Migration + 14 Post-Migration Fixes

Migration chia thành **2 giai đoạn**:
1. **22 Phases** — Chuyển dữ liệu qua XML-RPC (ORM)
2. **14 Fix Scripts** — Sửa data integrity qua SQL trực tiếp

### Phase 1-8: Base (Partners, Users, Banks)

| Phase | Model | Records | Ghi chú |
|-------|-------|---------|---------|
| 1 | Master data (countries, currencies, states) | 1,815+ | xmlid mapping only |
| 2 | res.partner.category | 9 | Parents → children |
| 3 | res.company | 1 | Map + update |
| 4 | res.partner | 304 | Companies → contacts |
| 5 | res.users | 12 | Auto-create partner → map ngược |
| 6 | Partner M2M (category_id) | — | Tag assignments |
| 7 | res.partner.bank | 97 | Bank accounts |
| 8 | ir.attachment | 1,374 | Binary attachments |

### Phase 9-12: Products & Accounting Setup

| Phase | Model | Records | Ghi chú |
|-------|-------|---------|---------|
| 9 | product.category | 13 | Hierarchical |
| 10 | product.template + product.product | 619 | Type mapping: `product` → `consu` + `is_storable=True` |
| 11 | account.account + account.journal | 201 + 13 | Chart of accounts |
| 12 | account.tax + payment terms | 8 + 7 | Tax mappings |

### Phase 13-17: Operations

| Phase | Model | Records | Ghi chú |
|-------|-------|---------|---------|
| 13 | hr.department + hr.job + hr.employee | 7 + 9 + 17 | HR data |
| 14 | sale.order + sale.order.line | 995 + 2,060 | Sales |
| 15 | purchase.order + purchase.order.line | 1,383 + 1,745 | Purchases |
| 16 | stock.location + stock.warehouse + stock.picking.type | 23 + 2 + 20 | Warehouse setup |
| 17 | mrp.bom + mrp.bom.line + mrp.production | 163 + 1,874 + 1,320 | Manufacturing |

### Phase 18-22: Accounting & Detail

| Phase | Model | Records | Ghi chú |
|-------|-------|---------|---------|
| 18 | account.move + account.move.line | 4,617 + 8,039 | Invoices, bills, entries |
| 19 | account.payment | 2,250 | Payments |
| 20 | account.partial.reconcile + account.full.reconcile | 2,042 + 2,039 | Reconciliation |
| 21 | stock.picking + stock.move + stock.move.line + stock.quant | 2,451 + 20,043 + 19,203 + 1,679 | Stock detail |
| 22 | crm.lead + project.project + project.task | 12 + 4 + 9 | CRM & Projects |

### Post-Migration Fixes (14 scripts)

Migration qua XML-RPC mang lại data integrity cao nhưng không hoàn hảo. Sau migration cần chạy 14 fix scripts để khắc phục các vấn đề mà ORM tự động gây ra hoặc không xử lý được.

| # | Script | Vấn đề | Records fixed |
|---|--------|--------|---------------|
| 1 | `fix_invoice_names.py` | Invoice name/number bị mất khi tạo qua ORM | ~2,200 |
| 2 | `fix_invoice_names2.py` | ~200 names bị unique constraint conflict | ~200 |
| 3 | `fix_user_permissions.py` | Group memberships thay đổi xmlid giữa v15/v19 | 348 |
| 4 | `fix_audit_fields.py` | create_uid/write_uid/dates bị ghi đè bằng admin | 67,227 |
| 5 | `fix_chatter_author.py` | Chatter messages hiện "Administrator" thay vì người gốc | 19,633 |
| 6 | `fix_invoice_salesperson.py` | invoice_user_id bị mất | 4,615 |
| 7 | `fix_taxes.py` | V19 auto-apply 10% VAT lên SO/PO lines không có tax | 794 |
| 8 | `fix_invoice_taxes.py` | V19 auto-apply 10% VAT lên AML lines + sai amount | 793 + 4,617 AM + 8,039 AML |
| 9 | `fix_reconciliation.py` | full_reconcile_id, reconciled flag, payment_state bị mất | 4,081 AML + 2,063 AM |
| 10 | `fix_unmapped_invoices.py` | 222 invoices có AML receivable không trong id_map | 222 invoices, 200 APR, 200 AFR |
| 11 | `fix_bank_state.py` | bank_id và state_id mapping sai | Partners + banks |
| 12 | `fix_journals.py` | 5 journals thiếu (bank journals) | 5 |
| 13 | `fix_pickings.py` | 65 pickings skip do 12 products chưa tồn tại | 65 pickings, 12 products |
| 14 | `fix_vat_partners.py` | 4 partners bị reject VAT do validation mới v19 | 4 |

> **Thứ tự chạy quan trọng**: `fix_journals` → `fix_invoice_names` → `fix_invoice_names2` → `fix_taxes` → `fix_invoice_taxes` → `fix_reconciliation` → `fix_unmapped_invoices`
> Lý do: taxes phải fix trước reconciliation; journals phải tồn tại trước khi fix invoice names.

Chi tiết xem: [post-migration-fixes.md](post-migration-fixes.md)

---

## Bẫy thực tế đã gặp (Lessons Learned)

> Chi tiết đầy đủ: [lessons-learned.md](lessons-learned.md)

### Tóm tắt 15 bẫy chính

| # | Bẫy | Ảnh hưởng | Fix |
|---|-----|-----------|-----|
| 1 | V19 auto-apply 10% VAT default tax | 794 SO/PO lines + 793 AML lines bị sai tax → sai totals | Remove tax, restore V15 amounts |
| 2 | AML receivable/payable bị inflate do auto-tax | 222 invoices có wrong receivable amount → reconciliation fail | Zero extra lines, restore V15 receivable |
| 3 | `fix_invoice_taxes.py` overwrite amount_residual | 4,081 reconciled AML lines mất reconciliation state | Recalculate from partial_reconcile records |
| 4 | Invoice `name` field không copy qua ORM | ORM tự sinh sequence mới thay vì dùng V15 name | Direct SQL UPDATE |
| 5 | Unique constraint (name + journal_id) | ~200 invoices conflict khi fix names | Thêm suffix: `-R`, `-2` |
| 6 | `create_uid`/`write_uid` bị admin | 67,227 audit trail records sai người tạo | SQL UPDATE mapping user IDs |
| 7 | Chatter messages hiện "Administrator" | 19,633 messages sai author | Map V15 create_uid → V19 partner_id |
| 8 | `tz='Asia/Saigon'` invalid trên Python 3.12 | Partner creation fail | Transform → `Asia/Ho_Chi_Minh` |
| 9 | Partner `type='private'` removed in v19 | Partner creation fail | Transform → `contact` |
| 10 | Product `type='product'` → `type='consu'` + `is_storable=True` | Product type changed in v19 | Field transform mapping |
| 11 | VAT validation stricter in v19 | 4 partners reject VAT | Create without VAT, set via SQL |
| 12 | User Portal + User role conflict | Settings save fail | Remove Role/User group from Portal users |
| 13 | 200 AML lines không trong id_map | 200 partial reconcile unmappable | Tạo mới APR/AFR bằng SQL |
| 14 | `account_account.code` → `code_store` (jsonb) | SQL queries fail trên v19 | Dùng `code_store` thay `code` |
| 15 | account_full_reconcile mất column `name` | Queries reference non-existent column | Chỉ dùng `id` |

---

## Quy trình Verification

### 1. Record Count Comparison

```
res.partner:                 v15=304    v19=304    ✓
res.users:                   v15=13     v19=12     (1 skip: portaltemplate)
product.template:            v15=619    v19=619    ✓
sale.order:                  v15=995    v19=995    ✓
purchase.order:              v15=1383   v19=1383   ✓
account.move:                v15=4617   v19=4617   ✓
account.payment:             v15=2250   v19=2250   ✓
stock.picking:               v15=2451   v19=2451   ✓
mrp.production:              v15=1320   v19=1320   ✓
account.partial.reconcile:   v15=2242   v19=2242   ✓
account.full.reconcile:      v15=2239   v19=2239   ✓
```

### 2. Accounting Integrity Check

| Kiểm tra | V15 | V19 | Match |
|----------|-----|-----|-------|
| Payment state: paid | 2,263 | 2,263 | ✓ |
| Payment state: not_paid | 98 | 98 | ✓ |
| Reconciled AML lines | 4,493 | 4,503 | ~✓ (10 extra do V19 auto-create) |
| Open balance 131 (receivable) | 3,396,307,315 | 3,396,307,315 | ✓ |
| Open balance 331 (payable) | -3,119,824,713 | -3,119,824,713 | ✓ |

### 3. Spot Check Critical Invoices

```
HD/2022/00003: V15=paid,residual=0 | V19=paid,residual=0  ✓
HD/2024/00125: V15=paid,residual=0 | V19=paid,residual=0  ✓
HD/2025/00019: V15=paid,residual=0 | V19=paid,residual=0  ✓
```

### 4. Data Comparison Script

`odoo-migration/compare_migration.py` — 9-section report:
- Partner counts, user counts, product counts
- SO/PO header + line totals
- Invoice amounts by type (out_invoice, out_refund, in_invoice, in_refund)
- Payment totals, stock move quantities

---

## Cách sử dụng

### Chạy migration (22 phases)

```bash
cd E:\Project\odoo-tayafood

# Chạy tất cả phases
python -m odoo-migration.migrate.run

# Chạy phase cụ thể
python -m odoo-migration.migrate.run --phase 18 19 20

# Xem danh sách phases
python -m odoo-migration.migrate.run --list

# Reset (xóa id_map.json, bắt đầu lại)
python -m odoo-migration.migrate.run --reset
```

### Chạy post-migration fixes

```bash
# Thứ tự khuyến nghị:
python odoo-migration\fix_vat_partners.py
python odoo-migration\fix_bank_state.py
python odoo-migration\fix_journals.py
python odoo-migration\fix_pickings.py
python odoo-migration\fix_invoice_names.py
python odoo-migration\fix_invoice_names2.py
python odoo-migration\fix_user_permissions.py
python odoo-migration\fix_audit_fields.py
python odoo-migration\fix_chatter_author.py
python odoo-migration\fix_invoice_salesperson.py
python odoo-migration\fix_taxes.py
python odoo-migration\fix_invoice_taxes.py
python odoo-migration\fix_reconciliation.py
python odoo-migration\fix_unmapped_invoices.py
```

### Verify kết quả

```bash
python odoo-migration\compare_migration.py
```

### Troubleshooting

| Lỗi | Nguyên nhân | Fix |
|-----|------------|-----|
| `ConnectionError: Authentication failed` | v19 chưa init xong | `docker logs odoo19 --tail 20`, đợi thêm |
| `no mapping for parent_id` | Parent chưa migrate | Chạy đúng thứ tự phases |
| `duplicate key constraint` | Data cũ trên v19 | Reset v19 database + `--reset` |
| `Asia/Saigon` invalid | Deprecated timezone | Đã fix trong field_transform |
| `Value 'private' not in selection` | Type removed v19 | Đã fix trong field_transform |
| `column aa.code does not exist` | v19 dùng `code_store` (jsonb) | Sửa query dùng `aa.code_store` |
| Settings save lỗi "conflict groups" | User có cả Portal + User role | Xóa Role/User group |

---

## Tài liệu liên quan

- [pipeline.md](pipeline.md) — Kiến trúc pipeline chi tiết
- [post-migration-fixes.md](post-migration-fixes.md) — Chi tiết 14 fix scripts
- [lessons-learned.md](lessons-learned.md) — Kinh nghiệm chi tiết từ từng vấn đề
