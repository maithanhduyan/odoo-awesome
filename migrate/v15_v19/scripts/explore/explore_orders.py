"""Explore sale.order and purchase.order structures in V15 vs V19."""
import xmlrpc.client

pw = "TaYa@2022Pwd"

s15 = xmlrpc.client.ServerProxy("http://localhost:8069/xmlrpc/2/object")
u15 = xmlrpc.client.ServerProxy("http://localhost:8069/xmlrpc/2/common").authenticate(
    "taya_db", "tayafood@gmail.com", pw, {}
)
s19 = xmlrpc.client.ServerProxy("http://localhost:19069/xmlrpc/2/object")
u19 = xmlrpc.client.ServerProxy("http://localhost:19069/xmlrpc/2/common").authenticate(
    "taya19_db", "tayafood@gmail.com", pw, {}
)

keep_types = ("char", "many2one", "selection", "boolean", "date", "datetime",
              "integer", "float", "monetary", "text", "many2many", "one2many")

# ── sale.order fields ──
print("=" * 60)
print("SALE ORDER FIELDS COMPARISON")
print("=" * 60)

f15 = s15.execute_kw("taya_db", u15, pw, "sale.order", "fields_get", [],
                      {"attributes": ["string", "type", "readonly"]})
f19 = s19.execute_kw("taya19_db", u19, pw, "sale.order", "fields_get", [],
                      {"attributes": ["string", "type", "readonly"]})

common = sorted(set(f15.keys()) & set(f19.keys()))
v15_only = sorted(set(f15.keys()) - set(f19.keys()))
v19_only = sorted(set(f19.keys()) - set(f15.keys()))

print(f"\nCommon: {len(common)}, V15-only: {len(v15_only)}, V19-only: {len(v19_only)}")
print(f"\nV15-only (important): {[k for k in v15_only if not k.startswith('x_') and not k.startswith('message_') and f15[k]['type'] in keep_types]}")
print(f"\nV19-only (important): {[k for k in v19_only if not k.startswith('x_') and not k.startswith('message_') and f19[k]['type'] in keep_types]}")

# ── sale.order.line fields ──
print("\n" + "=" * 60)
print("SALE ORDER LINE FIELDS COMPARISON")
print("=" * 60)

fl15 = s15.execute_kw("taya_db", u15, pw, "sale.order.line", "fields_get", [],
                       {"attributes": ["string", "type", "readonly"]})
fl19 = s19.execute_kw("taya19_db", u19, pw, "sale.order.line", "fields_get", [],
                       {"attributes": ["string", "type", "readonly"]})

lcommon = sorted(set(fl15.keys()) & set(fl19.keys()))
lv15 = sorted(set(fl15.keys()) - set(fl19.keys()))
lv19 = sorted(set(fl19.keys()) - set(fl15.keys()))

print(f"\nCommon: {len(lcommon)}, V15-only: {len(lv15)}, V19-only: {len(lv19)}")
print(f"\nV15-only (important): {[k for k in lv15 if not k.startswith('x_') and not k.startswith('message_') and fl15[k]['type'] in keep_types]}")
print(f"\nV19-only (important): {[k for k in lv19 if not k.startswith('x_') and not k.startswith('message_') and fl19[k]['type'] in keep_types]}")

# ── purchase.order fields ──
print("\n" + "=" * 60)
print("PURCHASE ORDER FIELDS COMPARISON")
print("=" * 60)

pf15 = s15.execute_kw("taya_db", u15, pw, "purchase.order", "fields_get", [],
                       {"attributes": ["string", "type", "readonly"]})
pf19 = s19.execute_kw("taya19_db", u19, pw, "purchase.order", "fields_get", [],
                       {"attributes": ["string", "type", "readonly"]})

pcommon = sorted(set(pf15.keys()) & set(pf19.keys()))
pv15 = sorted(set(pf15.keys()) - set(pf19.keys()))
pv19 = sorted(set(pf19.keys()) - set(pf15.keys()))

print(f"\nCommon: {len(pcommon)}, V15-only: {len(pv15)}, V19-only: {len(pv19)}")
print(f"\nV15-only (important): {[k for k in pv15 if not k.startswith('x_') and not k.startswith('message_') and pf15[k]['type'] in keep_types]}")
print(f"\nV19-only (important): {[k for k in pv19 if not k.startswith('x_') and not k.startswith('message_') and pf19[k]['type'] in keep_types]}")

