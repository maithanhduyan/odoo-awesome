"""Check V15 display_type values and sample invoice/entry structures."""
import xmlrpc.client

c15 = xmlrpc.client.ServerProxy("http://localhost:8069/xmlrpc/2/common")
uid15 = c15.authenticate("taya_db", "tayafood@gmail.com", "TaYa@2022Pwd", {})
m15 = xmlrpc.client.ServerProxy("http://localhost:8069/xmlrpc/2/object")

c19 = xmlrpc.client.ServerProxy("http://localhost:19069/xmlrpc/2/common")
uid19 = c19.authenticate("taya19_db", "tayafood@gmail.com", "TaYa@2022Pwd", {})
m19 = xmlrpc.client.ServerProxy("http://localhost:19069/xmlrpc/2/object")

# 1. V15 display_type values on account.move.line
print("=== V15 account.move.line display_type distribution ===")
for dt in [False, "line_section", "line_note", "product", "tax", "payment_term", "cogs", "rounding"]:
    cnt = m15.execute_kw("taya_db", uid15, "TaYa@2022Pwd", "account.move.line", "search_count",
        [[("display_type", "=", dt)]])
    if cnt > 0:
        print("  display_type=%s: %d" % (repr(dt), cnt))

# 2. V15 exclude_from_invoice_tab distribution
print("\n=== V15 exclude_from_invoice_tab ===")
for val in [True, False]:
    cnt = m15.execute_kw("taya_db", uid15, "TaYa@2022Pwd", "account.move.line", "search_count",
        [[("exclude_from_invoice_tab", "=", val)]])
    print("  exclude_from_invoice_tab=%s: %d" % (val, cnt))

# 3. V19 display_type selection values
fg19 = m19.execute_kw("taya19_db", uid19, "TaYa@2022Pwd", "account.move.line", "fields_get",
    [], {"attributes": ["selection"]})
dt_sel = fg19.get("display_type", {}).get("selection", [])
print("\n=== V19 display_type selections ===")
for val, label in dt_sel:
    print("  '%s': %s" % (val, label))

# 4. Sample V15 out_invoice (posted)
print("\n=== V15 Sample out_invoice (posted) ===")
inv = m15.execute_kw("taya_db", uid15, "TaYa@2022Pwd", "account.move", "search_read",
    [[("move_type", "=", "out_invoice"), ("state", "=", "posted")]],
    {"fields": ["id", "name", "move_type", "state", "partner_id", "journal_id",
                "date", "invoice_date", "invoice_date_due", "currency_id",
                "amount_total", "amount_residual", "amount_untaxed", "amount_tax",
                "ref", "narration", "payment_reference", "invoice_origin",
                "invoice_payment_term_id", "line_ids", "invoice_line_ids",
                "company_id", "auto_post"],
     "limit": 1, "order": "id asc"})
if inv:
    i = inv[0]
    for k, v in sorted(i.items()):
        print("  %s: %s" % (k, repr(v)[:120]))
    # Read lines
    print("\n  --- Lines ---")
    lines = m15.execute_kw("taya_db", uid15, "TaYa@2022Pwd", "account.move.line", "read",
        [i["line_ids"]],
        {"fields": ["id", "name", "display_type", "exclude_from_invoice_tab",
                     "account_id", "product_id", "quantity", "price_unit", "discount",
                     "debit", "credit", "balance", "tax_ids", "tax_line_id",
                     "product_uom_id", "currency_id", "amount_currency", "sequence"]})
    for l in lines:
        print("  Line %d: dt=%s excl=%s acct=%s prod=%s qty=%s price=%s d=%s c=%s tax=%s taxline=%s" % (
            l["id"], repr(l["display_type"]), l["exclude_from_invoice_tab"],
            l["account_id"], l.get("product_id"), l["quantity"], l["price_unit"],
            l["debit"], l["credit"], l["tax_ids"], l["tax_line_id"]))

# 5. Sample V15 entry (likely payment)
print("\n=== V15 Sample entry ===")
ent = m15.execute_kw("taya_db", uid15, "TaYa@2022Pwd", "account.move", "search_read",
    [[("move_type", "=", "entry"), ("state", "=", "posted")]],
    {"fields": ["id", "name", "move_type", "state", "partner_id", "journal_id",
                "date", "ref", "line_ids", "payment_id", "amount_total"],
     "limit": 2, "order": "id asc"})
for e in ent:
    print("  entry %d: name=%s journal=%s partner=%s payment_id=%s lines=%d amount=%s" % (
        e["id"], e["name"], e["journal_id"], e["partner_id"],
        e.get("payment_id"), len(e["line_ids"]), e["amount_total"]))

# 6. Payment terms mapping check
print("\n=== V15 Payment Terms ===")
v15_pt = m15.execute_kw("taya_db", uid15, "TaYa@2022Pwd", "account.payment.term", "search_read",
    [[]], {"fields": ["id", "name"]})
for pt in v15_pt:
    print("  v15#%d: %s" % (pt["id"], pt["name"]))

print("\n=== V19 Payment Terms ===")
v19_pt = m19.execute_kw("taya19_db", uid19, "TaYa@2022Pwd", "account.payment.term", "search_read",
    [[]], {"fields": ["id", "name"]})
for pt in v19_pt:
    print("  v19#%d: %s" % (pt["id"], pt["name"]))

# 7. How many entry moves are payment-related?
print("\n=== V15 entry moves with payment_id ===")
with_pay = m15.execute_kw("taya_db", uid15, "TaYa@2022Pwd", "account.move", "search_count",
    [[("move_type", "=", "entry"), ("payment_id", "!=", False)]])
without_pay = m15.execute_kw("taya_db", uid15, "TaYa@2022Pwd", "account.move", "search_count",
    [[("move_type", "=", "entry"), ("payment_id", "=", False)]])
print("  with payment_id: %d" % with_pay)
print("  without payment_id: %d" % without_pay)