# ── Sample data ──
print("\n" + "=" * 60)
print("SAMPLE SALE ORDERS V15")
print("=" * 60)
sos = s15.execute_kw("taya_db", u15, pw, "sale.order", "search_read", [[]],
                      {"fields": ["id", "name", "state", "partner_id", "date_order",
                                  "pricelist_id", "currency_id", "user_id",
                                  "warehouse_id", "company_id", "amount_total",
                                  "order_line"],
                       "order": "id", "limit": 5})
for so in sos:
    print(so)

print("\n" + "=" * 60)
print("V15 sale.order STATES distribution")
print("=" * 60)
for state in ["draft", "sent", "sale", "done", "cancel"]:
    cnt = s15.execute_kw("taya_db", u15, pw, "sale.order", "search_count",
                          [[["state", "=", state]]])
    print(f"  {state}: {cnt}")

print("\n" + "=" * 60)
print("SAMPLE SALE ORDER LINES V15")
print("=" * 60)
sols = s15.execute_kw("taya_db", u15, pw, "sale.order.line", "search_read",
                       [[["order_id", "=", sos[0]["id"]]]],
                       {"fields": ["id", "name", "product_id", "product_uom",
                                   "product_uom_qty", "price_unit", "discount",
                                   "tax_id", "price_subtotal"]})
for sol in sols:
    print(sol)

print("\n" + "=" * 60)
print("SAMPLE PURCHASE ORDERS V15")
print("=" * 60)
pos = s15.execute_kw("taya_db", u15, pw, "purchase.order", "search_read", [[]],
                      {"fields": ["id", "name", "state", "partner_id", "date_order",
                                  "currency_id", "user_id", "company_id",
                                  "amount_total", "order_line"],
                       "order": "id", "limit": 5})
for po in pos:
    print(po)

print("\n" + "=" * 60)
print("V15 purchase.order STATES distribution")
print("=" * 60)
for state in ["draft", "sent", "to approve", "purchase", "done", "cancel"]:
    cnt = s15.execute_kw("taya_db", u15, pw, "purchase.order", "search_count",
                          [[["state", "=", state]]])
    print(f"  {state}: {cnt}")

print("\n" + "=" * 60)
print("SAMPLE PURCHASE ORDER LINES V15")
print("=" * 60)
pols = s15.execute_kw("taya_db", u15, pw, "purchase.order.line", "search_read",
                       [[["order_id", "=", pos[0]["id"]]]],
                       {"fields": ["id", "name", "product_id", "product_uom",
                                   "product_qty", "price_unit", "taxes_id",
                                   "price_subtotal", "date_planned"]})
for pol in pols:
    print(pol)

# Check V19 sale.order state options
print("\n" + "=" * 60)
print("V19 sale.order 'state' selection")
print("=" * 60)
if "state" in f19 and "selection" in f19["state"]:
    print(f19["state"]["selection"])
else:
    print(f19.get("state", {}))

print("\nV19 purchase.order 'state' selection")
if "state" in pf19 and "selection" in pf19["state"]:
    print(pf19["state"]["selection"])
else:
    print(pf19.get("state", {}))

# Check pricelist
print("\n" + "=" * 60)
print("V15 Pricelists")
print("=" * 60)
pls = s15.execute_kw("taya_db", u15, pw, "product.pricelist", "search_read", [[]],
                      {"fields": ["id", "name", "currency_id"]})
for pl in pls:
    print(pl)

print("\nV19 Pricelists")
pls19 = s19.execute_kw("taya19_db", u19, pw, "product.pricelist", "search_read", [[]],
                         {"fields": ["id", "name", "currency_id"]})
for pl in pls19:
    print(pl)

# Warehouses
print("\n" + "=" * 60)
print("V15 Warehouses")
print("=" * 60)
whs15 = s15.execute_kw("taya_db", u15, pw, "stock.warehouse", "search_read", [[]],
                         {"fields": ["id", "name", "code"]})
for w in whs15:
    print(w)

print("\nV19 Warehouses")
whs19 = s19.execute_kw("taya19_db", u19, pw, "stock.warehouse", "search_read", [[]],
                         {"fields": ["id", "name", "code"]})
for w in whs19:
    print(w)
